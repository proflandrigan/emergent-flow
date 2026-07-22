# Bug Hunt Report: PR #90 (branch `issue-fixes-v1` vs `main`)

## Summary
- Scope reviewed: the full diff `main...issue-fixes-v1` (60 files, ~4,600 insertions) —
  Python (`emergentflow/eval/{score,judge}.py`, `emergentflow/ir/mutation.py`,
  `emergentflow/codegen/inspect.py`, `emergentflow/llm/__init__.py`,
  `emergentflow/nodes/examples/{eval_judge,eval_score,llm_call,llm_prompt,llm_prompt_from_file}.py`,
  `emergentflow/server/{app,service}.py`, `pyproject.toml`/`uv.lock`) and the UI
  (`ui/src/canvas/{Canvas,NodeContextMenu,NodeInfoPanel,SelectionToolbar,layout,nodes/EfNode}.tsx`,
  `ui/src/inspector/{CodePanel,Inspector,StepsPanel}.tsx`, `ui/src/store/graphStore.ts`,
  `ui/src/session/{ChatComposer,ChatModal}.tsx`).
- Confirmed findings: 4 (1 High, 3 Medium), all fixed in this session.
- All four confirmed bugs share one root cause: a "de-overlap"/"cascade" fix (issues #91,
  #94) that only checks the new item against *some* of the existing positions, not the
  full, evolving set — so the same-position collision it was written to solve can reappear
  one hop away. A fifth area (CodePanel's per-line highlight splitting, added for #95) had
  an unrelated but same-severity-class defect: naive string splitting of HTML that ignores
  tag boundaries, breaking highlighting for any LLM-touching graph's generated module
  docstring — the single most common code shape this PR's own features (#92 `llm.prompt`,
  #93 `eval.judge`) produce. All five are fixed with accompanying regression tests; the
  rest of the diff (deterministic scorers, LLM-as-judge client threading, prompt-from-file
  I/O quarantine, `build_step_traces` naming parity, the `db-dtypes` fix) held up under
  equivalence/parity review with no other confirmed defects.

## Findings

### High — `apply_mutation`'s node-cascade can collide with an explicitly-positioned sibling in the same batch
- **Location:** `emergentflow/ir/mutation.py:117-129` (pre-fix)
- **Class:** Off-by-one / incomplete collision set
- **Confidence:** Confirmed
- **Description:** The #91 fix nudges any `add_nodes` entry left at the default `Position()`
  sentinel to `(max_x, max_y) + step*(index+1)` of the graph's *pre-existing* node positions.
  It never checks the computed point against other nodes being added in the *same* mutation
  batch — neither explicitly-positioned siblings nor earlier cascaded ones. An agent (or the
  canvas) proposing a batch that mixes one explicitly-anchored node with several
  default-positioned ones can produce an exact duplicate position.
- **Evidence / Reproduction:**
  ```python
  g = Graph()
  m = GraphMutation(base_version=1, add_nodes=[
      Node(id="a", type="data.load_csv", position=Position(x=60, y=60)),
      Node(id="b", type="data.load_csv"),  # default position -> cascades
  ])
  g2 = apply_mutation(g, m)
  # before fix: a -> (60,60), b -> (60,60)  <-- exact collision
  ```
- **Impact:** Reintroduces the exact "nodes pile up on top of each other" bug issue #91 was
  filed to fix, for the common case of an agent placing one anchor node plus a batch of
  auto-positioned ones in a single mutation.
- **Remediation (applied):** Track a `taken_positions` set seeded from the pre-existing
  graph and grown as each `add_nodes` entry (explicit or cascaded) is placed; `_next_cascade_position`
  now loops the cascade index until it lands on a point not in `taken`. Regression test added:
  `tests/test_mutation.py::TestApplyMutationAdds::test_cascaded_default_position_does_not_collide_with_explicit_sibling`.

### Medium — `separateOverlappingNodes` can cascade a node onto an unrelated node elsewhere in the graph
- **Location:** `ui/src/canvas/layout.ts:17-51` (pre-fix)
- **Class:** Off-by-one / incomplete collision set
- **Confidence:** Confirmed
- **Description:** Same root cause as the Python finding above, on the canvas's own
  `loadIR`-time de-overlap pass. Nodes are grouped by their *original* rounded position;
  each colliding group member after the first is nudged by `CASCADE_STEP * index` — computed
  purely from its own original spot, never checked against the rest of the graph's occupied
  coordinates (including other groups, or nodes that don't collide with anything).
- **Evidence / Reproduction (Node.js, using the exact algorithm before the fix):**
  ```js
  const nodes = {
    A: { id: "A", position: { x: 0, y: 0 } },
    B: { id: "B", position: { x: 0, y: 0 } },   // collides with A
    C: { id: "C", position: { x: 48, y: 48 } }, // unrelated, elsewhere
  };
  separateOverlappingNodes(nodes);
  // before fix: B -> (48, 48)  <-- lands exactly on C
  ```
- **Impact:** A graph load can "fix" one overlap by creating a new one, silently, for any
  layout where a collision group's cascade step happens to land on another node's spot —
  plausible on any hand-arranged or agent-arranged canvas using round-number coordinates.
- **Remediation (applied):** `separateOverlappingNodes` now seeds a `taken` set with every
  node's position up front and keeps stepping a colliding member's cascade offset until it
  lands on a genuinely free spot, adding each resolved spot to `taken` before moving on.
  Regression test added: `ui/src/canvas/layout.test.ts` — "a cascaded node never lands on an
  unrelated node elsewhere in the graph".

### Medium — Repeated paste of the same clipboard stacks new nodes on top of each other
- **Location:** `ui/src/canvas/Canvas.tsx:232-241` / `ui/src/store/graphStore.ts:234-256` (pre-fix)
- **Class:** Stale state / incomplete collision handling
- **Confidence:** Confirmed
- **Description:** `pasteNodes(models)` always offsets its clones by a fixed `+40,+40` from
  each *model's own* position. `Canvas.tsx`'s Ctrl+V handler always calls `pasteNodes(clipboard)`
  with the clipboard captured at Ctrl+C time and never updates it afterward, so a second
  (third, ...) Ctrl+V of the same clipboard clones from the same original coordinates and
  produces a node at the exact same `+40,+40` spot as the previous paste.
- **Evidence / Reproduction (via the real `graphStore`, in an isolated vitest run):**
  ```
  originalId = addNodeFromSpec(loadCsv, {x:0, y:0})
  [id1] = pasteNodes([original])   // -> (40, 40)
  [id2] = pasteNodes([original])   // -> (40, 40)  <-- same spot as id1
  ```
  Confirmed by adding a temporary test asserting `pos1 !== pos2`, running it (it failed,
  both `{x:40,y:40}`), then removing the temporary file before making the real fix.
- **Impact:** The exact workflow issue #94 was meant to support — "select, copy, paste
  several times to make several copies" — produces indistinguishable, fully overlapping
  nodes after the first paste.
- **Remediation (applied):** `pasteNodes` now runs the merged node map through
  `separateOverlappingNodes` (the same de-overlap helper `loadIR` already uses) before
  committing state, so a clone landing on an already-occupied spot (including one from an
  earlier paste) is pushed to the next free cascade point automatically. Regression test
  added: `ui/src/store/graphStore.test.ts` — "pasting the same clipboard twice in a row does
  not stack the two new nodes on each other".

### Medium — CodePanel's per-line highlight splitting breaks syntax highlighting for any multi-line span (e.g. every LLM graph's module docstring)
- **Location:** `ui/src/inspector/CodePanel.tsx:137-154` (pre-fix)
- **Class:** API/contract misuse (treating hljs's single HTML string as line-independent)
- **Confidence:** Confirmed
- **Description:** The #95 "jump to line" feature renders `hljs.highlight(code).value.split("\n")`
  as one `<div>` per line so it can inject a scroll target and highlight background on a
  specific line. `highlight.js` emits one HTML string for the whole input; a `<span>` can
  legitimately wrap text containing real newlines (any token — most commonly a triple-quoted
  string — that itself spans lines). Splitting on raw `"\n"` cuts such spans apart: the
  interior lines lose the class entirely, and the boundary lines get an unmatched open/close
  tag.
- **Evidence / Reproduction:** `compiler.py` (unchanged by this PR, `emergentflow/codegen/compiler.py:363-364`)
  emits a triple-quoted module docstring for **any graph containing an LLM node** whenever
  `needs_llm and (env_hints or connection_hints)` — i.e. essentially any use of `llm.call`,
  `llm.prompt`, or (this PR's own) `eval.judge`. Compiling a real one-node `llm.call` graph
  and running the actual output through `hljs.highlight` + a `"\n"`-split shows the docstring's
  middle lines rendered with **no** `hljs-string` class, and the boundary lines with an
  unbalanced `<span>`/`</span>`:
  ```
  0 UNBALANCED "<span class="hljs-string">&quot;&quot;&quot;Generated by Emergent Flow..."
  1 balanced   "" (should be inside the string span; isn't)
  2 balanced   "This script calls an LLM provider. Before running it, set:" (unstyled, should be a string)
  3 UNBALANCED "    export ANTHROPIC_API_KEY=...&quot;&quot;&quot;</span>"
  ```
- **Impact:** Cosmetic but real regression in the Code tab's syntax highlighting for the
  most common graph shape in this app (any graph using an LLM node) — directly touches two
  of this PR's own new/changed node types (`llm.prompt`, `eval.judge`).
- **Remediation (applied):** Replaced the naive `.split("\n")` with `splitHighlightedByLine`,
  which walks the HTML tracking a stack of currently-open `<span class="...">` tags, closing
  them (without popping) at each line boundary and reopening identical tags at the start of
  the next line — every returned line is now self-contained, balanced HTML that still carries
  whatever class an unbroken span would have applied. Verified against the real
  `compile_to_code` output for an `llm.call` graph (all lines balanced, docstring lines keep
  `hljs-string`). Regression test added:
  `ui/src/inspector/CodePanel.test.tsx` — "keeps syntax highlighting valid across a multi-line
  string (e.g. the module docstring every LLM graph compiles to)".

## Notes & unverified leads (optional)
- `/inspect` (`emergentflow/server/service.py:inspect_graph`) always constructs a real
  `GatewayClient`/warehouse client and calls the raw `execute()` (not the cached,
  per-node-status `_execute_functional_with_status` path `/execute` uses), so opening the
  Steps tab on a graph with LLM/warehouse nodes triggers a full, uncached, all-or-nothing
  re-run — including real paid API calls — every time. This appears to be a deliberate
  design choice (documented in the function's own docstring) rather than a bug, but it's
  worth the team explicitly confirming that's intended before this ships, since it's an easy
  way to burn LLM spend by clicking a UI tab.
- Two commits on this branch (`fix(ui): fill chat panel height and soften message bubble
  styling`, `feat(ui): send chat messages on Enter, open slash-command persona palette`)
  aren't attributed to any of the seven issues (#87, #88, #91–#95) the PR body claims to
  fix, and there's no open issue for them in the repo's tracker. Not a functional bug, but
  worth flagging as scope not documented in the PR description.
- `emergentflow/eval/score.py`'s `_score_regex`/`_score_exact_match`/etc. raise a bare
  `KeyError` (not `ScorerError`) when a scorer spec is missing a kind-specific required key
  (e.g. `regex` without `pattern`). The docstring only promises `ScorerError` for a missing
  `name`/`kind` or an unrecognized `kind`, so this matches the documented contract — flagged
  here only as a minor error-typing inconsistency worth a follow-up, not a confirmed bug.

## Coverage & limitations
- Did not deep-dive `ChatComposer.tsx`/`ChatModal.tsx` beyond the scope-attribution note
  above (they implement a slash-command palette unrelated to the seven target issues).
- Did not fuzz `eval.score`'s JSON-schema subset checker (`_json_schema_violations`) beyond
  reading it; its handling of an unrecognized `schema["type"]` string (silently skips the
  type check) looked like a possible gap but wasn't pursued to a reproducible finding.
- Full Python test suite (`uv run pytest`) and full UI suite (`npm test`, 80 files / 611
  tests) were run after the fixes; both green, alongside `ruff check`, `ruff format --check`,
  `mypy`, `eslint`, `tsc --noEmit`, and `scripts/check_ui_boundary.py`.
