# Bug Hunt Report: entire codebase (branch `feature/explode-encode-lists-two-tower`, HEAD `70264ad`)

## Summary

- **Scope reviewed:** a whole-repository pass, weighted toward surface that prior hunts have
  *not* covered. Coverage was first mapped against the eleven existing reports in
  `.bug-hunt/`, which between them already cover `recommend/`, `ml/`, `clean/` (the pre-Epic-16
  ops), `stats/`, `llm/`, `eval/`, `viz/`, `ir/mutation.py`, `codegen/inspect.py`, and Epic 16
  Story groups A–D. This pass therefore concentrated on:
  - **Never-hunted-since-`5781588` core:** `emergentflow/server/` (`app.py`, `service.py`,
    `payload.py`, `cache.py`), `emergentflow/collab/session.py`, and the `emergentflow/codegen/`
    pipeline (`traversal.py`, `wiring.py`, `naming.py`, `compiler.py`, `validation.py`,
    `inference.py`, `export.py`).
  - **The newest un-hunted commits** — Story group E (`efebcf6`) and its follow-ups
    (`bc8a022`, `6f95e65`, `70264ad`): `emergentflow/types/` (`registry.py`,
    `compatibility.py`, `catalog.py`, `rules_artifact.py`) plus `schema/rules.json`, which
    together introduce the catalog's **first-ever explicit subtype edge**
    (`DocumentFrame <: DataFrame`), and the new UI inspector renderers
    (`LineagePanel.tsx`, `ReportView.tsx`, `PayloadView.tsx`).
  - **`emergentflow/research/`** (`lineage.py`, `quality.py`, `reproducibility.py`,
    `report.py`) and the Epic 16 `clean` verbs, probed empirically rather than only read.
  - Automated lead generators: `ruff check`, `ruff format --check`, `mypy emergentflow`
    (all clean at baseline), and the full `pytest` suite (**3288 passed, 24 skipped** at
    baseline — a green starting point, so nothing here is a pre-existing test failure).
  - **Not covered:** the `[bayes]`/`[explain]`/`[recommend]`/`[mcp]` optional-extra code paths
    beyond what the installed venv exercises, live warehouse drivers, and the bulk of `ui/src/`
    beyond the Story-group-E components (see *Coverage & limitations*).
- **Confirmed findings:** 2 Medium, 1 Low. All three are fixed, regression-tested, and
  committed.
- **Overall assessment:** the codebase is in good shape and the central invariants hold up
  under direct probing. ADR-0002's compile/execute equivalence gate passes; the determinism
  discipline the project depends on is genuinely pervasive — `topological_sort` breaks ties on
  a min-heap of node ids, `build_wiring_map` explicitly sorts fan-in sources,
  `build_name_map` sorts nodes and uses `blake2s` rather than the salted builtin `hash()`,
  `validate` sorts `graph.edges.items()`, and `capture_run` sorts node ids. Several promising
  leads were chased and **refuted** on evidence (see *Notes*), including a suspected fan-in
  ordering bug that turned out to be correctly guarded. The three real defects are all in
  code with thin or absent direct unit-test coverage: `fuzzy_join`'s collision guard checked
  the wrong thing, `trace_lineage` was the one pass in the codebase that *didn't* pin its
  output order, and `check_data_quality` — which has no dedicated test file at all — leaked a
  bare `KeyError` through a documented typed-error contract.

## Findings

### Medium — `fuzzy_join` silently emits duplicate column labels on a suffix collision

- **Location:** `emergentflow/clean/sampling.py:148`
- **Class:** API/contract misuse — collision check operates on a set, which erases the very
  duplicates it is meant to detect
- **Confidence:** Confirmed
- **Description:** When a key column overlaps between the two frames it is renamed with
  `suffixes[0]`/`suffixes[1]`. The guard built `final_left_columns` / `final_right_columns` as
  **sets** and only ever tested `score_column` against them. If suffix-renaming lands on a
  name that already exists (left has both `k` and `k_x`; `k` overlaps and is renamed to
  `k_x`), the set collapses the pair and the collision goes undetected — the function returns
  a DataFrame with two identically-labelled columns.
