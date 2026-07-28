# Bug Hunt Report: Epic 16 Story Group C — analytics depth (commit 23a5ffc)

## Summary
- Scope reviewed: the full diff of commit `23a5ffc` ("feat(stats): Epic 16 Story group C —
  analytics depth") — `emergentflow/stats/__init__.py` (non-parametric tests, effect sizes/CIs,
  `correct_pvalues`, `test_proportions`, `power_analysis`, `crosstab`, `cohort_retention`,
  `funnel`), `emergentflow/ml/__init__.py` (`reduce_dimensions`), `emergentflow/viz/__init__.py`
  (`plot_projection`), all 12 matching reference nodes under `emergentflow/nodes/examples/`, and
  supporting catalog/schema/docs/pyproject changes. Focus was statistical-formula correctness,
  sign conventions, ADR-0002 codegen/execute equivalence, DataFrame mutation guarantees, column
  collision guards, and optional-dependency gating (`[umap]`).
- Confirmed findings: 2 Medium (sign-inversion bugs in reported statistics).
- Overall assessment: the implementation is solid — validation, mutation guards, column-collision
  guards, and node/wrapper param-default parity were all correct everywhere checked, and every
  claim in the task brief about crosstab's raw-table chi-square and cohort_retention's day/week
  period arithmetic held up under direct numeric testing. The two confirmed bugs are both
  self-consistency/sign-convention defects: a reported statistic's sign disagreed with the sign
  of the other fields in the same result row, verified against an independent reference
  implementation (pingouin) and against statsmodels' own documented null-hypothesis convention.
  Neither affected p-values or any other computed field.

## Findings

### Medium — `mann_whitney`'s rank-biserial effect size had an inverted sign
- **Location:** `emergentflow/stats/__init__.py:338` (pre-fix), `mann_whitney`
- **Class:** Logic error / wrong sign convention
- **Confidence:** Confirmed
- **Description:** `effect_size` was computed as `1.0 - (2.0 * u_stat) / (n_a * n_b)`. The
  correct rank-biserial correlation formula (Wendt 1972), which the code's own docstring claims
  to implement, is `(2*U) / (n_a*n_b) - 1` — the negation of what was coded. `U` here is
  `scipy.stats.mannwhitneyu`'s reported statistic for the first sample (group_a), per scipy's own
  docs ("`mannwhitneyu` always reports the statistic associated with the first sample").
- **Evidence / Reproduction:** With `group_a = [10,11,12,13,14]` and `group_b = [1,2,3,4,5]`
  (group_a completely dominates group_b), the pre-fix code returned `effect_size = -1.0`.
  Cross-checked against `pingouin.mwu(a, b)` (an independent, widely used implementation of the
  same formula), which returns `RBC = 1.0` for the identical input — the correct sign. This also
  breaks self-consistency with this same module's `ttest`, whose Cohen's d is positive when
  group_a's mean exceeds group_b's (verified: `ttest_ind(a, b)` is positive when `mean(a) >
  mean(b)`), so the codebase's own established convention is "positive = group_a greater."
- **Impact:** Any consumer of `ef.stats.mann_whitney`'s `effect_size` (or the `stats.mann_whitney`
  node's output) would read the direction of the effect backwards — e.g. concluding group_b is
  larger when group_a is actually larger.
- **Remediation:** Changed the formula to `(2.0 * u_stat) / (n_a * n_b) - 1.0` and updated the
  docstring to state the corrected formula and its sign convention explicitly. Re-verified: the
  same dominance example now returns `effect_size = 1.0`, matching pingouin.

