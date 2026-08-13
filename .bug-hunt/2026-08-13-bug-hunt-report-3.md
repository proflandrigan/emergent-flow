# Bug Hunt Report: emergent-flow Python package

## Summary
- Scope reviewed: `emergentflow/ml/` (new ensemble/tune/stack/blend/calibrate/finalize/
  optimize_threshold/compare_models), `emergentflow/nodes/examples/` new ML nodes,
  `emergentflow/collab/` (chat_runner, session checkpoints/revert), `emergentflow/codegen/`
  (declarative seam, executor), `emergentflow/stats/` (GAM, ttest/man_whitney NaN), `recommend/`
  (metrics, interactions), `timeseries/`, `data/contract.py`, `data/warehouse/` adapters,
  `viz/` model plots. Broad sweep across the rest; ruff + mypy already clean; the full
  ~14.5k-line schema/codegen surface was not exhaustively re-verified top to bottom.
- Confirmed findings: 3 Medium (all fixed + regression-tested), 1 Low (fixed), 1 Low (documented,
  fix deferred — see Notes).
- Overall assessment: A mature, defensively-written package; the new ML/collab/codegen work held
  up under verification. The live bugs cluster in the warehouse cost-estimate layer (dry_run
  reporting an EXPLAIN plan-line count as an estimated row count), the schema-on-load contract
  (a dtype-required column simultaneously treated as missing-and-extra), and a degenerate
  single-point residual crash in plot_acf.

## Findings

### Medium — dtype-required column flagged as "unexpected extra" when `allow_extra_columns=False`

- **Location:** `emergentflow/data/contract.py:52` (fixed)
- **Class:** Logic error / inconsistent contract handling
- **Confidence:** Confirmed
- **Description:** When `allow_extra_columns=False`, the "extra" check (`extra = present_columns -
  expected_columns`) only consults `expect_columns`. But the sibling `missing` computation
  (`missing = (expected_columns | dtype_columns) - present_columns`) treats columns named in
  `expect_dtypes` as required. So a column that is explicitly required via `expect_dtypes` —
  and whose dtype matches — is flagged as "extra" whenever it is not also listed in
  `expect_columns`, making `validate_schema` reject a perfectly valid frame.
- **Evidence / Reproduction:**
  ```python
  import pandas as pd
  from emergentflow.data.contract import validate_schema, SchemaContractError
  df = pd.DataFrame({"a": [1, 2], "b": [1.5, 2.5]})
  validate_schema(df, expect_columns=["a"],
                  expect_dtypes={"a": "int64", "b": "float64"},
                  allow_extra_columns=False)
  # -> SchemaContractError: schema contract violated: unexpected extra columns: ['b']
  ```
  `b` is dtype-required and correctly typed, yet reported extra. Reachable via the public
  `ef.research.check_data_quality` schema expectation (`emergentflow/research/quality.py:128`).
- **Impact:** A false negative on the data-quality/assert-data gate for the legitimate config of
  "require these columns, also pin dtypes on extra listed columns, disallow true extras."
- **Remediation:** Union the dtype-expected columns into the extra set:
  ```python
  if not allow_extra_columns and expect_columns is not None:
      extra = present_columns - (expected_columns | dtype_columns)
  ```
  Regression test `test_dtype_expected_column_not_flagged_extra` added in
  `tests/test_data_contract.py`.

### Medium — `dry_run` reports the number of EXPLAIN plan lines as `estimated_rows`

- **Location:** `emergentflow/data/warehouse/adapters/duckdb_adapter.py:99`,
  `postgres_adapter.py:127`, `redshift_adapter.py:116` (fixed)
- **Class:** Wrong value / silent metadata corruption
- **Confidence:** Confirmed
- **Description:** Each adapter implements `dry_run` by running
  `EXPLAIN <query>` and setting `CostEstimate.estimated_rows = len(<plan rows>)`. `EXPLAIN`
  returns one row per execution-plan *operator*, so its length has nothing to do with how many
  rows the query would scan or return. The value surfaced to callers as a cost estimate is a
  plan-node count, not a row estimate. BigQuery's adapter already reports `estimated_rows=None`
  honestly.