- **Evidence / Reproduction:**
  ```python
  left  = pd.DataFrame({'k': ['apple', 'banana'], 'k_x': [1, 2]})
  right = pd.DataFrame({'k': ['apple'], 'r': [9]})
  out = ef.clean.fuzzy_join(left, right, left_on='k', right_on='k', how='left')
  ```
  Observed, before the fix:
  ```
  columns: ['k_x', 'k_x', 'k_y', 'r', 'match_score']
  duplicate columns? True
  ```
  This is demonstrably out of step with the rest of the family — every sibling verb rejects
  the same class of collision, verified by running each:
  | op | behaviour on an output-name collision |
  |---|---|
  | `clean.concat` (`source_column`) | `ColumnCollisionError` |
  | `clean.reshape` (`var_name`/`value_name`) | `ColumnCollisionError` |
  | `clean.clean_text` (`suffix`) | `ColumnCollisionError` |
  | `clean.parse_dates` (`components`) | `ColumnCollisionError` |
  | `clean.merge` / `pandas.merge` | `MergeError: Passing 'suffixes' which cause duplicate columns {'v_x'} is not allowed.` |
  | `timeseries.ewma` / `lag_features` / `rolling_aggregate` / `difference` / `time_weighted_aggregate` | `TimeseriesError` |
  | **`clean.fuzzy_join`** | **silently returns duplicate columns** |
- **Impact:** A silently corrupt frame flows downstream. Any subsequent `df["k_x"]` returns a
  *DataFrame* rather than a Series, so downstream ops fail with confusing, far-removed errors
  instead of at the join; `ef.clean.select_columns` and friends misbehave; and the server's
  `to_payload` hits its duplicate-column `ValueError` fallback path when rendering the result
  on the canvas.
- **Remediation (applied):** build the final column lists as **lists**, detect any duplicate
  across the combined set, and raise `ColumnCollisionError` — matching the sibling verbs and
  pandas' own `MergeError` contract:
  ```python
  final_left_columns = [f"{c}{suffixes[0]}" if c in overlap else c for c in left.columns]
  final_right_columns = [f"{c}{suffixes[1]}" if c in overlap else c for c in right.columns]
  final_columns = final_left_columns + final_right_columns
  duplicated = sorted({c for c in final_columns if final_columns.count(c) > 1}, key=str)
  if duplicated:
      raise ColumnCollisionError(
          f"suffixes {suffixes!r} produce duplicate output column(s) {duplicated!r}; "
          "choose different suffixes or rename the colliding column(s) before joining."
      )
  ```
  The `score_column` check now runs against the same list. The docstring gained a `Raises:`
  section. Regression tests:
  `tests/test_clean_sampling.py::test_fuzzy_join_suffix_rename_collision_is_rejected` (the
  collision now raises) and `::test_fuzzy_join_non_colliding_suffixes_still_join` (an ordinary
  overlapping-key join is unaffected).

### Medium — `trace_lineage` returns edges in dict insertion order, so identical graphs trace differently

- **Location:** `emergentflow/research/lineage.py:137`
- **Class:** Non-determinism / ordering dependency
- **Confidence:** Confirmed
- **Description:** `Lineage.nodes` is correctly deterministic — it is filtered from
  `topological_sort(graph)`, which breaks ties on a min-heap of node ids and is explicitly
  documented as insertion-order independent. `Lineage.edges`, however, was built by iterating
  `graph.edges.values()` directly, i.e. **dict insertion order**. Two structurally identical
  graphs whose edges were added in a different order therefore trace to different `edges`
  orderings. This is the only pass in the codebase that doesn't pin this down:
  `topological_sort`, `build_wiring_map` (`sorted(sources, key=...)`), `build_name_map`,
  `validate` (`sorted(graph.edges.items())`) and `capture_run` (`sorted(graph.nodes)`) all do.
- **Evidence / Reproduction:** the same diamond graph (`A -> {B, C} -> D`) built twice with
  the identical four edges inserted in opposite order — `nodes` matches, `edges` does not:
  ```
  nodes g1: ['a', 'b', 'c', 'd']
  nodes g2: ['a', 'b', 'c', 'd']
  nodes deterministic: True
  edges g1: [('a','b'), ('a','c'), ('b','d'), ('c','d')]
  edges g2: [('c','d'), ('b','d'), ('a','c'), ('a','b')]
  edges deterministic: False
  ```
- **Impact:** Ordinary canvas editing (deleting and re-adding an edge, or applying a
  `GraphMutation`) changes edge insertion order, so the `/lineage` route returns a different
  payload for a graph that has not structurally changed. `LineagePanel.tsx` resolves each hop
  with `currentLineage.edges.find(...)`, so with parallel edges between the same pair the
  rendered hop can change between traces. It also undermines the reproducibility guarantee
  that is the entire point of the epic this function belongs to (Story 17/18), and makes
  `Lineage` — a registered inspectable type users can compose into reports — unstable as a
  golden-test or report artifact.
