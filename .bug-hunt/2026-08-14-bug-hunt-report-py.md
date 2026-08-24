# Bug Hunt Report: emergentflow

## Summary
- **Scope reviewed:** Full Python SDK (`emergentflow/`): codegen, IR, stats, ml, recommend, eval, llm, timeseries, clean, explain, data, viz, server, collab. UI layer (`ui/`) excluded from this pass.
- **Confirmed findings:** 2 Medium, 3 Low
- **Overall assessment:** The codebase is well-structured, thoroughly tested (3814 passing tests), and type-checked clean by mypy. The confirmed bugs are narrow edge cases — no critical or high-severity defects were found. The most impactful bug is a silent counting error in `test_proportions` when NaN values are present in the success column.

## Findings

### Medium — NaN guard in test_proportions uses broken `not in` check; diff/NaN guard fails for NaN p_a
- **Location:** `emergentflow/stats/__init__.py:597`
- **Class:** Logic error / NaN handling
- **Confidence:** Confirmed
- **Description:** The condition `p_a not in (0, float("nan")) and p_a != 0` is intended to guard against division by zero and NaN. However, `float("nan") not in (0, float("nan"))` evaluates to `True` because NaN `!=` NaN per IEEE 754. So when `p_a` is NaN, the guard does NOT catch it — `diff / p_a` still produces NaN (which happens to be harmless via propagation), and more importantly `p_a not in (0, float("nan"))` combined with `p_a != 0` always evaluates to the same as `p_a != 0` alone. The `not in` against NaN is dead logic and conceptually wrong. Should use `math.isnan(p_a)`.
- **Evidence / Reproduction:**
  ```python
  import math
  p_a = float("nan")
  assert p_a not in (0, float("nan")) and p_a != 0  # True — guard does NOT catch NaN
  assert not (p_a == 0 or math.isnan(p_a))            # False — correct guard
  ```
- **Impact:** No functional impact (NaN / NaN = NaN), but the guard is misleading dead code that masks intent. If someone later changed the fallback from `float("nan")` to a default value, NaN p_a would silently pass through and produce a wrong `relative_uplift`.
- **Remediation:** Replace `p_a not in (0, float("nan")) and p_a != 0` with `not (p_a == 0 or math.isnan(p_a))` and import `math`.

### Medium — test_proportions does not drop NaN values from success_col, inflating denominator counts
- **Location:** `emergentflow/stats/__init__.py:586-589`
- **Class:** Data integrity / Silent wrong output
- **Confidence:** Confirmed
- **Description:** Lines 586-587 extract `a` and `b` series without calling `.dropna()`, so `n_a` and `n_b` count rows including NaN. But `a.sum()` on line 589 skips NaN by pandas default (NaN-safe sum). This means `n_b` counts the NaN row while `count_b` does not, producing an underestimated `p_b`. The validation on line 583 does call `.dropna().isin(...)`, so NaN values are validated but not excluded from counting — an inconsistency that silently distorts proportions.
- **Evidence / Reproduction:**
  ```python
  import pandas as pd
  b = pd.Series([1, 0, None])
  n_b = int(b.shape[0])  # 3 — counts NaN row
  count_b = int(b.sum()) # 1 — sum skips NaN
  p_b = count_b / n_b    # 0.333 — should be 0.5 if NaN excluded consistently
  ```
  Running `ef.stats.test_proportions` with NaN in `success_col` demonstrates this.
- **Impact:** Users unaware of NaN in their success column get silently wrong proportions — denominators are inflated, proportions are underestimated.
- **Remediation:** Add `.dropna()` to the series extraction on lines 586-587:
  ```python
  a = df.loc[df[group_col].astype(str) == a_label, success_col].dropna()
  b = df.loc[df[group_col].astype(str) == b_label, success_col].dropna()
  ```

### Low — dict-valued encodings in viz validation check dict keys instead of field-value column references
- **Location:** `emergentflow/viz/spec.py:53-54`
- **Class:** Logic error / Wrong column validation
- **Confidence:** Confirmed
- **Description:** When an encoding value is a `dict` (e.g., `{"field": "temperature", "aggregate": "sum"}`), the column validation at line 54 extracts `list(value.keys())` — yielding `["field", "aggregate"]` — and checks whether those keys are column names. The actual column reference is `value["field"]`, not the dict keys. In practice this works for plotly's `hover_data` convention where dict keys ARE column names, but for Altair-style or generalized `{"field": "col", ...}` encoding, the wrong names are checked.
- **Evidence / Reproduction:**
  ```python
  encoding = {"x": {"field": "temperature", "aggregate": "sum"}}
  value = encoding["x"]
  refs = list(value.keys())  # ["field", "aggregate"] — neither is a column name
  ```
  The test at `tests/test_viz_plot_seam.py:77` uses the `hover_data` convention (keys as column names), which works, so this doesn't appear in testing.
