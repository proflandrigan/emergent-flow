# Bug Hunt Report: `ui/` (React canvas, branch `feature/explode-encode-lists-two-tower`, HEAD `6b82318`)

## Summary

- **Scope reviewed:** the `ui/` workspace in full — 178 TS/TSX files, ~25k lines. Weighted toward
  the places a defect is both reachable and provable:
  - **The contract boundary** (`src/store/ir.ts`, `model.ts`, `graphStore.ts`, `src/io/irFile.ts`,
    `IRToolbar.tsx`) — the only code that translates between the canvas model and the wire IR,
    and therefore the only place that can silently lose IR data. Checked systematically, not by
    eye: every checked-in graph in the repo (`examples/*.json` plus all three
    `examples/epic16_acceptance_demos/*.json`) was round-tripped through `fromIR`/`toIR` and
    deep-diffed field by field.
  - **Pure logic modules** where repros are cheap: `src/inspector/widgets.ts` (param↔widget
    coercion), `src/store/validateIR.ts`, `src/io/irFile.ts`.
  - **Async/state machinery**: `src/session/sessionStore.ts` (optimistic concurrency, SSE event
    fan-in), `src/session/sessionClient.ts`, `src/inspector/QueryBuilderPreview.tsx` and
    `LineagePanel.tsx` (debounced fetch + cancellation).
  - Automated lead generators: `npm run lint` (0 errors, 3 warnings — all triaged below),
    `npm run typecheck` (clean), `npm run build` (clean), and `npm test`
    (**631 passed / 83 files** at baseline — green, so nothing here is a pre-existing failure).
  - Cross-checked two UI-side assumptions against the Python server rather than assuming
    (the `stale_version` error prefix, and what the backend actually does with the value the
    canvas sends).
  - **Not covered:** visual/CSS regressions, drag-and-drop and React Flow interaction behaviour
    that needs a real browser, the CodeMirror-backed editors, and accessibility. See
    *Coverage & limitations*.
- **Confirmed findings:** 2 High. Both fixed, regression-tested, and committed.
- **Overall assessment:** the canvas is well built and the parts most likely to rot — the
  debounced-fetch cancellation in `LineagePanel`/`QueryBuilderPreview`, the SSE event
  serialization in `sessionStore`, the `Ajv`-backed IR validation on import — are all correct,
  and several suspicious-looking things turned out to be deliberate and right (documented in
  *Notes*). Both real defects are at the **boundary between the canvas's internal model and the
  IR contract**, and both share a root cause: the canvas model quietly represents *less* than
  the IR does, and nothing was checking that. One drops a whole IR field on every graph that
  passes through the store; the other picks a widget that can't represent its param's type.
  Neither was caught by the existing 631 tests because both round-trip tests only exercise
  FUNCTIONAL graphs built on the canvas itself, which never carry the lost field.

## Findings

### High — the canvas silently destroys an `nn.module`'s subgraph, leaving a graph that no longer compiles

- **Location:** `ui/src/store/ir.ts:56` (`nodeToIR`) and `:69` (`nodeFromIR`); root cause
  `ui/src/store/model.ts:25` (`NodeModel`)
- **Class:** Data loss — lossy model/wire mapping
- **Confidence:** Confirmed
- **Description:** `Node.subgraph` is the inner graph a composite/module node owns (ADR 0003
  "Option A" nesting). For a DECLARATIVE graph it is not a detail — it *is* the model: the
  `nn.module` node's subgraph holds the entire layer chain. `NodeModel` had no `subgraph` field,
  so `fromIR` dropped it on the way in and `toIR` could not put it back. Every path that moves a
  graph through the store is affected, because they all funnel through these two functions:
  | path | call site |
  |---|---|
  | Import an IR file | `IRToolbar.tsx:65` → `loadIR` |
  | Export an IR file | `IRToolbar.tsx:29` → `toIR` |
  | Create/join a collab session | `sessionStore.ts:239`, `:241`, `:253` |
  | Push the local graph to a session | `sessionStore.ts:271` |
  | **Accept an agent's proposal** | `sessionStore.ts:336` |
  | SSE `graph_replaced` / `proposal_accepted` | `sessionStore.ts:123` |
  | Run / compile / validate / lineage / steps | `ExecutionToolbar`, `CodePanel`, `useLiveValidation`, `LineagePanel`, `StepsPanel` |
