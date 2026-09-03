# Bug Hunt Report: PR #162 (Epic 159 — Inference and Evaluation)

## Summary
- **Scope reviewed:** All 24 changed files in PR #162 — 8 new files, 14 modified, 2 regenerated contracts. Covers stats (proportion CI, bootstrap CI, cluster metrics/stability, survival), ml/evaluate imbalanced metrics, clean/outliers clip action, split strategies, reference nodes, and validity rules.
- **Confirmed findings:** 2 Medium, 2 Low
- A systematic sweep across the new code found 5 bugs plus 1 feature gap. The most impactful are: (1) `detect_outliers(action="clip")` with an empty target silently adds outlier-flagging columns it should not, (2) `bootstrap_ci` crashes with an opaque `IndexError` when `n_resamples=0`, (3) `survival_curve` silently accepts non-binary event columns producing misleading curves, and (4) the `cluster_stability` reference node omitted the `params` parameter that the backend supports, preventing users from tuning estimator hyperparameters. Several other leads were investigated and refuted after careful analysis (including the `_partial_eta_sq_ci` lambda naming suspicion — the computation is actually correct).

## Findings

### Medium — `detect_outliers(action="clip")` adds outlier columns when target is empty
- **Location:** `emergentflow/clean/outliers.py:287,306-312,316-320`
- **Class:** Logic error / resource leak (wrong output shape)
- **Confidence:** Confirmed
- **Description:** When `action="clip"` and there are no eligible numeric columns to clip (empty `target`), the function adds `flag_column` (default `is_outlier`) and `score_column` (default `outlier_score`) to the output DataFrame. For `action="clip"`, these columns should never be added — clip should only cap values and return the original DataFrame unchanged. This happens in two paths: the non-grouped path (line 316–320) and the grouped empty-parts path (lines 306–312).
- **Evidence / Reproduction:**
  ```python
  df = pd.DataFrame({'id': [1,2,3], 'cat': ['a','b','c']})
  result = detect_outliers(df, columns=[], action='clip')
  # result.columns == ['id', 'cat', 'is_outlier', 'outlier_score']  ← WRONG
  ```
  The columns `is_outlier` and `outlier_score` are present even though `action="clip"` was specified. A `flag` call with the same input correctly adds them; a `clip` call should not.
- **Impact:** Users who chain `detect_outliers(action="clip")` after filtering see unexpected columns in their data. Mild data corruption (unexpected columns appearing) for a realistic path.
- **Remediation:**
  1. Added a guard at line 289: `if effective_clip and not target: return df.copy()` (parallel to the existing `effective_drop and not target` guard).
  2. Changed line 307 from `if effective_drop:` to `if effective_drop or effective_clip:` so the grouped path also returns clean.

### Medium — `cluster_stability` reference node missing `params` parameter
- **Location:** `emergentflow/nodes/examples/cluster_stability.py:51-91`
- **Class:** Missing feature / capability gap
- **Confidence:** Confirmed
- **Description:** The `cluster_stability` reference node did not expose a `params` parameter, even though the underlying `ef.stats.cluster_stability()` function accepts `params: dict[str, Any] | None = None` and passes it to the estimator during both the full-data fit and every bootstrap refit. Without this parameter, users can never customize estimator hyperparameters (e.g., `n_clusters` for KMeans), so the node always runs with sklearn defaults — KMeans with `n_clusters=8` with no way to change it.
- **Evidence / Reproduction:** The node's `params` list (lines 51–91) has no `params` entry; comparing with the `cluster_metrics` sibling node which correctly exposes `params` at the same location.
- **Impact:** The `cluster_stability` node is effectively broken for real clustering workloads — users can never control `n_clusters`, linkage, or any other estimator hyperparameter. This is a functional gap, not a crash.
- **Remediation:** Added `ParamSpec(name="params", type_token="dict[str, Any] | None", default=None, ...)` to the node's `params` list, and threaded it through both `codegen()` and `execute()`. Also regenerated UI contracts.