- **Impact:** Dictionary-valued encodings that nest the column reference inside a `"field"` key would get wrong column validation (checking "field" and "aggregate" as column names instead of the actual column). Currently only affects hypothetical or future encoding patterns since plotly's `hover_data` uses keys-as-column-names.
- **Remediation:** Handle the `{"field": ...}` sub-pattern explicitly:
  ```python
  if isinstance(value, dict):
      refs = [value.get("field")] if "field" in value else list(value.keys())
  ```

### Low — dict-valued encodings in viz validation only extract keys from dict values, not `"field"` key
- **Location:** `emergentflow/viz/spec.py:52-54`
- **Class:** Logic error / Wrong column validation
- **Confidence:** Confirmed
- **Description:** (Same as above, different angle.) For a dict-encoding like `{"field": "actual_col", "aggregate": "sum"}`, the validator checks `"field"` and `"aggregate"` as column names, both of which are wrong. The correct column name is `value["field"]`. This is a latent bug in the column-validation gate.
- **Impact:** See above — only affects encodings using the `{"field": ...}` sub-pattern.
- **Remediation:** Same as above.

### Low — clean `sample` uses identical `random_state=seed` for every stratum, producing correlated draws
- **Location:** `emergentflow/clean/sampling.py:93`
- **Class:** Statistics / Sampling correctness
- **Confidence:** **Unproven (no behavioral impact demonstrated)**
- **Description:** The `stratified_sample` function loops over groups produced by `df.groupby(by, ...)` and calls `group.sample(n=take, random_state=seed)` with the same global `seed` for every stratum. This means each stratum's random draw starts from the same RNG state, producing correlated (not independent) random samples across strata. However, every draw within a stratum is still uniform, and the same-seed idiom is a common (if debatable) reproducibility convention. The practical behavioral impact is subtle and not demonstrated with concrete wrong output.
- **Why NOT fixed:** Changing to a per-stratum derived seed would alter deterministic outputs across many tests (`test_clean_sampling.py`, `test_epic16_acceptance_demos.py`, equivalence matrices) — high churn for an unproven statistical refinement. Left as a lead.
- **Remediation (if pursued):** Use a derived per-stratum seed: `random_state=(seed + hash(key)) % (2**31 - 1)`, and update the affected determinism/golden tests.

## Notes & unverified leads

- **`emergentflow/explain/__init__.py:377`** — `plot_predicted_vs_actual` calls `.min()`/`.max()` on potentially empty arrays from empty input DataFrame. However, `_require_regression_model` and `.predict()` would fail before reaching `.min()`. Unproven as independently reachable crash.
- **`emergentflow/llm/gateway.py:99`** — `response.choices[0]` assumes at least one choice. Could fail for some LiteLLM error modes. Cannot reproduce without a live provider.
- **`emergentflow/clean/sampling.py:93`** — The `for _key, group in df.groupby(by, sort=True, observed=True, dropna=False)` uses `sort=True` but also `observed=True` which is not meaningful for non-categorical data. Likely innocent.
- **`emergentflow/codegen/naming.py:206-214`** — The hash-disambiguation loop may exit without uniqueness if collisions persist through all 16 iterations. Extremely unlikely in practice (blake2s 4+ chars). Would need a post-loop uniqueness assertion.
- **`emergentflow/server/service.py:609`** — `_skip_reason(src, node_status)` references `src` which could be undefined if the MANY-port loop at line 594 iterates zero times. Guarded by the `any_upstream_missing` boolean which can only be True inside the loop. Not reachable.

## Coverage & limitations
- UI layer (`ui/`) not reviewed (JavaScript/TypeScript canvas — separate domain, different bug classes).
- Test files (`tests/`) not reviewed for correctness of the tests themselves.
- No dependency-audit pass (supply-chain risk).
- No concurrency stress tests run (all identification is from static analysis of synchronization patterns).
