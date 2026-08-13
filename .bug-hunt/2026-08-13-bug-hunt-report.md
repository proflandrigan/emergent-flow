# Bug Hunt Report: emergent-flow Python package

## Summary
- Scope reviewed: `emergentflow/stats/`, `emergentflow/timeseries/`, `emergentflow/recommend/`,
  `emergentflow/eval/`, `emergentflow/explain/`, and `emergentflow/codegen/` (with supporting
  researchers). Targeted bug hunt; the full ~61k-line package was not exhaustively reviewed.
- Confirmed findings: 1 High, 1 Medium (both fixed + regression-tested)
- Overall assessment: The package is carefully written — the strongest suspicion class (the
  ADR-0002 compile-to-code == execute invariant) held up under verification, and only the
  obscure MANY-cardinality composite-boundary edge broke it. The most user-impactful bug is a
  silent NaN-poisoning path in `mann_whitney`, which directly contradicts an equivalent NaN
  fix already applied to its sibling `ttest`.

## Findings

### High — `mann_whitney` returns NaN statistic/p-value whenever `value_col` contains a NaN
- **Location:** `emergentflow/stats/__init__.py:341` (now fixed at 341-346)
- **Class:** Null-handling / statistics correctness
- **Confidence:** Confirmed
- **Description:** `a`/`b` are sliced *without* dropping NaN rows, then passed straight into
  `scipy.stats.mannwhitneyu`, which strips NaN internally. As a result the reported `n_a`/`n_b`
  (and the rank-biserial effect-size denominator `2U/(n_a*n_b)`) count NaN rows, while scipy's
  statistic is computed on the NaN-free subset. When *any* value is NaN, scipy propagates NaN,
  so both `statistic` and `p_value` come back `NaN` — a silently useless result for the user —
  even though the data is perfectly analysable. The sibling `ttest` was already fixed to
  `.dropna()` for exactly this reason (lines 194-195), so the two tests disagree.
- **Evidence / Reproduction:**
  ```python
  import pandas as pd, numpy as np
  from emergentflow.stats import mann_whitney
  df = pd.DataFrame({"group": ["a","a","a","b","b","b"], "value": [1.,2.,np.nan,4.,5.,6.]})
  print(mann_whitney(df, group_col="group", value_col="value")[["statistic","p_value","n_a","n_b"]])
  # BEFORE: statistic NaN, p_value NaN, n_a 3, n_b 3    (n_a wrong: should be 2)
  # AFTER:  statistic 0.0, p_value 0.2, n_a 2, n_b 3   (matches scipy on the dropna subset)
  ```
  Direct scipy check: `mannwhitneyu([1,2,nan],[4,5,6]).pvalue -> nan`, but
  `mannwhitneyu([1,2],[4,5,6]).pvalue -> 0.2`.
- **Impact:** Any user running a Mann-Whitney test on real data containing missing values gets a
  NaN p-value instead of an answer, plus inflated reported sample sizes — silently wrong output
  on a common path.
- **Remediation:** Drop NaN rows before both the slice and the call (mirrors `ttest`):
  ```python
  a = df.loc[df[group_col].astype(str) == a_label, value_col].dropna()
  b = df.loc[df[group_col].astype(str) == b_label, value_col].dropna()
  ```
  Regression test added: `tests/test_stats.py::test_mann_whitney_nan_values_are_excluded`.

### Medium — composite MANY boundary IN port drops the seeded value in `execute` (ADR-0002 divergence)
- **Location:** `emergentflow/codegen/executor.py:213` (now fixed at 213-223)
- **Class:** Logic error / equivalence violation (ADR-0002: `compile_to_code(ir) == execute(ir)`)
- **Confidence:** Confirmed
- **Description:** When a composite node's subgraph leaves a `Cardinality.MANY` IN port dangling
  (no intra-subgraph source), `resolve_composite_boundary` treats it as a boundary port and
  `_execute_composite` seeds it via `seed_inputs` (executor.py:305-309). But the executor's MANY
  branch (executor.py:213-219) never consulted `seed_inputs` — it built `values` purely from
  intra-subgraph `sources` (empty for a dangling port) and handed the node `[]`, silently
  dropping the seeded outer value. The compile side (`_codegen_composite`, compiler.py:392-397)
  rebinds the same boundary port to a positional arg `p{i}` and *does* thread the outer value
  through. Net effect: the compiled program returns `[7]` while `execute` returns `[]` for the
  same graph — breaking the centrepiece equivalence invariant.
