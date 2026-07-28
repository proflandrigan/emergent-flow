# Bug Hunt Report: ML tools suite (`emergentflow/ml/` + `ml.*` reference nodes)

## Summary
- Scope reviewed: `emergentflow/ml/__init__.py` (all 12 public ops: `evaluate`, `summarize`,
  `train_classifier`, `train_regressor`, `train_random_forest`, `predict`, `train_test_split`,
  `fit_estimator`, `fit_transform`, `select_features`, `fit_pipeline`, `grid_search`,
  `cross_validate`, `compare_models`, `apply_estimator`, `fit_and_label`),
  `emergentflow/ml/registry.py`, `emergentflow/ml/catalog.py` (the full curated estimator
  allow-list), `emergentflow/ml/summaries.py`, `emergentflow/ml/generator.py`, and every
  `ml.*` reference node in `emergentflow/nodes/examples/` (`fit_estimator`, `apply_estimator`,
  `predict`, `train`, `train_random_forest`, `train_regressor`, `transform`, `fit_transform`,
  `pipeline`, `cross_validate`, `grid_search`, `compare_models`, `evaluate`, `select_features`,
  `cluster_detect`).
- Confirmed findings: 1 High.
- The reference-node layer is uniformly mechanical (`codegen` and `execute` both call the exact
  same `emergentflow.ml.*` function with the exact same arguments), so ADR-0002 equivalence
  holds by construction there and no divergence was found. The one confirmed bug is a plain
  correctness defect in the shared business logic itself (`emergentflow/ml/__init__.py`),
  affecting both `execute()` and compiled code identically since both route through the same
  function.

## Findings

### High — `ef.ml.predict()` silently overwrites a real, pre-existing `prediction` column
- **Location:** `emergentflow/ml/__init__.py:349-360` (the `predict()` public op, backing the
  `ml.predict` node)
