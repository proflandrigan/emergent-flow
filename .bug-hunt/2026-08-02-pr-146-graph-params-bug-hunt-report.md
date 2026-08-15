# Bug Hunt Report: PR #146 — graph-level flow parameters (issue #116)

## Summary
- Scope reviewed: all Python changes in PR #146 (`feature/graph-params-116`) — IR models
  (`Graph.params`, `Param.ref`/`description`), the v1→v2 migration, ref resolution/materialization
  (`codegen/params.py`), validation diagnostics (`codegen/validation.py`), compiler/codegen
  (`compiler.py`, `context.py`, `naming.py`), executor (`executor.py`), the CLI `--param`, the
  server `/execute`/`/execute_node`/`/execute/stream`, reproducibility capture, the reference nodes
  (`data.load_csv`, `data.sql_query`), and the UI components/tests.
- Confirmed findings: 3 Medium.
- Overall assessment: The feature is well-tested and the core resolve/materialize path is sound,
  but three inconsistencies let graph-param refs behave differently across the entry points the
  PR claims are equivalent: composite-subgraph refs bypass the shared validation gate entirely
  (compile and execute then fail with *different* errors, and a mistyped ref silently bakes a
  wrong-typed value); the server's single-node `/execute_node` path ignores refs and runs the
  node with its stale literal; and `ef.execute` accepts an override value that violates a ref'd
  node param's own declared contract, which the server's FUNCTIONAL walk rejects. All three are
  now fixed and covered by regression tests; the full suite (3564 passed), the ADR-0002
  equivalence gate (333 passed), ruff, and mypy are green.

## Findings

### MEDIUM — Composite-subgraph graph-param refs bypass the validation gate
- **Location:** `emergentflow/codegen/validation.py:251` (`_collect_param_ref_diagnostics`)
- **Class:** Missing validation / compile↔execute divergence (ADR 0002 equivalence)
- **Confidence:** Confirmed
- **Description:** `_collect_param_ref_diagnostics` only iterates top-level `graph.nodes`; it
  never recurses into a `layout.composite` node's `subgraph`. The PR explicitly supports refs
  inside composite subgraphs (they resolve against the enclosing graph's params — see the
  reviewer-pass test `test_composite_subgraph_ref_resolves_against_outer_params`), but the
  shared gate that is supposed to surface `ref_unresolved` / `ref_type_mismatch` /
  `ref_not_supported` diagnostics never sees them. The three entry points then diverge:
  `validate` reports *nothing*, `compile_to_code` raises a raw `KeyError` (from
  `_param_expr_refs` in `compiler.py`), and `execute` raises a `GraphParamError` (from
  `_resolve_node_params` in `params.py`). A mistyped ref (e.g. a `str` graph param feeding an
  `int` node param) passes validation entirely and silently bakes the wrong-typed value.
- **Evidence / Reproduction:** `repro_subgraph_refs.py` builds a composite whose subgraph sink
  has `ref="missing"` with no graph params:
  - `validate(g).diagnostics` → `[]` (no diagnostics at all).
  - `compile_to_code(g)` → `KeyError: 'missing'`.
  - `execute(g)` → `GraphParamError: node 'sink' param 'value' references graph parameter
    'missing' which is not defined`.
  With a `str` graph param feeding the `int` sink param: `validate` returns `[]` and
  `execute(g)["comp"]` returns `{'out': 'not-an-int'}` — a silently wrong-typed result where
  the top-level equivalent is a `ref_type_mismatch` error.
- **Impact:** Any graph that puts a ref inside a composite's subgraph loses all ref validation.
  Unresolved refs produce an opaque `KeyError` on compile, and mistyped refs can silently
  produce wrong-typed data. Violates the PR's stated invariant that "unresolved/mistyped refs
  surface as validation diagnostics" and that compile and execute reject identically.
- **Remediation:** Make `_collect_param_ref_diagnostics` recurse into `node.subgraph`, checking
  every ref at every nesting level against the **top** graph's `params` map (matching
  `materialize_graph` and `_codegen_composite`, which both resolve subgraph refs against the
  enclosing graph's params). Also convert `_param_expr_refs`'s bare `KeyError` into a proper
  `CodegenError` so a direct `_assemble` call on an unvalidated graph fails cleanly. Both done;
  verified: `validate` now reports `ref_unresolved`/`ref_type_mismatch`, and both
  `compile_to_code` and `execute` reject with the same `GraphValidationError`.

