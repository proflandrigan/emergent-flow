# Bug Hunt Report: emergentflow core SDK (Aug 2, 2026)

## Summary
- Scope reviewed: `emergentflow/` core on `main` at `4adfef3` — the IR + codegen/executor core (compiler, executor, validation, params, naming, wiring, traversal, declarative, inspect, export), the local server (`app.py`, `service.py`, `cache.py`, `artifacts.py`, `flows.py`, `runs.py`, `payload.py`), data ingest + warehouse seam (`data/__init__.py`, `warehouse/*`, `http/*`, `documents.py`), the LLM seam (`llm/*`), stats, timeseries, eval, ml, recommend, clean, explain, viz, research, collab (session, chat_runner, knowledge, consult), script, connections, and cli. The `ui/` canvas and docs prose were not reviewed.
- Confirmed findings: 2 Medium.
- Baseline: existing suite green (`tests/test_warehouse_spec_compiler.py` 15 passed); every finding below is a behavior not covered by the existing tests. Both findings reproduced with minimal local fixtures (no real data, no network).

Overall assessment: the codebase is remarkably disciplined — heavy input validation, typed errors, collision guards, and the ADR-0002 dual-path pattern hold up throughout. The two confirmed defects are cross-feature interaction bugs: (1) the visual query builder's CROSS-join option compiles to SQL that every backend rejects (the `ON` clause is unconditionally emitted even though CROSS joins cannot carry one), and (2) the agent-mutation protocol (`apply_mutation.set_params`) silently destroys graph-parameter `ref` wiring (and `description`) on any node param it touches, because it rebuilds `Param` objects field-by-field instead of copying. Both are reachable from normal product flows and neither is covered by a test.

## Findings

### MEDIUM — Visual query builder CROSS join compiles to invalid SQL (rejected by every backend)
- **Location:** `emergentflow/data/warehouse/spec_compiler.py:245-261` (the join loop in `compile_spec`), via `_build_join` at `spec_compiler.py:172-198`
- **Class:** Logic error / invalid output on a reachable configuration
- **Confidence:** Confirmed
- **Description:** `_build_join` unconditionally builds an `ON` condition from the spec's `on` list, and `compile_spec`'s join loop always passes it to `select_node.join(..., on=on_cond, join_type="CROSS")`. SQL forbids an `ON` clause on a `CROSS JOIN`. So any spec with a CROSS join — the join type is a first-class option of the `data.query_builder` node (`type="CROSS"` handled at `spec_compiler.py:256-258`) — compiles to `... FROM a CROSS JOIN b ON <cond> ...`, which DuckDB (and every other dialect) rejects with a parser error. The CROSS option is therefore unusable end-to-end: it cannot produce runnable SQL at all.
- **Evidence / Reproduction:** `repro_cross_join.py`:
  - `compile_spec({"source":"sales","select":["revenue"],"join":[{"relation":"regions","on":[{"left":"sales.region_id","right":"regions.id"}],"type":"CROSS"}]}, "duckdb")`
    → `SELECT revenue FROM sales CROSS JOIN regions ON sales.region_id = regions.id`
  - Running that SQL against a real DuckDB raises `ParserException: Parser Error: syntax error at or near "ON"`.
  - The identical spec with `"type": "INNER"` compiles to `SELECT revenue FROM sales JOIN regions ON sales.region_id = regions.id` and runs fine — confirming the bug is specific to the CROSS branch (the `on` must be dropped for CROSS).
- **Impact:** A user who picks the "CROSS" join type in the query builder (or hand-writes such a spec) gets a broken query on every execution path — `ef.execute`, the compiled module, the live SQL preview, and the server — with a confusing parser error rather than a clear "CROSS joins don't take ON conditions" message. CROSS joins are a legitimate, documented option, so this is a functional bug, not a misfeature.
- **Remediation:** In `compile_spec`'s join loop, do not pass `on` when the join type is CROSS:

  ```python
  table_expr, on_cond = _build_join(join_spec)
  join_type = join_spec.get("type", "INNER").upper()
  join_kwargs: dict[str, Any] = {}
  if join_type == "CROSS":
      join_kwargs["join_type"] = "CROSS"
  elif join_type in ("LEFT", "RIGHT", "FULL"):
      join_kwargs["join_type"] = join_type
      join_kwargs["on"] = on_cond
  else:  # INNER (default) and any unrecognized value keep the ON condition
      join_kwargs["on"] = on_cond
  select_node = select_node.join(table_expr, **join_kwargs)
  ```

  Consider also relaxing `_build_join` so a CROSS join does not *require* an `on` list (CROSS joins legitimately have no join key); the minimal fix above already makes the CROSS path emit valid SQL when `on` is present.