- **Evidence / Reproduction:** the repo's own checked-in example,
  `examples/declarative_module.json`, put through the canvas's real mappers and then through the
  real Python compiler:
  ```
  --- ORIGINAL (as exported by the SDK)
      subgraph: present, 3 layers
      compile_to_code: OK -> ['class SimpleClassifier(nn.Module):']
  --- AFTER CANVAS IMPORT+EXPORT
      subgraph: MISSING (destroyed)
      compile_to_code: CodegenError: nn.module node 'n-module' has no subgraph to compile.
  ```
  A systematic field-by-field diff over **every** checked-in graph bounded the damage to exactly
  two fields — `Node.subgraph` and `Edge.type_compatible` — and showed that for FUNCTIONAL graphs
  the only change is `null -> undefined`, which is semantically identical (both deserialize to
  `None`). The declarative example is the only one that loses real content, and it loses all of
  it.
- **Impact:** A user opens a declarative model on the canvas and saves it: the model is gone,
  with no error at any point. The exported file still looks like a valid graph — it passes the
  importer's own Ajv validation — but `compile_to_code` now rejects it. The same destruction
  happens server-side the moment a declarative graph is pushed to a collab session or an agent
  proposal is accepted, so the loss is not confined to a local file the user could recover.
- **Remediation (applied):** carry the field through opaquely. `NodeModel` gains
  `subgraph?: IRGraph | null`, and both mappers copy it **only when the key was present**, so
  `null` vs absent round-trips exactly (the SDK writes `subgraph: null` on every leaf node; a
  canvas-built node has no such key and must not gain one):
  ```ts
  if (node.subgraph !== undefined) {
    ir.subgraph = node.subgraph;   // nodeToIR
  }
  ```
  The canvas still does not render or edit subgraphs — it just stops destroying them.
  Regression tests in `ui/src/store/ir.test.ts`: a module's subgraph survives deep-equal, an
  explicit `subgraph: null` stays `null`, and a canvas-built node does not gain the key.
  Re-verified end to end — the round-tripped example now compiles to
  `class SimpleClassifier(nn.Module)` again.

### High — `ml.compare_models`' estimator picker is a single-select for a list param, and sends a value the backend can't read

- **Location:** `ui/src/inspector/widgets.ts:60` (`widgetForParam`), with the rendering
  consequence at `ui/src/inspector/ConfigForm.tsx:151`
- **Class:** Logic error — precedence bug in widget selection, producing a type mismatch
- **Confidence:** Confirmed
- **Description:** `widgetForParam` tested `param.hints?.choices` **before** the list-type
  checks, so any list-typed param that also declares choices collapsed to a single-value
  `"select"`. Exactly one param in the shipped catalog has this shape, and it is the one where
  choosing several values is the entire point: `ml.compare_models.estimators`, `list[str]` over
  the 29-estimator catalog. Three things follow, all wrong:
  1. `ConfigForm` renders a plain `<select>` with no `multiple` — the user can pick **one**
     estimator for a node whose purpose is comparing several.
  2. `parseValue` takes the `"select"` branch and returns the raw **string**, so the IR param
     carries `"RandomForestClassifier"` where a `list[str]` is required.
  3. A correct list value — from an imported graph, an agent proposal, or the SDK — is displayed
     via `formatValue` as the joined string `"RandomForestClassifier, Ridge"`, which matches no
     option in the dropdown, and `validateValue` then flags the perfectly valid value with a
     spurious `Must be one of: ...`.
- **Evidence / Reproduction:** the pure functions, against the real shipped catalog entry:
  ```
  type_token        : list[str]
  widget chosen     : select                            <- single-value
  formatValue(list) : "RandomForestClassifier, Ridge"   <- matches no <option>
  validate(list)    : Must be one of: AdaBoostClassifier, ...   <- valid value rejected
  parseValue(pick)  : "RandomForestClassifier"  typeof: string  <- not a list
  ```
  And what the backend does with that string — it is iterable, so it is iterated
  *character by character*:
  ```
  correct list   : ef.ml.compare_models(..., estimators=['RandomForestClassifier','LogisticRegression'])
                   -> ok, 2 rows compared
  bare string    : ef.ml.compare_models(..., estimators='RandomForestClassifier')
                   -> UnknownEstimatorError: unknown estimator 'R'; expected one of [...]
  ```
- **Impact:** The node cannot be configured correctly from the canvas at all. Picking estimators
  either produces a run that dies with `unknown estimator 'R'` — an error naming a single letter,
  which points nowhere near the actual cause — or, if the user leaves a valid list alone, shows a
  permanent false validation error on a correct graph.
- **Remediation (applied):** match the list shape first and give it a real widget.
  `WidgetKind` gains `"multiselect"`; `widgetForParam` returns it when a param has choices **and**
  a list type (scalar-with-choices still returns `"select"`, unchanged):
  ```ts
  if (param.hints?.choices && isListType(param.type_token)) {
    return "multiselect";
  }
  ```
  `ConfigForm` renders a native `<select multiple>` that writes the selection straight back as an
  array (deliberately *not* via `parseValue` — the selected options are already the typed value).
  `validateValue` gains a multiselect branch that bounds item **count** via `min_length`/
  `max_length` and checks membership **per item** instead of against the stringified array, and
  `parseValue` treats the kind like a list so a string value still yields an array.
  Regression tests in `ui/src/inspector/widgets.test.ts` (8 cases, including one asserting the
  real `ml.compare_models.estimators` catalog entry resolves to `multiselect` and that a valid
  two-item value passes) and `ui/src/inspector/ConfigForm.test.tsx` (the rendered element is
  `multiple`, and selecting two options stores `["RandomForestClassifier", "Ridge"]`).