- **Remediation (applied):** sort the induced-subgraph edges deterministically, keyed to
  follow the topological `order` that `nodes` already presents, with the edge id as the
  tie-break for parallel edges:
  ```python
  position = {nid: i for i, nid in enumerate(order)}
  in_subgraph = [
      (edge_id, edge) for edge_id, edge in graph.edges.items()
      if edge.source.node_id in visited and edge.target.node_id in visited
  ]
  in_subgraph.sort(key=lambda item: (
      position[item[1].source.node_id], position[item[1].target.node_id], item[0],
  ))
  ```
  Both the `Lineage.edges` attribute docs and `trace_lineage`'s `Returns` section now state
  the guarantee. Regression test:
  `tests/test_research_lineage.py::test_trace_lineage_edge_order_is_insertion_order_independent`
  asserts both that the two orderings agree and that the result follows source-then-target
  topological order.

### Low — `check_data_quality` raises a bare `KeyError` for an unknown column, breaking its documented error contract

- **Location:** `emergentflow/research/quality.py:39` (and `:51`, `:70`, `:82`, `:95` — every
  column-scoped check)
- **Class:** Error handling — undocumented, untyped exception escaping a documented contract
- **Confidence:** Confirmed
- **Description:** `check_data_quality`'s docstring documents exactly two failure modes:
  `DataQualityError` (an expectation evaluated to a violation) and `ResearchError` (an
  expectation named an unknown `"type"`). But every column-scoped check indexes
  `frame[column]` directly, so an expectation naming a column that isn't in the frame escapes
  as a bare `KeyError` — a third, undocumented failure mode.
- **Evidence / Reproduction:** all five column-scoped expectation types, before the fix:
  ```
  ef.research.check_data_quality(df, [{"type": "non_null",       "column": "nope"}])  -> KeyError: 'nope'
  ef.research.check_data_quality(df, [{"type": "range",          "column": "nope", "min": 0}])       -> KeyError: 'nope'
  ef.research.check_data_quality(df, [{"type": "unique",         "column": "nope"}])  -> KeyError: 'nope'
  ef.research.check_data_quality(df, [{"type": "regex_match",    "column": "nope", "pattern": "x"}]) -> KeyError: 'nope'
  ef.research.check_data_quality(df, [{"type": "allowed_values", "column": "nope", "values": [1]}])  -> KeyError: 'nope'
  ```
  Contrast the same mistake elsewhere in the SDK, which is uniformly typed and names what was
  available:
  ```
  ef.clean.select_columns(df, columns=["nope"])  -> UnknownColumnError: unknown columns ['nope']; expected one of ['t', 'v'].
  ef.stats.correlation(df,   columns=["nope"])  -> ValueError:         unknown columns ['nope']; expected one of ['t', 'v'].
  ```
- **Impact:** A typo in an expectation surfaces on the canvas (and to any `assert_data` node
  caller) as `KeyError: 'nope'` with no indication of which expectation was at fault or what
  columns actually exist. Callers catching the documented `ResearchError` — the reasonable
  thing to do given the docstring — don't catch it at all, so it propagates as an unhandled
  error rather than a reported data-quality problem.
- **Remediation (applied):** validate column-scoped expectations up front, raising the already
  documented `ResearchError` with the same message shape the rest of the SDK uses:
  ```python
  if etype in _COLUMN_SCOPED_CHECKS:
      column = exp.get("column")
      if column not in frame.columns:
          raise ResearchError(
              f"expectation {etype!r} names unknown column {column!r}; "
              f"expected one of {list(frame.columns)!r}."
          )
  ```
  `_COLUMN_SCOPED_CHECKS` is derived from `_SINGLE_VIOLATION_CHECKS` minus `"row_count"`, so
  it can't drift as expectation types are added. `"row_count"` (frame-scoped) and `"schema"`
  (whose job *is* reporting missing columns) are deliberately exempt. The docstring's
  `Raises:` section now covers it. This module had **no dedicated test file**, which is why
  the gap survived; `tests/test_research_quality.py` is new and covers the pass path, the
  violation path, unknown types, all five column-scoped types (parametrized), and the two
  exemptions.

## Notes & unverified leads

Leads chased and **refuted on evidence** — recorded so a later hunt doesn't re-spend the time:

- **Fan-in source ordering (suspected, refuted).** `build_wiring_map` populates its `incoming`
  map by iterating `graph.edges.values()`, which looked like the same insertion-order bug as
  the lineage finding — and it would have been far more serious, since a `Cardinality.MANY`
  port's source order determines row order for `clean.concat`, section order for
  `research.build_report`, and the recommender-list order for `recommend.compare` /
  `hybrid_weighted` / `hybrid_switching`. Refuted: `wiring.py:150` applies
  `sorted(sources, key=lambda ref: (ref.node_id, ref.port_id))` before building each
  `InputBinding`. Verified empirically by executing and compiling the same fan-in graph with
  edges inserted in both orders — `execute` results and `compile_to_code` output were both
  byte-identical.
