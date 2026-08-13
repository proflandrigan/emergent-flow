# Bug Hunt Report: emergent-flow (Python + UI)

## Summary
- **Scope reviewed:** `emergentflow/` Python package (codegen, stats, recommend, timeseries,
  data/warehouse, clean, server, collab, connections, ir, llm) and `ui/` React canvas.
  Full test/lint/typecheck gates were run first; all pass (3740 passed, 0 failed; ruff/mypy/
  eslint/tsc clean), so findings are untested edge cases surfaced by static + targeted reading.
- **Confirmed findings:** 1 High, 3 Medium
- **Overall assessment:** The codebase is well-tested and clean — the ADR-0002 equivalence gate
  and golden tests do serious work. The bugs that survive tests are in narrowly-reached branches:
  degenerate statistical inputs (constant dummy column, NaN values in a t-test group) and two
  canvas interaction edge cases. None are data-corrupting on the happy path, but the stats ones
  silently return wrong numbers, which is the most dangerous class.

## Findings

### HIGH — GAM coefficient frame misaligns when a linear term is constant
- **Location:** `emergentflow/stats/catalog.py:328`, `emergentflow/stats/summaries.py:198`
- **Class:** Incorrect statistical output (parameter misalignment)
- **Confidence:** Confirmed
- **Description:** `sm.add_constant(df[linear_terms])` is called with statsmodels' default
  `has_constant="skip"`. If any `linear_terms` column is constant, no separate intercept column
  is added (that constant column *becomes* the intercept slot). `gam_coefficient_frame` then
  unconditionally maps `params.iloc[0]` → "Intercept" and `params.iloc[i]` → `linear_terms[i-1]`,
  so every stored coefficient lands against the wrong row label.
- **Evidence / Reproduction:**
  ```python
  import pandas as pd, numpy as np, statsmodels.api as sm
  from statsmodels.gam.generalized_additive_model import GLMGam
  from statsmodels.gam.smooth_basis import BSplines
  from emergentflow.stats.summaries import gam_coefficient_frame
  df = pd.DataFrame({"x": np.linspace(0,10,120), "cat": np.tile([3.0],120),
                     "target": np.random.default_rng(0).normal(size=120) + 5.0})
  exog = sm.add_constant(df[["cat"]])          # -> only ['cat'] (skip), NO 'const'
  res = GLMGam(df["target"], exog=exog, smoother=BSplines(df[["x"]].to_numpy(), df=[4], degree=[3])).fit()
  print(list(res.params.index))                 # ['cat','x0_s0','x0_s1','x0_s2']
  print(gam_coefficient_frame(res, ["cat"], ["x"]))  # Intercept=get(cat coef),
                                                      #  cat=get(x0_s0 spline coef)  -- WRONG
  ```
  Observed: frame rows `Intercept=1.541` and `cat=1.292`, but `res.params` index is
  `['cat','x0_s0',...]` — so `Intercept` shows the real `cat` coefficient and `cat` shows a
  spline basis coefficient. With a non-constant term the frame is correct, proving the shift.
- **Impact:** GAM fits that include a constant-valued covariate silently report every linear
  coefficient (and the intercept) under the wrong labels / with spline values, corrupting
  reported results.
- **Remediation:** Force an explicit intercept regardless of content, then map names by the
  design matrix's actual column order. In `catalog.py:327-330`, build the exog with an explicit
  constant:
  ```python
  import pandas as pd, numpy as np
  exog_lin = pd.DataFrame({"Intercept": np.ones(len(df))})
  for term in linear_terms:
      exog_lin[term] = df[term].to_numpy()
  exog_linear = exog_lin if linear_terms else pd.DataFrame({"const": np.ones(len(df))}, index=df.index)
  ```
  and, in `summaries.py:198`, derive `names` from the *actual* exog columns used by the model
  (first `len(exog.columnsOfRegressors)` params) rather than assuming `["Intercept", *linear_terms]`.
  Add a regression test with a constant linear term asserting `params` count == `names` count and
  per-term values match `sm.add_constant`'s real column order.

### MEDIUM — t-test sample-size counts include NaN value rows, skewing pooled variance & CI
- **Location:** `emergentflow/stats/__init__.py:194-201 (and 215-216)`
- **Class:** Incorrect statistical output (degenerate-input counts)
- **Confidence:** Confirmed
- **Description:** `n_a_count = a.shape[0]` counts every row where the group label matches, even
  when `value_col` is NaN, whereas `a.mean()`/`a.var()`/scipy's `ttest_ind` operate on the
  non-NaN values only. The reported `n_a`/`n_b` and the pooled-variance weight (`(n-1)*var`)
  therefore use a larger sample than the actual measurements.
- **Evidence / Reproduction:**
  ```python
  import pandas as pd, numpy as np
  from emergentflow.stats import ttest
  df = pd.DataFrame({"grp": ["a","a","a","b","b"], "val": [1.0, 2.0, np.nan, 10.0, 11.0]})
  print(ttest(df, group_col="grp", value_col="val").n_a)  # 3 (should be 2)
  ```
  Observed: `n_a=3`, `mean_a=1.5`, `a.var(ddof=1)=0.5` — pandas computed over the 2 real values,
  but `n_a_count` is 3, so `pooled_sd` weights group A by a phantom row, shifting Cohen's d and CI.
- **Impact:** A NaN in one group inflates that group's sample size and variance weighting,
  returning slightly-to-materially wrong effect-size estimates and confidence intervals; the
  reported `n_a`/`n_b` are also wrong.