### MEDIUM — Server `/execute_node` ignores graph-param refs and runs the node's stale literal
- **Location:** `emergentflow/server/service.py:1185` (`execute_node`)
- **Class:** Wrong value / ref not resolved
- **Confidence:** Confirmed
- **Description:** `execute_node` (the canvas's "run this node") deserializes the graph and runs
  the single node's `execute()` directly, never calling `materialize_graph`. For a node whose
  param carries a `ref`, the literal `value` on the node is intentionally ignored during a full
  graph run (the graph param's resolved value is baked in instead), so `run this node` silently
  executes with that stale literal — disagreeing with the same node inside a full graph run.
- **Evidence / Reproduction:** `repro_execute_node.py` — a `test.sink` node with
  `value=999, ref="p"` and a graph param `p` with value `42`:
  - Full graph run: `execute(g)["n"] == {'out': 42}`.
  - `/execute_node` envelope `{"graph": ..., "run_node": "n"}` → result payload `{'out': 999}` —
    the stale literal, not the resolved graph param.
- **Impact:** The canvas's "Run this node" produces results that differ from "Execute" for any
  ref'd node, silently. Users can get different answers from the two buttons for the same graph.
- **Remediation:** Materialize the graph before extracting the node when any node carries a ref:
  `if has_graph_param_refs(graph): graph = materialize_graph(graph)` after `_to_graph`. Done;
  verified `execute_node` now returns the resolved value (`42`).

### MEDIUM — `ef.execute` accepts an override that violates a ref'd node param's contract; the server rejects it
- **Location:** `emergentflow/codegen/executor.py:131` (`execute`)
- **Class:** SDK↔server inconsistency / error handling
- **Confidence:** Confirmed
- **Description:** `execute` gates the *original* graph, then materializes refs/overrides into a
  deep copy and runs it **without re-gating**. An override value that violates a ref'd node
  param's own declared contract (e.g. `dialect`'s `choices`) therefore flows straight through.
  The server's FUNCTIONAL walk (`_execute_functional_stream`) does re-gate the materialized
  graph, so the same request over the canvas is a 422. Same input, different verdict.
- **Evidence / Reproduction:** `repro_asymmetry2.py` — a `test.choice_sink` node with
  `hints=ValidationHints(choices=["a","b","c"], ref_supported=True)` ref'd to graph param `p`
  (`value="a"`), overridden with `"z"`:
  - `validate(materialize_graph(g, params={"p":"z"}))` → `['param_invalid']`.
  - `ef.execute(g, params={"p": "z"})` → returns `{'n': {'out': 'z'}}` (no error).
  - `execute_graph({"graph": ..., "params": {"p": "z"}})` → `GraphValidationError` (422).
- **Impact:** SDK programmatic runs silently produce output the canvas would refuse; a value the
  node's own contract forbids escapes validation on the SDK path.
- **Remediation:** After materializing, run the shared gate on the materialized copy so `execute`
  accepts/rejects the same graphs the server does. `validate_param_values` skips `None` and refs
  are re-checked against the same map, so a graph that passed the first gate only newly-fails
  when an override value is genuinely invalid for the node it feeds. Done; verified `execute`
  now raises `GraphValidationError` (`param_invalid`) for the out-of-choices override while
  passing the valid default.

## Notes & unverified leads

- **`_collect_param_diagnostics` still does not recurse into composite subgraphs** — a composite
  subgraph node whose *literal* param value violates its own constraints still slips past the
  gate. This predates PR #146 (subgraph support landed earlier), and I scoped the fix to ref
  diagnostics; recursing param-value diagnostics would be a behavior change for existing
  composite graphs and needs its own review.
- **Server `/execute` does not type-coerce override values** (the CLI's `_coerce_param_value`
  does): `--param p=abc` for an `int` graph param is rejected by the CLI, but a raw
  `{"params": {"p": "abc"}}` over HTTP bakes a string. With the re-gate fix this is now caught
  only when the fed node param has constraints; otherwise it flows through. Coercing on the
  server would make the two transports agree.
- **`compile_to_code(graph)` cannot validate override values** (it has no override concept), so
  an override-invalid graph "compiles" while `execute(graph, params=...)` now rejects. This is
  inherent to the design; the equivalence harness binds overrides as module-scope variables and
  bypasses the gate, so no equivalence test is affected.
- **Subgraph refs always resolve against the top graph's params** — a composite whose *subgraph*
  declares its own `params` map cannot reference those from within; both compile and execute
  error (differently: `CodegenError` vs `GraphParamError`). Documented nowhere; a validation
  diagnostic would be friendlier.
- **UI**: the "run params" override form renders a text input for every type, so a `bool` param
  only yields `true` on the exact lowercase string `"true"` (case-sensitive, `"1"`/`"True"`
  → `false`), and an `int` value like `10.5` is silently `Math.round`ed. Cosmetic/edge; not
  fixed.

## Coverage & limitations
- Reviewed every Python file in the PR diff plus the UI components and their tests. The two
  reference nodes, the compiler's `main(*, param=...)` emission, the migration, the CLI coercion,
  and the reproducibility capture were exercised via the existing test suite rather than
  line-by-line proofs.
- The live-Postgres driver-integration CI job was not run; `pytest -m "not integration"` and
  `pytest -m equivalence` were run locally and are green (3564 passed / 62 skipped; 333 passed).
- UI files were not modified, so the UI gates were not re-run; they were green on the branch.
