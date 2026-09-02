# Bug Hunt Report: PR #161 (by= param for detect_outliers / outlier_summary)

## Summary
- Scope reviewed: All changed files in PR #161 — `emergentflow/clean/outliers.py`, `emergentflow/stats/eda.py`, node definitions, and tests.
- Confirmed findings: 1 Medium (two variants of the same root cause), 1 Low
- Two bugs found: `detect_outliers` uses label-based `reindex` which silently corrupts results on DataFrames with non-unique indices; `outlier_summary` returns a bare `pd.DataFrame()` with no columns when `by=` is used on an empty DataFrame, violating the contract shared by its non-grouped path.

## Findings

### Medium — `detect_outliers` grouped path corrupts results on duplicate-index DataFrames
- **Location:** `emergentflow/clean/outliers.py:298` (original line)
- **Class:** Label-based index misalignment
- **Confidence:** Confirmed
- **Description:** The grouped path (`by_cols` truthy) calls `out.reindex([i for i in df.index if i in out.index])` to restore original row order. `reindex` is label-based: when the DataFrame has duplicate index labels, a single label maps to multiple source rows, and `reindex` silently picks only the first match for each occurrence of the label. Rows whose label appears more than once are duplicated (from the first match) instead of carrying their own values.
- **Evidence / Reproduction:**
  ```python
  df = pd.DataFrame({"group": ["a", "a", "b", "b"], "x": [1.0, 100.0, 5.0, 7.0]},
                     index=[0, 0, 1, 2])
  result = detect_outliers(df, columns=["x"], method="zscore", threshold=1.0, by="group")
  # Expected is_outlier: [False, True, False, False]  (row 1, x=100.0, flagged)
  # Actual:               [False, False, False, False]  (row 1's flag eaten by reindex)
  ```
  The same bug affects the `drop=True` variant — the wrong rows are dropped, producing incorrect row counts.
- **Impact:** Users with non-unique (e.g., concatenated) index DataFrames get silently wrong outlier flags and counts. Row filtering (`drop=True`) returns an incorrect subset.
- **Remediation:** Replace the index-reset approach — use an intermediate `RangeIndex` during the grouped/recursive computation, then restore original labels at the end via positional indexing:
  ```python
  original_index = df.index
  df_temp = df.copy()
  df_temp.index = pd.RangeIndex(len(df))
  # ... groupby df_temp, compute parts ...
  out = pd.concat(parts)
  pos_order = [i for i in range(len(df)) if i in out.index]
  out = out.reindex(pos_order)
  if pos_order:
      out.index = original_index[pos_order]
  return out
  ```

### Low — `outlier_summary` with `by=` on empty DataFrame returns zero-column DataFrame
- **Location:** `emergentflow/stats/eda.py:307` (original line)
- **Class:** Missing column contract on edge case
- **Confidence:** Confirmed
- **Description:** When `outlier_summary` is called with `by=` on a zero-row DataFrame, `df.groupby(by_cols)` produces zero groups, `result_rows` stays empty, and the code returns `pd.DataFrame()` — an empty DataFrame with no columns. The non-grouped path returns a DataFrame with proper columns (`column`, `method`, `threshold`, `lower`, `upper`, `n`, `n_outliers`, `pct_outliers`). Any downstream code accessing `result["column"]` gets a `KeyError`. The detect_outliers path already had a fix for its equivalent case (commit 59269d3); this is the same gap in outlier_summary.
- **Evidence / Reproduction:**
  ```python
  df = pd.DataFrame({"group": pd.Series(dtype="object"), "x": pd.Series(dtype="float64")})
  result = outlier_summary(df, columns=["x"], method="zscore", threshold=1.0, by="group")
  # result.columns -> []  (expected: ["group", "column", "method", ...])
  result["column"]  # KeyError
  ```
- **Impact:** Any node downstream of an `OutlierSummary` node with `by=` set that processes an empty frame will crash with a `KeyError`.
- **Remediation:** Return a proper empty DataFrame with the expected columns when `result_rows` is empty:
  ```python
  if not result_rows:
      expected_cols = by_cols + [
          "column", "method", "threshold", "lower", "upper",
          "n", "n_outliers", "pct_outliers",
      ]
      return pd.DataFrame({c: pd.Series(dtype="object") for c in expected_cols})
  return pd.concat(result_rows, ignore_index=True)
  ```

## Notes & unverified leads
- **`by_cols` as tuple**: If a user passes a tuple for `by`, `isinstance(by, str)` is False, so `list(by)` is called — `list(("a", "b"))` produces `["a", "b"]`, which works. Not a bug.
- **Group key column in `columns=`**: If the same column is in both `by_cols` and `columns`, the code correctly excludes it from measurement columns. Verified correct.
- **Multilevel groupby NaN keys**: `dropna=False` keeps NaN group keys — verified that the code handles this correctly via the existing `key_tuple` unpacking.

## Coverage & limitations
- Reviewed only the changed files in PR #161. The rest of the codebase was not audited.
- The duplicate-index fix was verified against both `drop=False` and `drop=True` paths.
- The full test suite (3857 passed) was run to ensure no regressions.