- **Class:** Logic error / missing guard (inconsistent with sibling function)
- **Confidence:** Confirmed
- **Description:** `predict()` unconditionally does `result["prediction"] = model.estimator.predict(...)`
  with no check for whether `df` already has a `prediction` column. Its sibling function
  `apply_estimator()` (line 1023-1092, the backend for the near-identical `ml.apply_estimator`
  node's `op="predict"`) performs the *exact same* operation but explicitly guards against this:
  ```python
  if "prediction" in df.columns:
      raise ValueError("df already has a 'prediction' column; rename it before predicting.")
  ```
  `predict()` has no equivalent check, so real data in a column named `prediction` is silently
  destroyed. Every other column-adding op in this module (`apply_estimator`'s `"transform"`/
  `"score_samples"` ops, `fit_transform`, `fit_and_label`'s `"cluster"` column) has this same
  overwrite guard — `predict()` is the sole outlier.
- **Evidence / Reproduction:** Ran the following against the repo (via `uv run python`):
  ```python
  import pandas as pd
  import emergentflow as ef

  df = pd.DataFrame({"x1": [1,2,3,4,5,6], "x2": [2,1,4,3,6,5], "y": [0,1,0,1,0,1]})
  model = ef.ml.train_regressor(df, target="y", features=["x1", "x2"])

  df_with_real_predictions = df.copy()
  df_with_real_predictions["prediction"] = ["REAL_A","REAL_B","REAL_C","REAL_D","REAL_E","REAL_F"]

  result = ef.ml.predict(model, df_with_real_predictions)
  print(result["prediction"].tolist())
  # -> [0.0, 1.0, 0.0, 1.0, 0.0, 1.0]   (the real string data is gone, no warning/error)

  ef.ml.apply_estimator(model, df_with_real_predictions, op="predict")
  # -> ValueError: df already has a 'prediction' column; rename it before predicting.
  ```
  Confirmed the real `prediction` column's string values (`"REAL_A"`, etc.) are silently
  replaced by the model's numeric output with `ef.ml.predict()`, while the equivalent
  `ef.ml.apply_estimator(..., op="predict")` call on the identical input correctly refuses and
  raises `ValueError`. Also confirmed via `grep` that neither behavior is covered by any
  existing test (`tests/test_ml.py` has `test_predict_adds_prediction_column` but nothing
  exercising a pre-existing `prediction` column), so the regression would not be caught by CI.
- **Impact:** Any graph or hand-written script using the `ml.predict` node (or calling
  `ef.ml.predict` directly) on a frame that already happens to carry a `prediction` column —
  e.g. chaining two `ml.predict` nodes without renaming in between, comparing a baseline
  model's predictions against a second model's, or predicting on a dataset that already ships
  a `prediction` field — silently loses that data with no error and no warning. This is exactly
  the failure mode `apply_estimator`'s guard was written to prevent; `predict()` reintroduces it.
- **Remediation:** Add the same guard `apply_estimator()` already uses, at
  `emergentflow/ml/__init__.py:358` (right before assigning the column):
  ```python
  @public_op(name="ef.ml.predict")
  def predict(model: FittedModel, df: pd.DataFrame) -> pd.DataFrame:
      missing = [c for c in model.feature_names if c not in df.columns]
      if missing:
          raise ValueError(f"missing feature columns {missing!r}; expected {model.feature_names!r}.")
      if "prediction" in df.columns:
          raise ValueError("df already has a 'prediction' column; rename it before predicting.")
      result = df.copy()
      result["prediction"] = model.estimator.predict(df[model.feature_names])
      return result
  ```
  Since both the `ml.predict` node's `execute()` and its compiled code call this same function,
  the fix applies identically to both ADR-0002 paths with no node-layer changes needed. Add a
  regression test mirroring `apply_estimator`'s (a frame with a pre-existing `prediction`
  column raises `ValueError`) to close the coverage gap that let this ship.

## Notes & unverified leads (optional)
- `emergentflow/ml/__init__.py:744-818` (`grid_search`): the docstring states `param_grid`
  values "must be a non-empty list of candidate values," but the code never explicitly checks
  for an empty list per key — only that `param_grid` itself is non-empty. Did not verify
  whether an empty-list value produces a confusing error vs. a clean one; would need a targeted
  repro against `GridSearchCV` to confirm actual behavior before treating as a finding.
- `emergentflow/ml/__init__.py:522-579` (`fit_transform`): `TargetEncoder` (a `fit_transform`-
  archetype estimator) is inherently supervised, but nothing in `fit_estimator`/`fit_transform`
  flags it as requiring `target` the way `SelectKBest`/`RFE`/`SelectFromModel` are called out.
  Calling it with `target=None` would fall through to `est.fit_transform(df[feature_names])`
  and presumably fail inside sklearn with a less-clear error. Not verified end-to-end; likely a
  UX/error-message quality gap rather than a correctness bug, since the underlying call would
  still fail (not silently produce wrong output).

## Coverage & limitations
- Did not review `emergentflow/recommend/` (a separate, parallel seam per `CLAUDE.md`, not part
  of `ml`), the declarative `nn.*` node family (`nn_module.py`/`nn_linear.py`/`nn_relu.py`,
  governed by a different seam), or the `explain`/`stats`/`timeseries` families, all out of
  scope for "the suite of ml tools."
- Did not exercise the full curated estimator catalog (40+ sklearn classes registered in
  `catalog.py`) end-to-end against real data for numerical-edge-case bugs (e.g. degenerate
  single-class fits, all-NaN columns, singular matrices); spot-checked the dispatch/validation
  logic in `__init__.py` that is shared across all of them rather than per-estimator behavior.
  A deeper pass fuzzing `fit_estimator`/`fit_transform`/`compare_models` across the full catalog
  with edge-case data (empty df, single row, single class, all-identical features) is a
  reasonable next step but was not performed here.
- Did not run the full `uv run pytest` suite as part of this hunt; relied on targeted greps and
  hand-written repros against the installed package.
