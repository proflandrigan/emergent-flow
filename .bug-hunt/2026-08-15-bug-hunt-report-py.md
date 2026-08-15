# Bug Hunt Report: emergentflow (Python package)

- **Date:** 2026-08-15
- **Branch:** `feat/agent-onboarding-and-oom`
- **Team:** Bug-Hunt skill (Discovery → Verify → Report loop)

## Summary
- Scope reviewed: fresh sweep of `emergentflow/ml/` (post-fit estimators, grid/randomized/compare
  adapters, `optimize_threshold`), `emergentflow/recommend/` (interactions, block-wise KNN,
  metrics, evaluate), `emergentflow/timeseries/`, `emergentflow/clean/` (derive, expressions,
  sampling, impute/cast/merge/semi_join), `emergentflow/stats/` (eda, summaries), `emergentflow/data/`
  (http sheets, warehouse `query.py` + all four adapters), `emergentflow/eval/score.py`,
  `emergentflow/research/`, `emergentflow/types/compatibility.py`. Areas "just hunted" in the
  immediately-preceding 2026-08-14 pass (codegen, collab, server, mutation/cache) were not
  re-audited.
- Confirmed findings: **1 High, 1 Low.** Both reproduced end-to-end, fixed, and pinned by
  regression tests. Numerous further leads (see Notes) were reasoned through and demonstrated as
  either not bugs on the pinned dependencies or degenerate-input-only.
- Overall assessment: The package remains exceptionally healthy — the full suite (3828 passed,
  up 2 from the regression tests added here), ruff, mypy, and the ADR-0002 equivalence gate
  (331 passed) are all green. The single High is a data-integrity mislabel reachable through the
  normal warehouse query path on a 0-row result; the Low is a spurious duplicate operating point
  in `optimize_threshold`'s returned metrics curve. Both were defects, not style nits.

## Findings

### [HIGH] — Empty warehouse results mislabel every column as `nullable=False`
- **Location:** `emergentflow/data/warehouse/adapters/duckdb_adapter.py:77` (and the identical
  `bigquery_adapter.py:83`, `postgres_adapter.py:106`, `redshift_adapter.py:93`)
- **Class:** Data-integrity / state-consistency (false schema claim on an empty result)
- **Confidence:** Confirmed
- **Description:** All four adapters derive column nullability as
  `nullable=bool(df[col].isna().any())`. On a 0-row result frame, `.any()` returns `False` for
  every column, so `SELECT ... WHERE ...` over a genuinely nullable column that happens to return
  zero rows reports that column as **not nullable** — a specific, wrong schema claim. The true
  nullability of an empty result is unknowable from the frame alone; the previous behavior turned
  that unknowable case into a false negative instead of an honest "unknown".
- **Evidence / Reproduction:**
  ```python
  import duckdb, tempfile, os
  from emergentflow.data.warehouse.adapters.duckdb_adapter import DuckDBAdapter
  from emergentflow.data.warehouse.protocol import QueryRequest
  path = os.path.join(tempfile.mkdtemp(), "t.duckdb")
  con = duckdb.connect(path)
  con.execute("CREATE TABLE t (a INTEGER, s VARCHAR)")
  con.execute("INSERT INTO t VALUES (1, NULL), (2, 'x'), (NULL, 'y')")
  con.close()
  ad = DuckDBAdapter()
  res = ad.execute(QueryRequest(
      sql="SELECT a, s FROM t WHERE a > 100", dialect="duckdb", connection="c"), {"path": path})
  print(res.row_count, [(c.name, c.nullable) for c in res.columns])
  # Before the fix: 0 [('a', False), ('s', False)]  -- both are nullable columns (full table
  # reports True), so this is a wrong claim.
  # After the fix:   0 [('a', True),  ('s', True)]   -- nullability reported conservative/unknown.
  ```
  Regression test: `tests/test_warehouse_adapters.py::TestDuckDBAdapter::test_empty_result_reports_nullable_for_unknown`.
- **Impact:** Any consumer relying on the returned `QueryResult.columns` nullability (the canvas
  schema panel, downstream describe-equivalent contract, or type inference) sees a false
  `nullable=False` for nullable columns whenever a query returns no rows — the exact class of
  query (a narrow `WHERE`) that most often returns empty. Silent, under-claimed nullability can
  mislead data-profiling and schema-validation logic across all four backends.
- **Remediation:** Report `True` (unknown/conservative) when there are no rows, since an empty
  frame proves nothing; keep the true data-driven derivation for non-empty results. Applied
  identically in all four adapters:
  ```python
  nullable=bool(df[col].isna().any()) if len(df) else True,
  ```

### [LOW] — `optimize_threshold` returns a duplicate operating point in its metrics curve
- **Location:** `emergentflow/ml/__init__.py:541-577` (`optimize_threshold`)
- **Class:** Logic error / off-by-one in operating-point bookkeeping
- **Confidence:** Confirmed
- **Description:** The loop that converts `precision_recall_curve`'s output into the returned
  `metrics` table appended a synthetic "decision-threshold-0 = predict everything positive" point
  to the end of the curve. But `precision_recall_curve` **already** emits that exact operating
  point (precision = class prevalence, recall = 1.0) as its *first* returned entry (the
  minimum-threshold point, which predicts every sample positive). The result was a metrics frame
  with two identical operating points — the same `(precision, recall)` appearing at both the top
  (min threshold) and the bottom (threshold 0.0) of the returned curve — and one more row than
  there are real decision thresholds. It also shipped a stale comment that mis-attributed where
  the "predict all" point lives in sklearn's output.
