# Bug Hunt Report: PR #153 (ml/ensembling/tuning/post-fit)

## Summary
- Scope reviewed: the `feat/ml-ensembles-tuning-postfit` branch (PR #153) — the new backend
  ops in `emergentflow/ml/__init__.py` (`ensemble_model`, `calibrate_model`,
  `optimize_threshold`, `finalize_model`, `blend_models`, `stack_models`, `tune_model`), the
  seven reference node definitions under `emergentflow/nodes/examples/`, and their tests
  (`tests/test_ml_ensembles.py`, `tests/test_ml_postfit.py`). The UI `catalog.json` regen and
  the `__init__.py` registration imports were reviewed for wiring only.
- Confirmed findings: 1 Medium, 1 Low.
- Overall assessment: The feature is well-structured, follows the curated-estimator
  conventions, and the `codegen`/`execute` equivalence holds (the ADR-0002 gate passes). Two
  real defects were found and fixed: four ensembling/calibration wrappers silently discarded
  a fitted model's hyperparameters by rebuilding the base with `type(model.estimator)()`
  instead of `sklearn.base.clone`, and `optimize_threshold` dropped the final
  "predict-everything-positive" operating point from the Precision-Recall curve. Both are
  corrected with evidence-backed repros (original and post-fix) and no behavioral regressions.

## Findings

### Medium — Ensembling/calibration wrappers discard the fitted model's hyperparameters
- **Location:** `emergentflow/ml/__init__.py` — `ensemble_model` (line ~432), `calibrate_model`
  (~485), `blend_models` (~615), `stack_models` (~662)
- **Class:** Logic error / silent loss of configuration
- **Confidence:** Confirmed
- **Description:** To satisfy sklearn's requirement of an *unfitted* base estimator, the four
  wrappers rebuilt each base with `type(model.estimator)()`, which constructs a fresh
  estimator using its **factory defaults**, discarding every non-default hyperparameter the
  user configured when the input `FittedModel` was trained. A model the user tuned
  (e.g. `RandomForestClassifier(max_depth=3, n_estimators=25)`) is ensembled as if it were
  `RandomForestClassifier()` (`max_depth=None, n_estimators=100`). This silently changes what
  "wrap my fitted model" means and can produce a materially different ensemble.
- **Evidence / Reproduction:**
  ```
  rf = fit_estimator(df, estimator="RandomForestClassifier",
                     params={"max_depth": 3, "n_estimators": 25}, target="label")
  print(rf.estimator.max_depth, rf.estimator.n_estimators)          # 3 25
  e = ensemble_model(rf, df, task="classification", target="label")
  inner = e.estimator.estimator
  print(inner.max_depth, inner.n_estimators)                        # None 100  (BUG)
  from sklearn.base import clone
  print(clone(rf.estimator).max_depth, clone(rf.estimator).n_estimators)  # 3 25
  ```
  `sklearn.base.clone` returns an unfitted copy that preserves every hyperparameter, which is
  exactly the "unfitted clone" the estimators require. The same reproduction pattern holds for
  `blend_models`/`stack_models` base estimators and `calibrate_model`.
- **Impact:** Ensembles/blends/stacks/calibrations are built from re-initialized default bases
  rather than the models the user actually fit, so tuned configurations are silently ignored.
- **Remediation:** Replace the default-constructor rebuilds with `clone`:
  - `ensemble_model`: `base = clone(model.estimator)`
  - `calibrate_model`: `base = clone(model.estimator)`
  - `blend_models`: `estimators = [(f"m{i}", clone(m.estimator)) for i, m in enumerate(models)]`
  - `stack_models`: same list comprehension replacement
  Added `from sklearn.base import clone`. Verified post-fix: the ensemble base now reports
  `max_depth == 3`, `n_estimators == 25`. Locked in by `test_ensemble_model_preserves_base_hyperparameters`
  and `test_blend_and_stack_preserve_base_hyperparameters`.

### Low — optimize_threshold drops the "predict-everything-positive" operating point
- **Location:** `emergentflow/ml/__init__.py` — `optimize_threshold` (loop ~line 542)
- **Class:** Boundary / off-by-one
- **Confidence:** Confirmed
- **Description:** `sklearn.metrics.precision_recall_curve` returns `precision`/`recall`
  arrays that are **one element longer** than `thresholds`; the trailing `(precision, recall)`
  pair is the decision-threshold-0 ("classify everything positive") operating point. The code
  iterated with `zip(thresh, prec, rec, strict=False)`, which truncates to the length of
  `thresh` and silently drops that final operating point from both the returned `metrics`
  table and the `best_f1`/`best_threshold` search.
- **Evidence / Reproduction:**
  ```
  r = optimize_threshold(model, df, target="label")
  # imbalanced data: 2000 positives? no, 10% positive -> PR arrays len 2001, thresh len 2000
  len(r.metrics)                      # 2000 rows reported
  len(prec), len(rec), len(thresh)    # 2001, 2001, 2000
  r.metrics["precision"].iloc[-1]     # 0.0   <- final all-positive point absent
  prec[-1]                            # 1.0   <- true final operating point precision
  ```
  The reported table omitted one valid operating point and the F1 search never evaluated it.
- **Impact:** The returned `metrics` table is missing a legitimate decision point, and
  `best_threshold`/`best_f1` can be marginally understated when the trivial
  predict-everything-positive point is among the best (common with weak/random models on
  balanced data). Real but low-severity.
- **Remediation:** Iterate over the full `precision`/`recall` arrays, pairing each with
  `thresholds[i]` when available and `0.0` otherwise:
  ```python
  rows, best_t, best_f1, n_thresh = [], 0.0, 0.0, len(thresh)
  for i, (p, r) in enumerate(zip(prec, rec, strict=True)):
      f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
      t = float(thresh[i]) if i < n_thresh else 0.0
      rows.append((t, float(p), float(r), f1))
      if f1 > best_f1:
          best_f1, best_t = f1, t
  ```
  Post-fix `len(r.metrics) == 2001 == len(prec)`, the final row reports threshold `0.0` and
  matches `prec[-1]`/`rec[-1]`. Locked in by `test_optimize_threshold_metrics_cover_full_precision_recall_curve`.

## Notes & unverified leads
- **Task-arity mismatches are not validated.** `ensemble_model`/`blend_models`/`stack_models`
  accept a `task` that may disagree with the fitted estimators' true archetype (e.g. passing a
  regressor with `task="classification"`), which fails at fit time with an opaque sklearn error
  rather than `ef.ml`'s typed errors. Verified a clear error is raised but the message is not
  custom. Likely worth a precondition check, but not confirmed as a distinct defect.
- **`blend_models` never surfaces its `weights` param** through the `BlendModels` node or its
  codegen (the node only exposes `task/target/features/voting`). Not a bug (defaults to `None`
  and both paths agree), just an unused capability.

## Coverage & limitations
- Repro scripts were run in an isolated venv against synthetic data only (no torch/network).
- The UI `catalog.json` delta was not independently validated; the PR author's UI gates and the
  `check_ui_boundary.py` invariant were assumed (boundary is unchanged by these edits).
- Candidates like `finalize_model`'s `get_params(deep=False)` reconstruction were verified to
  preserve hyperparameters (no change made).