- **Remediation:** Compute counts over the same non-missing subset used for means:
  ```python
  a = df.loc[df[group_col].astype(str) == a_label, value_col].dropna()
  b = df.loc[df[group_col].astype(str) == b_label, value_col].dropna()
  ```
  This aligns `n_a`, `n_b`, `var_a`, `var_b`, means and scipy with a single consistent subset.
  Add a regression test with a NaN in one group asserting `n_a` == number of non-NaN values.

### MEDIUM — Escape in flow-name rename commits instead of cancelling
- **Location:** `ui/src/io/IRToolbar.tsx:440-443`
- **Class:** Logic error (control-flow/UX)
- **Confidence:** Confirmed
- **Description:** The inline rename `<input>` has `onKeyDown` that calls `setEditingName(false)`
  on Escape, intending to cancel. But unmounting/hiding the input fires `onBlur` → `commitName()`,
  which persists `nameDraft` to the graph and saves the flow. Escape therefore commits the draft
  instead of discarding it.
- **Evidence / Reproduction:** Code trace: `Escape -> setEditingName(false)` → input unmounts →
  React fires `onBlur` (`IRToolbar.tsx:435`) → `commitName()` reads `nameDraft` and calls
  `setName`/`saveFlow`. The comment/intent ("cancel") is contradicted by observable persistence.
- **Impact:** A user typing a new name then pressing Escape to keep the old name finds the new
  name saved anyway; there is no way to cancel a rename.
- **Remediation:** Guard against a committing blur after Escape with a ref:
  ```tsx
  const cancelRename = useRef(false);
  // in input onKeyDown Escape branch:
  cancelRename.current = true;
  setEditingName(false);
  // onBlur:
  function commitName() {
    setEditingName(false);
    if (cancelRename.current) { cancelRename.current = false; return; }
    /* existing commit body */
  }
  ```
  Also reset `cancelRename.current = false` when starting an edit. Add a UI test simulating
  Escape then asserting `setName` was not called.

### MEDIUM — Expanded inspector mounts the body twice, double-firing network fetches
- **Location:** `ui/src/inspector/Inspector.tsx:284 and 289`
- **Class:** Duplicate side effects / resource waste
- **Confidence:** Confirmed
- **Description:** When `expanded`, the docked `<aside>` still renders `renderBody()` (line 284)
  *and* the `OverlayModal` renders `renderBody()` again (line ~289). Both are kept mounted at
  once, so the active tab's component (ConfigForm/QueryBuilderPreview/CodePanel/step/lineage
  panels) instantiates twice and its effects run twice — duplicate `/compile`, `/compile-spec`,
  `/lineage`, `/inspect` requests, duplicated subscriptions, and two live inputs bound to the same
  store param.
- **Evidence / Reproduction:** Byte-level: both call sites are unconditional (aside always
  returns `renderBody()`; when `expanded` the modal also calls `renderHeader()`+`renderBody()`).
  No `key` isolates them. Opening the expanded inspector on a `data.query_builder` node issues the
  `/compile-spec` debounce from two instances.
- **Impact:** Doubled server round-trips and duplicated UI state/side effects on the expanded
  inspector; wasted bandwidth and potential for stale/duplicate writebacks from two controlled
  inputs editing the same store value.
- **Remediation:** Render the docked body only when collapsed, and the modal body only when
  expanded. E.g. gate the aside's body area:
  ```tsx
  {!expanded && <div style={{ flex: 1, ... }}>{renderBody()}</div>}
  {expanded && <OverlayModal ...>{renderBody()}</OverlayModal>}
  ```
  (keep header/tabs visible in both so the tab strip stays usable). Add/adjust a component test to
  assert a single mounted instance of the active tab component when expanded.

## Notes & unverified leads
- **Partial-eta-square CI `+1` denominator** (`emergentflow/stats/__init__.py:251-252`): the
  conversion `eta = lambda / (lambda + df1 + df2 + 1)` carries a trailing `+1` not present in the
  point estimate `ss_effect/(ss_effect+ss_resid)`; the CI is therefore slightly biased vs. its own
  point estimate. Framed as "Steiger 2004" formulation, but the denominator mismatch with the point
  estimate at the null could not be proven wrong authoritatively — flagged for a stats author to
  confirm against the reference.
- **Composite helper name collision** (`emergentflow/codegen/compiler.py:416`): `_composite_<slug>`
  is not collision-deduplicated like `build_name_map`; two slug-identical composite ids would
  shadow, but ids are UUIDs so this is cosmically unlikely. Not confirmed as reachable.
- **Warehouse `dry_run` "estimated_rows" == `len(EXPLAIN)`** (three adapters): counts EXPLAIN plan
  lines, not row cardinality; the returned number is constant w.r.t. actual query size. It may be
  an intentional plan-node count rather than a cardinality mislabeled; could not confirm the
  intended semantic, so left as a note.
- **`bayesian_fit_stats` `next(iter(...))`** would StopIteration if `observed_data.sizes` were
  empty; unreachable in practice. Not confirmed.
- **Numerous lower-confidence static leads** (spec_compiler join-type fallthrough, `add_constant`
  in VIF, rolling-window `min_periods`, connections TOCTOU, chat-turn stuck RUNNING, SSE cross-
  thread generator) surfaced by parallel discovery were not verified to reproduce and are excluded
  per the bug-hunter bar.

## Coverage & limitations
- Reviewed analysis centered on verified statistical + UI interaction bugs. The full lead inventory
  (60+) from per-family discovery agents is far larger than the confirmed set; many leads were
  plausible-but-unproven and are intentionally not reported as findings.
- Deep verification of server concurrency (SSE threads, connections TOCTOU) and recommend/timeseries
  numeric edge cases was not exhaustively re-run; those areas warrant a focused follow-up hunt.