- **Evidence / Reproduction:**
  ```python
  from collections import Counter
  from emergentflow.ml import optimize_threshold  # + a fitted binary FittedModel/frame
  m = res.metrics
  key = Counter((round(p, 9), round(r, 9)) for p, r in zip(m["precision"], m["recall"]))
  # Before the fix: (0.495, 1.0) occurs TWICE; len(m) == len(thresh) + 1 == 201.
  # After the fix:  no duplicate operating points; len(m) == len(thresh) == 200, and the
  #                 predict-all baseline appears once, explicitly labeled threshold 0.0.
  ```
  Regression test updated/added in `tests/test_ml_postfit.py::test_optimize_threshold_metrics_cover_full_precision_recall_curve`.
  Confirmed `best_f1`/`best_threshold` are unchanged by the fix (the appended point never
  outperformed the real curve, so removing the duplicate does not move the optimized threshold).
- **Impact:** Consumers rendering or inspecting the returned `metrics` DataFrame (e.g. a canvas
  precision-recall curve, or code that keys on operating points) would count two identical
  "predict everything positive" rows and one spurious extra point. Purely cosmetic to the
  topology of a curve, hence Low, but it also encoded a wrong mental model of sklearn's layout
  that made the bug non-obvious.
- **Remediation:** Emit exactly one row per real decision threshold, label sklearn's already-present
  first (min-threshold) predict-all point with the canonical threshold `0.0`, and drop the synthetic
  trailing "predict nothing positive" point (precision=1, recall=0, no threshold, no useful F1):
  ```python
  for i, (p, r) in enumerate(zip(prec, rec, strict=True)):
      if i < n_thresh:
          t = 0.0 if i == 0 else float(thresh[i])
      else:
          continue  # sklearn's trailing "predict nothing positive" point; drop it
      f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
      rows.append((t, float(p), float(r), f1))
  ```

## Notes & unverified leads
- **`ml.evaluate` `roc_auc` default `pos_label` (refuted for current sklearn).** Hypothesized the
  `roc_auc_score(y_true, proba[:, 1])` call (default `pos_label`) could invert or drop the metric
  for string / disjoint-integer class labels, since the sibling precision/recall/f1 use
  `classes[1]`. Verified empirically on string labels (`['neg','pos']`) and disjoint-int labels
  (`[1, 2]`): the pinned sklearn (1.9.0) removed `pos_label` from `roc_auc_score` and scores
  `proba[:,1]` (the `classes_[1]` column) consistently; a manual Mann-Whitney AUC matched the
  reported value exactly. Not a bug on the pinned dependency; re-check if the sklearn pin is
  bumped.
- **`ml.grid_search`/`tune_model`/`cross_validate` treat `cv`/`scoring` as pass-through
  (reasoned, not promoted).** No allow-list validation on `cv` (an `int` is assumed) or
  `scoring` beyond sklearn's own validation, so an invalid value surfaces a raw sklearn error
  rather than a typed one. Needs non-default user input and is redundant with sklearn's own
  messages; Low, left for a params-validation-focused pass.
- **Warehouse `_inject_limit` with negative `max_rows` (demonstrated reachable, not promoted).**
  `_inject_limit` renders `LIMIT max_rows + 1` with no lower-bound guard, so a caller-supplied
  negative `max_rows` produces `LIMIT 0`/a negative literal and breaks; `max_rows=0` works
  (returns 0 rows). Requires abnormal negative input the UI/nodes never produce; Low, noted in the
  prior 2026-08-14 hunt too — a candidate for a shared params-validation guard.
- **`optimize_threshold` uses `precision_recall_curve(..., pos_label=...)` while `roc_auc`
  dropped `pos_label` (consistency note, not a defect).** `precision_recall_curve` still accepts
  `pos_label` on this pin; no issue observed. Just flagging the API drift for a future pin bump.

## Coverage & limitations
- Deep-dive verified and fixed: warehouse adapters' empty-result `nullable` (DuckDB + all three
  cloud siblings), `ml.optimize_threshold` operating-point duplication.
- Fresh sweeps (leads only) across `ml` post-fit adapters, `recommend` (interactions, block-wise
  KNN similarity, metrics, `evaluate`/`_bounded_diversity`), `timeseries`, `clean` (derive,
  expressions, sampling, merge/semi_join, impute/cast, explode_lists), `stats` (eda, summaries),
  `data/http` sheets, `eval/score`, `research`, `types/compatibility`.
- Not re-audited (covered by the immediately-preceding 2026-08-13/14 hunts): `collab/`, `codegen/`,
  `server/`, `clean/outliers`. The `ui/` canvas is out of scope for this Python-package hunt.
- Gates: full suite **3828 passed, 103 skipped** (2 new regression tests); `ruff check`/`format`
  clean; `mypy` clean (349 source files); ADR-0002 equivalence gate **331 passed**. No `@public_op`
  signatures, IR models, or node `spec` changed, so no `export_ui_contracts`/boundary churn was
  required.