- **Evidence / Reproduction:** A composite wrapping a single MANY fan-in node, fed by an outer
  source emitting `7`:
  - `execute(outer_graph)["comp"]["out0"]` → `[]` (BEFORE fix), `[7]` (AFTER fix)
  - `compile_to_code(outer_graph)` emits `composite_out0 = _composite_comp([src_out])` and the
    compiled `main()` returns `{"composite_out0": [7]}` on both sides of the fix.
  Full runnable repro in `/tmp/opencode/repro_many_boundary.py`.
- **Impact:** Composites whose subgraph exposes a MANY boundary input compute the wrong result
  under `execute` (the in-process reference interpreter the server/canvas use) while the compiled
  form is correct — a silent correctness gap on an unusual but legal graph shape.
- **Remediation:** Honor `seed_inputs` in the MANY branch before the sources-only fallback,
  exactly as the ONE-cardinality branch already does:
  ```python
  seed_key = (node.id, port.name)
  if seed_inputs is not None and seed_key in seed_inputs:
      inputs[port.name] = seed_inputs[seed_key]
      continue
  ```
  Regression test added: `tests/test_codegen_executor.py::test_composite_many_dangling_boundary_in_port_seeds_value`, which asserts `execute` and the compiled `main()` return the same `[1]`.

## Notes & unverified leads
- `emergentflow/recommend/catalog.py:73-80` `_compute_popularity_scores(score_type="weighted")`
  computes `col_sum * mean_rating` (= `count * mean²`), but its own docstring (line 56) says
  `count * mean_rating`. However `count * mean_rating` *mathematically* collapses to `col_sum`,
  i.e. identical to `"count"`, so the documented formula is degenerate and the intent is
  ambiguous. Left unfixed (changing it is a behavior gamble); flagged so a maintainer can pick a
  deliberate formula and correct the docstring.
- `emergentflow/stats/diagnostics_catalog.py:52` `_vif`: `spec.get("columns") or list(...)
  select_dtypes("number")` treats an explicitly-empty `columns` as "all numeric columns", and a
  non-numeric column in `columns` would crash inside statsmodels rather than raise a typed error.
  Requires a crafted spec; low reachability.
- `emergentflow/recommend/catalog.py:838/892` `temporal_split`/`random_split` use
  `round(len * test_ratio)`; small per-user groups can round to zero test rows so they are never
  scored. Inherent to rounding; arguably intended — needs a product decision, not a fix.
- `emergentflow/recommend/interactions.py:112` `from_dataframe` (and `eval/export.py`
  `build_finetune_rows`, `eval/label.py:72`): non-canonical frames raise a bare `ValueError`/
  `KeyError` instead of the family's typed error. Defensive-polish only.

## Coverage & limitations
- Reviewed: `stats` (incl. `eda`, `summaries`, `diagnostics_catalog`), `timeseries`, `recommend`
  (catalog, interactions, metrics, splits), `eval`, `explain`, `codegen` (compiler, executor,
  declarative, wiring, naming, traversal, context, export, composite).
- Not exhaustively reviewed: `ml` catalog (~large), `data/warehouse`, `llm`, `server`, `collab`,
  `viz`, `clean`, `research`, `validity`. These were only noticed/treated where the delegated
  sweep surfaced no confirmable bug within the verification budget.
- The two reported bugs were verified with minimal local reproductions against test data; no
  live/networked resources were touched. `mann_whitney` was previously untested for NaN (only a
  `ttest` NaN test existed); both fixes now carry regression tests.