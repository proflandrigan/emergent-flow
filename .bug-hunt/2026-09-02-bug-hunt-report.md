# Bug Hunt Report: emergent-flow PR #162 (Epic 159)

## Summary
- Scope reviewed: All 23 changed files in PR #162 — 8 new files, 14 modified, 1 re-export snapshot.
- Confirmed findings: 4 Medium, 1 Low
- Four bugs found in the PR's new code, all in code paths that either silently crash or prevent intended usage. None are data-corruption bugs, but two (cluster_metrics crash, demo runtime failure) would halt execution for users hitting those paths.

## Findings

### Medium — cluster_metrics crashes when `features` yields 0 feature columns
- **Location:** `emergentflow/stats/__init__.py:1068`
- **Class:** Unhandled edge case / missing precondition check
- **Confidence:** Confirmed
- **Description:** `cluster_metrics` filters `label_col` out of the provided `features` before computing, but doesn't check whether the filtered result is empty. When all provided feature columns are the label column (e.g., `features=["label"]` where `label_col="label"`), the filtered array has shape `(n, 0)` and `calinski_harabasz_score`, `davies_bouldin_score`, and `silhouette_score` all raise `ValueError` because they require at least 1 feature.
- **Evidence / Reproduction:**
  ```python
  df = pd.DataFrame({'label': [0, 0, 1, 1], 'feat': [1.0, 2.0, 3.0, 4.0]})
  ef.stats.cluster_metrics(df, label_col='label', features=['label'])
  # → ValueError: Found array with 0 feature(s) (shape=(4, 0)) while a minimum of 1 is required.
  ```
  Also reproduces with `features=[]`.
- **Impact:** Any `cluster_metrics` call where the user passes `features` that include only the `label_col` (or no numeric columns at all) crashes with an opaque sklearn error rather than returning `nan` metrics as the similar `n_clusters < 2` and `n_samples == 0` branches do.
- **Remediation:** Added `or clean_data.shape[1] < 1` to the existing early-return guard at line 1068. The guard now returns NaN cluster metrics for the degenerate zero-features case immediately, before any sklearn call.

### Medium — Demo `examples/segmentation_study/demo.py` uses wrong column name
- **Location:** `examples/segmentation_study/demo.py:58`
- **Class:** Hardcoded column name mismatch
- **Confidence:** Confirmed
- **Description:** The wine dataset's column `od280/od315_of_diluted_wines` was hardcoded in the demo as `od280_od315` (underscores instead of slashes). This caused `ef.clean.select_columns` to raise `UnknownColumnError`.
- **Evidence / Reproduction:**
  ```
  $ uv run python examples/segmentation_study/demo.py
  → UnknownColumnError: unknown columns ['od280_od315']; expected one of [... 'od280/od315_of_diluted_wines', ...]
  ```
- **Impact:** The demo (a new intro file for Epic 159) crashes on first run, failing its purpose as a worked example.
- **Remediation:** Changed `od280_od315` → `od280/od315_of_diluted_wines` in the `columns` list.

### Medium — Demo `examples/segmentation_study/demo.py` misassigns `fit_transform` return
- **Location:** `examples/segmentation_study/demo.py:63`
- **Class:** Return-value misuse (ignored tuple unpacking)
- **Confidence:** Confirmed
- **Description:** `ef.ml.fit_transform` returns `(FittedTransformer, pd.DataFrame)`, but the demo assigned it to `scaled` (a bare name) and then passed `scaled` to both `fit_and_label` and `cluster_stability`, which expect a DataFrame. `fit_and_label` crashed with `AttributeError: 'tuple' object has no attribute 'columns'`.
- **Evidence / Reproduction:**
  ```
  # After fixing the column name:
  $ uv run python examples/segmentation_study/demo.py
  → AttributeError: 'tuple' object has no attribute 'columns'
  ```
- **Impact:** The demo crashes on first run. Also: `fit_and_label` returns `(FittedModel, pd.DataFrame)`, which was similarly misassigned to a bare name and then passed to `cluster_metrics` expecting a DataFrame. Two separate tuple-unpacking bugs in the same script.
- **Remediation:** Changed to `_, scaled = ef.ml.fit_transform(...)` and `_, clustered = ef.ml.fit_and_label(...)`.

### Medium — Demo `examples/segmentation_study/demo.py` passes unsupported `label_col` to `fit_and_label`
- **Location:** `examples/segmentation_study/demo.py:70`
- **Class:** Unsupported keyword argument
- **Confidence:** Confirmed
- **Description:** `ef.ml.fit_and_label` does not accept a `label_col` parameter — its output column is always named `"cluster"`. The demo passed `label_col="segment"`, which raised `TypeError: fit_and_label() got an unexpected keyword argument 'label_col'`. This forced a cascade: the downstream `cluster_metrics` call also referenced `"segment"` instead of `"cluster"`.
- **Evidence / Reproduction:** Demonstrated by the demo crash after fixing the two previous bugs.
- **Impact:** The demo crashes before it produces any output.
- **Remediation:** Removed the `label_col` kwarg from the `fit_and_label` call and changed `cluster_metrics`'s `label_col` to `"cluster"`.

### Low — E501 line too long in `test_reference_nodes.py`
- **Location:** `tests/test_reference_nodes.py:782`
- **Class:** Style / code-gate violation
- **Confidence:** Confirmed
- **Description:** The golden-string assertion for the new `strategy` param default generated a line 111 characters long, exceeding the project's 100-char ruff limit. CI's `ruff check` would fail.
- **Evidence / Reproduction:** `uv run ruff check .` reported `E501 Line too long (111 > 100)` at the line before the fix.
- **Impact:** CI lint gate would fail for the PR.
- **Remediation:** Wrapped the string expression across multiple lines using parentheses.

## Notes & unverified leads
None.

## Coverage & limitations
- Did not audit the UI contract artifacts (`ui/src/generated/`) since those are regenerated by scripts.
- Did not test survival analysis (requires `lifelines` extra, not installed).
- Did not test the `[bayes]` or `[recommend]` optional extras.
- All four medium bugs were in new files or changed code introduced by this PR.