- **Client-side mirror of the subtype rules (refuted).** ADR 0012 says the frontend
  re-implements the compatibility check over the serialized catalog, and Story group E adds
  the catalog's first-ever subtype edge — a client-side implementation that ignored
  `subtypes` would have been invisible until exactly this commit. Refuted: `ui/src/` has no
  such implementation; it consumes the server's `/validate` `edge_compatibility` map
  (`ui/src/store/validation.ts`), so there is no second algorithm to drift.
- **Non-finite floats in the `"table"` payload (refuted).** `to_payload`'s DataFrame branch
  hands `sample.to_json(orient="records")` straight to `json.loads` without passing through
  `_sanitize_nonfinite`, which the module docstring warns produces browser-invalid
  `NaN`/`Infinity` tokens. Refuted by test: pandas' `to_json` maps `inf`, `-inf` **and** `NaN`
  to `null`, and the resulting payload re-serializes to valid JSON.
- **`capture_run` content hashes never populating (refuted).** `capture_run` gates content
  hashing on `node.type.startswith("data.")`, which would be a silent no-op if node types
  were unprefixed. Refuted: all eleven loader node types really are `data.*`-prefixed.
- **`ExecutionCache` serving stale results for file-backed nodes (refuted).** `_node_hash`
  covers params but not file *contents*, so a cacheable loader would serve stale data after
  the file changed. Refuted: every file- or network-reading node already declares
  `cacheable = False` (`load_csv`, `load_json`, `load_parquet`, `load_excel`,
  `load_google_sheet`, `load_documents`, `http_fetch`, `sql_query`, `query_builder`,
  `describe_relation`, `embed_text`, `llm_call`, `llm_prompt_from_file`, `eval_run`,
  `eval_judge`).
- **Generated variable names shadowing compiler-emitted names (refuted).** `build_name_map`
  always emits `f"{node_base}_{port_slug}"`, which necessarily contains an underscore, so it
  can never collide with the emitted module's `client` / `clients` / `warehouse` / `http`
  locals, with `_results` / `_name` / `_value`, or with any Python keyword or entry in
  `_AVOID_BUILTINS` (all single words, no underscore).
- **Codegen/execute kwarg divergence (inconclusive method, no findings).** A mechanical AST
  scan comparing each node's `codegen` string-template kwargs against its `execute` call
  kwargs produced only false positives — nodes pass params via a dict/`**` expansion the
  scanner can't follow. The existing `-m equivalence` gate covers this properly and passes.

Genuinely **unproven** (not promoted to findings, would need a dedicated concurrency harness):

- `SessionStore.get()` / `.list()` (`emergentflow/collab/session.py:185`, `:176`) hand back the
  **live** `GraphSession` object outside the lock, while mutators like `accept_proposal` update
  `session.graph` and `session.version` as two separate statements under it. A reader
  serializing a session concurrently with an accept could in principle observe a new graph
  with an old version, or vice versa. Confirming this needs a deterministic interleaving
  harness; the local-single-user deployment model makes it very unlikely to bite in practice.
- `ExecutionCache._evict_to_cap` (`emergentflow/server/cache.py:135`) calls `p.stat()` on
  paths from `glob`/`iterdir` while holding only a *process-local* lock. Two server processes
  sharing the default `./.ef-cache` directory could race a file out from under the `stat`.
  Not reproduced.

## Coverage & limitations

- Optional-extra code paths were exercised only to the extent the local venv provides them
  (`rapidfuzz`, `torch`, `shap`, `pymc` etc. were not uniformly installed); 24 tests skip for
  this reason in both the baseline and post-fix runs.
- No live warehouse or LLM provider was contacted — by design, the equivalence gate and tests
  run against `ReplayClient` and fixture-recorded adapters.
- `ui/src/` was reviewed only for the Story-group-E additions (`LineagePanel`, `ReportView`,
  `PayloadView`, `Inspector`) plus the compatibility-plumbing question above; the canvas,
  session/chat, and connection-manager surfaces were last swept in the 2026-07-14 hunt and
  warrant their own pass. One transient-UX observation there was **not** promoted to a finding
  because it is cosmetic and unproven as a defect: `LineagePanel` keeps rendering the previous
  node's lineage for the `debounceMs` (400 ms) window after the selection changes, because the
  effect doesn't clear `lineage` state before the new debounced fetch fires.
- The `emergentflow/collab/` chat-runner and persona machinery (+153 lines since the last full
  hunt) was read but not exercised end to end; it needs a live agent backend to probe
  meaningfully.
- Verification ran entirely against local test fixtures and synthetic frames in the repo's own
  venv. Gates after the fixes: `ruff check` clean, `ruff format --check` clean,
  `mypy emergentflow` clean (303 files), full `pytest` suite green.