### MEDIUM — `apply_mutation.set_params` silently destroys graph-param `ref` (and `description`) wiring
- **Location:** `emergentflow/ir/mutation.py:171-183` (the `set_params` param-rebuild loop)
- **Class:** State corruption / silent data loss on a cross-feature interaction (issue #116 refs)
- **Confidence:** Confirmed
- **Description:** `apply_mutation`'s `set_params` handling replaces a matching `Param` by constructing a fresh `Param(name, type_token, value, default)` — deliberately omitting `ref` and `description`. Before issue #116 this was harmless (those fields didn't exist); now, any node param that is ref'd to a graph-level parameter loses its `ref` the moment an agent proposes a `set_params` value update. The graph-param wiring the human configured is silently severed, and the node starts using the literal value (or, if the mutation is later re-proposed, the whole graph-param override no longer reaches that node). The same applies to `description`, which is also dropped. The value-update path is reachable from the two agent surfaces: `consult.py`'s Mode-B consult returns a `set_params`-only `GraphMutation` (`consult.py:134-138`), and the in-app chat agent proposes `set_params` mutations.
- **Evidence / Reproduction:** `repro_mutation_ref.py` — a node with `Param(name="value", type_token="int", value=999, default=999, ref="p", description="d")`, then `apply_mutation(g, GraphMutation(base_version=0, set_params={node.id: {"value": 42}}))`:
  - Before: `[('value', 'p', 'd')]`
  - After: `[('value', None, None)]` — `ref` and `description` are gone.
  - Executing the mutated graph would bake `42` in as a literal and ignore the graph parameter `p` that the author wired, with no diagnostic.
- **Impact:** An agent-assisted edit (chat or one-shot consult) on a graph that uses graph-level flow parameters silently breaks the parameter wiring. Because `propose_diagnostics` validates the *mutated* graph and `ref_unresolved`/`ref_type_mismatch` only fire when a `ref` is present, the corruption is silent: the mutation applies cleanly and the graph runs, just with the wrong (literal) value. Users get different results from the same graph depending on whether an agent touched a ref'd param.
- **Remediation:** Preserve the existing `Param`'s untouched fields by copying instead of rebuilding:

  ```python
  for p in existing_params:
      if p.name in param_updates:
          updated_params.append(p.model_copy(update={"value": param_updates[p.name]}))
          updated_param_names.add(p.name)
      else:
          updated_params.append(p)
  ```

  This keeps `ref`/`description`/`type_token`/`default` intact while updating only the value — `set_params` stays a *partial* value update as documented ("An agent never has to reconstruct a full `Param` object ... only the new value"). Note this also means the hints check in `apply_mutation` now runs against the value the node will actually use at resolve time only if the ref is absent; if preserving refs for ref'd params is deemed wrong (the agent's value would be ignored by `materialize_graph`), a deliberate, explicit un-ref would need its own mutation key — silently dropping the ref is the one behavior that is never correct.

## Notes & unverified leads
- **`ef.stats.test_proportions` counts NaN `success_col` rows into `n` but not into `count`** (`stats/__init__.py:575-581`): the validation at `:573` explicitly allows NaN in `success_col` (it checks `df[success_col].dropna().isin(...)`), but `n_a = a.shape[0]` counts the NaN rows while `count_a = a.sum()` skips them — so a column containing NaN silently deflates the observed proportions. Unproven as a *reported* defect only because the docs say "must contain only 0/1/True/False values" (which NaN technically is not); flagged for a decision between rejecting NaN up front or dropping those rows consistently.
- **`apply_mutation` cascade-position index double-increment** (`mutation.py:141-146`): `_next_cascade_position` returns the index it consumed after skipping collisions, and the caller then does `cascade_index += 1` again. Traced carefully, the resulting positions never overlap, so this is merely a slightly larger-than-necessary step — not a bug.
- **Server `/examples` and `/flows` slug/path guards**: `_static_file` and `get_example` both use `is_relative_to` checks, and `flows.py` `_SLUG_RE` blocks traversal. Prior hunts already verified the `rename` traversal fix; re-read and confirmed no regression.
- **`data.http_fetch` offset pagination** (`fetch.py:196`): first page uses `offset=0` which is correct; page counting is standard. No issue found.
- **Composite-subgraph param *value* diagnostics still do not recurse** into subgraphs (`validation.py:_collect_param_diagnostics`), so a composite subgraph node with an invalid literal param value slips past `ef.validate`. This predates this hunt (noted in the PR-146 report) and is a behavior-change risk to scope separately; not re-reported as a new finding.

## Coverage & limitations
- Reviewed every `emergentflow/` Python module except the per-node example catalog entries in depth (spot-checked representative nodes across data/clean/ml/stats/recommend/viz/llm) and the `reports/` family (imports `ydata_profiling`, exercised only via existing tests). The `ui/` canvas, `docs/`, `epics/`, and `scripts/` were out of scope.
- No network access, no live cloud warehouse, no production data. Warehouse repros used in-process DuckDB; LLM/HTTP seams were verified only structurally.
- The full suite was not re-run (existing targeted suites green); a broad `pytest -m "not integration"` is advisable after the fixes below.

## Fixes applied (this session)
Both confirmed findings were fixed on a branch, verified by new regression tests:

- **Finding 1:** `compile_spec` no longer emits an `ON` condition for CROSS joins (`spec_compiler.py` join loop). Verified: the CROSS-join spec now compiles to `SELECT revenue FROM sales CROSS JOIN regions ...` (no `ON`), runs on DuckDB, and the INNER/LEFT/RIGHT/FULL paths are unchanged.
- **Finding 2:** `apply_mutation.set_params` now uses `p.model_copy(update={"value": ...})`, preserving `ref`/`description`/`type_token`/`default`. Verified: the ref'd param keeps `ref="p"` after the mutation.

New regression tests: `test_cross_join_compiles_without_on` (in `tests/test_warehouse_spec_compiler.py` / the spec-compiler test module) and a `set_params` ref-preservation test in the mutation test module.