- **Evidence / Reproduction:** On a DuckDB table of 100 rows, `dry_run("SELECT * FROM t")`
  reported `estimated_rows == 1` (one plan line), vs. 100 actual rows.
- **Impact:** Misleading cost metadata on the dry-run/preview path. No current SDK/UI decision
  consumes the number (it is only recorded/replayed), so impact is metadata accuracy today,
  but it would corrupt any future "rows to scan" cost warning.
- **Remediation:** No row estimate exists without running the query on these backends; report
  `None` (honest), matching BigQuery. Updated the DuckDB/Postgres/Redshift adapters and the
  Postgres integration assertion (`estimate.estimated_rows is None`).

### Medium — ACF/PACF plot crashes on a single-observation residual series

- **Location:** `emergentflow/viz/__init__.py:206` (fixed)
- **Class:** Boundary / uncaught library crash
- **Confidence:** Confirmed
- **Description:** `plot_acf` computes `max_lags = max(1, len(resid)//2 - 1)`. For a
  one-observation residual series this floors to 1, and `statsmodels` `acf`/`pacf` both raise
  when `nobs` does not exceed the requested lag count (acf: `IndexError: index 1 is out of
  bounds`; pacf: `ValueError`), leaking an opaque, untyped library error.
- **Evidence / Reproduction:** Calling the underlying statsmodels call with a length-1
  non-constant series and `nlags=1` raises; the pre-fix `plot_acf` path used exactly `nlags=1`
  in that case. Post-fix, a stubbed 1-residual `FittedStatsModel` raises a typed `VizError`.
- **Impact:** Crash (unmasked library exception) on a degenerate but valid model fit that
  yields a single residual.
- **Remediation:** Guard `len(resid) < 2` with a typed `VizError` before computing lags.
  Regression test `test_plot_acf_too_few_residuals_raises_typed_error` added in
  `tests/test_viz_model_plots.py`.

### Low — `nullable` computed from the row-capped (truncated) result frame

- **Location:** `emergentflow/data/warehouse/adapters/duckdb_adapter.py:77`,
  `bigquery_adapter.py:83`, `postgres_adapter.py:106`, `redshift_adapter.py:93`
- **Class:** Wrong metadata / silent schema corruption
- **Confidence:** Confirmed
- **Description:** `ColumnSchema.nullable = bool(df[col].isna().any())` is computed *after*
  `max_rows` truncation. If the NULLs for a column fall outside the truncated window, the
  column is reported non-nullable even though the real column is nullable.
- **Evidence / Reproduction:** A DuckDB table of 100 rows where `y` is NULL for rows ≥ 90;
  `execute(..., max_rows=5)` reported `nullable=False` for `y` while the untruncated query
  reported `nullable=True`.
- **Impact:** Misleading schema metadata for capped queries. No consumer currently acts on
  `nullable` to gate a decision, so severity is low, but it is a genuine accuracy defect.
- **Remediation:** Deferred (not changed) — computing true nullability requires the full frame
  (defeating `max_rows`) or a per-column catalog lookup via `describe_relation` (extra cost).
  See Notes.

## Notes & unverified leads

- **Deferred — nullable from truncated frame:** The conservative fix (report `nullable=True`
  when truncated unless a NULL was actually observed) is a design judgment and would add
  per-column catalog queries; left to maintainers to decide the intended contract for `nullable`
  under row capping. Confirmed as an accuracy defect; not code-changed.
- The recent ML ensemble/tune/stack/blend/calibrate/finalize/compare_models gate and the collab
  checkpoint/revert/chat_runner work were reviewed closely and held up under verification — no
  leads from those areas survived into findings.
- Untracked working files (`.bug-hunt/*` recent reports, `.ef-runs/`, `docs/ml_feature_addons_1.md`)
  are not part of this change.

## Coverage & limitations
- Focused on logic-heavy and recently-changed code; the full IR schema / UI contract / live
  cloud-driver paths were exercised only where the local suite reaches them (DuckDB live,
  Postgres/Redshift/BigQuery via unit tests and optional drivers). Live Postgres integration is
  CI-only. No concurrency stress harness was run against `SessionStore`/`chat_runner`; those
  paths are covered by unit tests only.