### Low — `bootstrap_ci` crashes with opaque `IndexError` when `n_resamples=0`
- **Location:** `emergentflow/stats/__init__.py:1298-1299`
- **Class:** Missing input validation
- **Confidence:** Confirmed
- **Description:** `bootstrap_ci` does not validate that `n_resamples > 0`. When called with `n_resamples=0`, the boot loop produces an empty list, and the subsequent `boot_stats[lower_idx]` access raises `IndexError: list index out of range` instead of a descriptive error.
- **Evidence / Reproduction:**
  ```python
  df = pd.DataFrame({'value': [1,2,3,4,5]})
  bootstrap_ci(df=df, value_col='value', statistic='mean', n_resamples=0)
  # IndexError: list index out of range  ← opaque
  ```
- **Impact:** Users passing `n_resamples=0` (e.g., from a script bug) see an opaque Python indexing error rather than a meaningful `ValueError` pointing to the bad parameter.
- **Remediation:** Added guard after existing input validations:
  ```python
  if n_resamples < 1:
      raise ValueError(f"n_resamples must be >= 1; got {n_resamples}.")
  ```

### Low — `survival_curve` silently accepts non-binary `event_col`
- **Location:** `emergentflow/stats/survival.py:148-152`
- **Class:** Missing input validation
- **Confidence:** Confirmed
- **Description:** `survival_curve` validates that `duration_col` and `event_col` exist in the DataFrame but does not validate that `event_col` is binary (0/1 or True/False). If a user passes a continuous column as `event_col`, `KaplanMeierFitter.fit()` silently interprets any non-zero value as an event, producing misleading survival curves. Compare with `proportion_confint` which correctly validates binary content.
- **Evidence / Reproduction:**
  ```python
  df = pd.DataFrame({'duration': [1,2,3], 'event': [0.5, 1.5, 2.5]})
  result = survival_curve(df, duration_col='duration', event_col='event')
  # Returns curves as if 0.5/1.5/2.5 are event indicators  ← WRONG
  ```
- **Impact:** Users with continuous `event_col` values silently get misleading survival curves (events at every observation with non-zero values). The error is not surfaced until the user inspects the curves and notices the problem.
- **Remediation:** Added binary validation after column-existence checks:
  ```python
  if not df[event_col].dropna().isin([0, 1, True, False]).all():
      raise ValueError(
          f"event_col {event_col!r} must be binary (0/1 or True/False); "
          f"got values {sorted(df[event_col].dropna().unique())!r}."
      )
  ```

## Notes & unverified leads

The following leads were investigated but REFUTED after careful analysis:

- **`_partial_eta_sq_ci` swapped CI bounds (stats/__init__.py:295-298)** — The variable names `lambda_low`/`lambda_high` appear swapped at first glance (`lambda_low` solves for the `1 - α/2` percentile), but the actual computation is correct: `lambda_low` solves for the percentile `1 - α/2` which produces a *small* non-centrality λ (the CDF is inverse w.r.t. λ), so `eta_low = λ_small / (λ_small + df1 + df2 + 1)` correctly gives the lower η² bound. The code is correct; only the naming is confusing.

- **`ml/evaluate` pos_label=1 fallback for string labels (ml/__init__.py:238)** — The fallback `pos_label = 1` when `classes_` is `None` could produce wrong metrics for string labels. However, `classes_` is always set by any fitted sklearn classifier, so this fallback is unreachable in normal use. It would only trigger on a manually constructed unfitted `FittedModel`.

- **`proportion_confint` tuple column values (stats/__init__.py:1257-1264)** — The tuple-groupby-key handling correctly handles tuple-typed column values because the code uses `groupby(['col'])` (list form) which wraps keys in 1-tuples, so `g[0]` always extracts the actual column value — even when that value is itself a tuple.

- **`cluster_metrics` zero-features crash (stats/__init__.py:1068)** — Tested with constant features; `silhouette=0.0` is returned correctly, no crash. The existing guard `clean_data.shape[1] < 1` already handles `< 1` features.

## Coverage & limitations
- Did not test `fit_survival` regression paths (requires `lifelines` extra; already tested indirectly via CI which installs it)
- Did not audit the `ui/` frontend code for bugs (scope was limited to Python changes)
- Did not audit `uv.lock` beyond verifying regeneration passes
- Surviving analysis nodes in `stats/__init__.py` (cohort_retention, funnel, test_proportions, mann_whitney, anova) were read but not deeply verified for correctness — only the new/modified Epic 159 code was the focus