## Notes & unverified leads

Leads chased and **refuted on evidence**:

- **`QueryBuilderPreview.tsx:99` — eslint's "missing dependency: 'spec'" (refuted).** The one
  substantive lint warning in the workspace. It is a deliberate serialize-as-dependency pattern:
  the dep array holds `specKey = JSON.stringify({ spec, dialect })`, and `spec` is a pure function
  of the same render's inputs, so the effect re-runs exactly when the content changes and the
  captured `spec` is always the one that produced the current `specKey`. Adding `spec` to the
  array would instead re-fire on every render, since `buildSpec(node)` returns a fresh object.
  Not a stale closure.
- **`Edge.type_compatible` dropped on round-trip (refuted as harmful).** It *is* dropped, but the
  systematic diff showed the only observed transition is `null -> undefined`, which is
  semantically identical for the consumer (both mean "not yet checked"). A non-`null` cached
  verdict is recomputed by `/validate` on every change and held live in `validationStore`, so
  preserving a stale verdict across an edit would be worse than dropping it. Deliberate-looking
  and harmless; left alone.
- **`stale_version` detected by string prefix (refuted).** `sessionStore` branches on
  `errorMessage(err).startsWith("stale_version")` to raise its rebase UI — brittle-looking, and it
  would silently disable conflict handling if the server's wording drifted. Checked against the
  server: `emergentflow/server/app.py:250` returns `_error_json(409, f"stale_version: {exc}")`, and
  `sessionClient` rethrows `body.error` verbatim, so the prefix is a real contract that holds.
- **Other lost IR fields (refuted by exhaustive check).** Beyond the two above, the field-by-field
  diff over every checked-in graph found no other dropped or altered field.
- **The other two lint warnings (refuted).** Both are `react-refresh/only-export-components` in
  `SchemaBrowserPanel.tsx` and `Palette.tsx` — a dev-server hot-reload ergonomics rule, with no
  runtime behaviour attached.

**Unverified / noted, deliberately not promoted to findings:**

- The `"list"` widget joins on `", "` and splits on `","`, so a list item that itself contains a
  comma does not survive an edit round-trip (`["a,b"]` → `"a, b"` → `["a", "b"]`). This is
  inherent to a comma-separated text widget and is documented as such in `widgets.ts`; it needs a
  realistic param where comma-bearing values occur to be worth calling a bug.
- `LineagePanel` keeps rendering the *previous* node's lineage for the 400 ms debounce window
  after the selection changes, because the effect doesn't clear `lineage` before the new fetch is
  scheduled. Cosmetic and transient; carried over from the previous report's note.
- `nodeToIR` normalizes an absent `group_id` to `null`, so a node that arrived without the key
  gains `group_id: null` on export. Semantically a no-op on the Python side (the field defaults to
  `None`) and pre-existing; noted only because it surfaced while asserting exact round-trip
  equality.

## Coverage & limitations

- Everything was verified in `jsdom` via vitest, plus the real Python compiler for the
  cross-boundary claims. No real browser was driven, so drag-and-drop, React Flow viewport/edge
  interaction, canvas rendering, CSS/theming and accessibility are **not** covered by this pass.
- The CodeMirror-backed editors (`CodePanel`, the SQL/Python param widgets) were read but not
  exercised — they need a real editor host to probe meaningfully.
- `ChatModal.tsx` (709 lines, the largest file in the workspace) and the connections panels were
  reviewed for state-machine and error-handling shape but not driven end to end, since both need a
  live server and, for chat, a live agent backend.
- `prettier --check` reports pre-existing non-conformance in several files (including
  `widgets.ts` and `ConfigForm.tsx` before this change). It is **not** a CI gate — the UI job runs
  `gen:types` drift check, `lint`, `typecheck`, `build`, `test` — so the fixes deliberately do not
  reformat those files, to avoid burying two small behavioural changes in unrelated churn. The
  added test code introduces no churn in any pre-existing region (verified by diffing the
  pre-existing line range against `HEAD`).
- Gates after the fixes: `npm run lint` 0 errors (same 3 pre-existing warnings), `npm run typecheck`
  clean, `npm run build` clean, `npm test` **643 passed / 83 files** (was 631 — the 12 added
  regression tests), no regressions.
