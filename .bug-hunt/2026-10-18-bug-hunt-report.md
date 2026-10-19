# Bug Hunt Report: emergent-flow (entire codebase)

## Summary
- Scope reviewed: `emergentflow/` (all packages) and `ui/src/`, split across seven parallel hunters by area. Read depth varied by area; see Coverage.
- Confirmed findings: 1 High, roughly a dozen and a half Medium and Low (grouped below; all fixed, each with a regression test).
- Verified with the full gates on the combined tree: ruff, ruff format, mypy, UI boundary check, pytest (4112 passed excluding the live-Postgres and psycopg-installed tests), UI lint, typecheck, vitest (987 passed).

## Findings

### HIGH — Path traversal via node id in ArtifactStore
- **Location:** `emergentflow/server/artifacts.py` (`_pkl_path`/`_meta_path`)
- **Class:** Path traversal
- **Confidence:** Confirmed
- **Evidence:** `put("../../escaped", ...)` wrote files outside the store root; regression test `test_artifact_store_node_id_cannot_escape_root`.
- **Remediation (applied):** `_safe_key` hashes any non-slug id with sha256.

### MEDIUM
- **Read-only SQL gate bypass** (`data/warehouse/query.py`): `SELECT ... INTO` and data-modifying CTEs passed `read_only=True`. Fixed by rejecting write nodes anywhere in the parse tree.
- **Schema-qualified names** (`data/warehouse/spec_compiler.py`): `main.sales` compiled to one quoted identifier. Now split into parts.
- **`detect_outliers(by=...)` duplicate index** (`clean/outliers.py`): `ValueError` on non-unique index. Now uses positional labels.
- **Composite subgraph var shadows outer param** (`codegen/compiler.py`, `naming.py`): compiled `main()` raised `UnboundLocalError` while `execute` worked (ADR-0002).
- **Empty-string params diverge between execute/codegen** (`nodes/examples/outlier_summary.py`, `save_frame.py`, `detect_outliers.py`): fixed with `or None`.
- **`ml.train_test_split` temporal** (`ml/__init__.py`): float truncation gave the test side extra rows (10 rows, `test_size=0.8` gave 9 test rows).
- **`ml.evaluate` string labels** (`ml/__init__.py`): `average_precision`, `brier`, `positive_rate` silently dropped. `tests/test_ml.py` had encoded the buggy key set and was updated.
- **`correct_pvalues` with NaN** (`stats/__init__.py`): BH made all adjusted p-values NaN; Bonferroni miscounted m.
- **Cluster-robust covariance with missing rows** (`stats/catalog.py`): crashed for OLS/WLS/GLS/GLM.
- **Half-applied mutation on invalid author** (`collab/session.py`): 422 returned after state change.
- **Budget gate approval never worked** (`collab/budget_gate.py`): closed gate opened a fresh one on the next execute.
- **connections.toml non-atomic write and unlocked read-modify-write** (`connections/profiles.py`, `server/service.py`): profile loss under failure or concurrency.
- (Evidence for all: reproduced before the fix, regression test added; see the test files listed below.)

### LOW
- `cohort_retention` crashed on missing user/date (`stats/__init__.py`).
- Loaders treated literal paths containing `[ ? *` as globs (`data/__init__.py`).
- Validity rules ignored `strategy="temporal"` (`validity/rules/temporal.py`, `metrics.py`).
- `KnowledgeStore.save` left a phantom entry when persist failed (`collab/knowledge.py`).
- `compare_metrics` `delta_pct` wrong sign for negative baselines (`collab/metrics.py`).
- UI: deleting a group node left members with a dangling `groupId` (`ui/src/store/graphStore.ts`) (rated Medium by the UI hunter).

Regression tests: `tests/test_budget_gate_approval.py`, `test_collab_metrics_compare.py`, `test_connections_atomic_write.py`, `test_detect_outliers_empty_by_equivalence.py`, `test_ml_split_eval_regressions.py`, `test_nodes_empty_string_params_equivalence.py`, `test_stats_hunt_regressions.py`, `ui/src/store/graphStore.removeGroup.test.ts`, plus additions to existing test files.

## Notes & unverified leads
- `chat_runner.py`: turn can strand in RUNNING if the session is deleted mid-start; subprocess not reaped on reader exception; stderr read after stdout EOF.
- Bearer-token comparison uses `!=` (not constant-time); not demonstrable.
- `ndcg_at_k` ideal DCG uses `min(len(relevant), n_positions)`; documented choice.
- `cross_validate(cv_strategy="temporal")` relies on pre-sorted rows.
- `forecast_arima` crashes if `order` is explicitly None (same on both paths).
- `script.custom_code` execute/codegen differ if `transform` is defined twice.
- `apply_mutation` `set_params` on a param with a graph-param `ref` is overwritten by `materialize_graph`.
- Several NaN-handling edge cases (`bootstrap_ci` group NaN, `_vif`, `research/quality.py`) are debatable semantics.

## Coverage & limitations
- Not read in depth: `data/http/*`, postgres/redshift/bigquery adapters, `viz_*` and most `recommend_*` nodes, ALS/BPR/NCF/two-tower code, `ml` pipeline/feature-transform helpers.
- `tests/test_warehouse_adapters.py::TestPostgresMissingDriver` fails only where `psycopg` is installed (environment artifact, not a product bug).
- Some regression tests were not re-run against the unfixed code (agents were told not to touch git); failures were reproduced with scratch repros before the fixes.
- Process note: two hunters ran `git stash` and popped it immediately; no edits were lost (full gates pass on the combined tree). The pre-existing `stash@{0}` was left untouched.