### Medium — `test_proportions`'s z-statistic sign was inverted relative to `diff`/CI
- **Location:** `emergentflow/stats/__init__.py:577` (pre-fix), `test_proportions`
- **Class:** Logic error / wrong sign convention (self-consistency)
- **Confidence:** Confirmed
- **Description:** The function's docstring promises `diff`/`ci_low`/`ci_high`/`relative_uplift`
  are all "GROUP B RELATIVE TO GROUP A" (`p_b - p_a`), and `confint_proportions_2indep(count_b,
  n_b, count_a, n_a, compare="diff", ...)` was correctly ordered to match that convention
  (confirmed against statsmodels' source: `diff = p1 - p2` for `compare="diff"`, and the call
  passes `count_b`/`n_b` as `count1`/`nobs1`). However, `stat, p_value = proportions_ztest([
  count_a, count_b], [n_a, n_b])` passes group_a first, so per statsmodels' own documented
  convention ("the null hypothesis is that `prop[0] - prop[1] = value`"), the returned `stat` is
  oriented as `p_a - p_b` — the opposite sign of `diff`.
- **Evidence / Reproduction:** With group_a's success rate 0.5 and group_b's 0.6 (`diff = +0.1`,
  group_b higher), the pre-fix code returned `statistic = -1.42`. A statistic and its
  accompanying `diff`/CI in the same result row disagreeing in sign is a genuine self-consistency
  defect (this doesn't change the two-sided `p_value`, which is sign-invariant, but it does mean
  the reported `statistic` field contradicts `diff`'s documented direction).
- **Impact:** A user reading the one-row result (`statistic=-1.42, diff=+0.1`) would reasonably
  but incorrectly infer the statistic supports the opposite conclusion from `diff`; any downstream
  code that used `statistic`'s sign as a proxy for direction (rather than `diff`) would be wrong.
- **Remediation:** Swapped the call to `proportions_ztest([count_b, count_a], [n_b, n_a])`,
  matching the `compare="diff"` CI's argument order, and updated the docstring to state that
  `statistic` (not just `diff`/CI) follows the group-B-relative-to-group-A convention. Re-verified:
  `statistic = +1.42` now matches `diff = +0.1`'s sign.

## Notes & unverified leads (optional)
- `_partial_eta_sq_ci` (Steiger's noncentral-F method for the partial-η² CI on `anova`): passed
  every sanity check attempted (point estimate always inside the returned CI across a strong-effect
  and a null-effect synthetic dataset; correctly clamps the lower bound to 0 for a weak/null
  effect). I did not have an independent reference implementation (e.g. R's `MBESS`/`effectsize`)
  available to cross-check exact numeric values, so this is verified-by-sanity-check rather than
  verified-against-an-oracle. No inconsistency found; not escalated to a finding.
- `TSNE`'s barnes_hut method has a known sklearn-side restriction to `n_components <= 3`; a caller
  requesting `n_components >= 4` with `method="tsne"` would get an sklearn `ValueError` rather than
  a silently wrong result. This is an sklearn limitation surfaced as-is, not a wrapper bug, and
  isn't contradicted by any docstring promise, so not reported as a finding.

## Coverage & limitations
- Checked in full: sign/formula correctness for all new stats functions (`mann_whitney`,
  `wilcoxon`, `kruskal`, `chi_square`, `correct_pvalues`, `test_proportions`, `power_analysis`,
  `crosstab`, `cohort_retention`, `funnel`), `ttest`/`anova`'s new effect-size/CI fields,
  `reduce_dimensions`, `plot_projection`; DataFrame mutation guarantees (all confirmed to copy,
  none mutate); column-collision guards (`correct_pvalues`, `reduce_dimensions` both guard
  correctly); every new reference node's `codegen` vs `execute` param values/defaults (all 12
  checked line-by-line, all consistent); `[umap]` optional-dependency gating (confirmed
  `importlib.util.find_spec("umap")` is checked before any `umap` import, on the only code path
  that imports it); determinism (no unseeded randomness or dict/set iteration order dependency
  found in any new function).
- Not independently re-derived from a symbolic-math oracle: the noncentral-F root-finding CI
  formula for partial η² (`_partial_eta_sq_ci`) — see note above.
- Did not re-review pre-existing code outside this commit's diff (e.g. `ef.viz.plot`'s existing
  chart-adapter internals, which `plot_projection` merely delegates to).
