# Bug Hunt Report: analytics and data transform suite (emergentflow.stats / emergentflow.clean)

## Summary
- Scope reviewed: `emergentflow/clean/__init__.py` (all ops: impute_missing, drop_missing,
  select_columns, cast_types, filter_rows, explode_lists, encode_lists, merge, semi_join) and
  their node wrappers in `emergentflow/nodes/examples/`; `emergentflow/stats/` (`__init__.py`,
  `spec.py`, `catalog.py`, `diagnostics.py`, `diagnostics_catalog.py`, `eda.py`, `summaries.py`);
  `emergentflow/data/__init__.py` (loaders). Warehouse adapters (`emergentflow/data/warehouse/`)
  were not reviewed in depth.
- Confirmed findings: 1 High, 1 Medium, 1 Low.
- Overall assessment: the `clean`/`stats` wrappers are generally careful thin wrappers with good
  boundary validation, but the validation gate for stats models (`_prepare_model_spec`) has a gap
  that lets an invalid GAM `link`/`family` combination reach statsmodels raw, and the `vif`
  diagnostic has a real, easily-triggered crash whenever any target column is already constant
  (zero-variance), because it assumes `statsmodels.add_constant` always prepends a constant
  column — which it silently doesn't when the data already contains one.

## Findings

### High — `vif` diagnostic crashes (or misattributes results) when any target column is constant
- **Location:** `emergentflow/stats/diagnostics_catalog.py:47-67` (`_vif`)
- **Class:** API/contract misuse — silently-changing return shape of `sm.add_constant` not accounted for
- **Confidence:** Confirmed
- **Description:** `_vif` builds `exog = sm.add_constant(df[columns]).to_numpy()` and then reads
  `variance_inflation_factor(exog, i)` for `i` in `1..len(columns)`, assuming `add_constant`
  always prepends a new constant column at index 0 (so column `i` in `exog` lines up with
  `columns[i-1]`). But `sm.add_constant`'s default `has_constant="skip"` does **not** add a
  constant column if the input already contains one that is constant (zero-variance) — a
  perfectly ordinary situation (a flag column, a filtered subset where a numeric column happens
  to take one value, etc.). When that happens, `exog` has exactly `len(columns)` columns instead
  of `len(columns) + 1`, silently shifting every VIF-to-column association by one and making the
  final loop iteration (`i == len(columns)`) read one column past the end of `exog`.
- **Evidence / Reproduction:**
  ```python
  import numpy as np, pandas as pd, emergentflow as ef
  np.random.seed(0)
  n = 50
  df = pd.DataFrame({
      "a": np.random.normal(size=n),
      "b": np.full(n, 5.0),   # constant column
      "c": np.random.normal(size=n),
  })
  ef.stats.diagnostic(df, diagnostic="vif", spec={"columns": ["a", "b", "c"]})
  ```
  Raises `IndexError: index 3 is out of bounds for axis 1 with size 3`. With `sm.add_constant`
  called directly on the same shape of data (`sm.add_constant(pd.DataFrame({"a":..., "b": [5]*10}))`),
  the returned frame keeps shape `(10, 2)` instead of `(10, 3)` — confirming no constant column
  was added, which is the root cause. Also reproduced with `columns=["a", "b"]` (2 columns, 1
  constant): still crashes with `IndexError: index 2 is out of bounds for axis 1 with size 2`.
  Before crashing, any earlier loop iterations compute VIF for the *wrong* column (the values are
  shifted by one index), so a caller who somehow saw a partial/cached result would additionally
  get silently mislabeled data — not just a crash.
- **Impact:** Any user running the `vif` diagnostic on a dataset where one of the selected
  (or, by default, all-numeric) columns happens to be constant gets an unhandled `IndexError`
  instead of a diagnostic result — a normal, realistic multicollinearity-checking workflow that
  crashes on ordinary data (e.g. a filtered subset, an indicator/flag column with only one value
  present, a column that's constant within a particular cohort).
- **Remediation:** Don't rely on `add_constant`'s column-count being `len(columns) + 1`. Either
  force a constant to be added (`sm.add_constant(df[columns], has_constant="add")`, which always
  prepends regardless of existing constants) and keep the current `enumerate(..., start=1)`
  indexing, or compute the offset from the actual returned shape, e.g.:
  ```python
  exog_df = sm.add_constant(df[columns], has_constant="add")
  exog = exog_df.to_numpy()
  offset = list(exog_df.columns).index if "const" in exog_df.columns else 0
  ```
  The simplest fix is `has_constant="add"`, which restores the invariant the loop already assumes.

### Medium — GAM `link` given without `family` bypasses spec validation, raising a raw `KeyError`
- **Location:** `emergentflow/stats/spec.py:89-102` (`_prepare_model_spec`) and
  `emergentflow/stats/catalog.py:320-323` (`_fit_gam`)
- **Class:** Logic error — validation gate conditioned on the wrong field
- **Confidence:** Confirmed
- **Description:** `_prepare_model_spec`'s family/link compatibility check only runs
  `if "family" in spec and spec["family"] is not None`. For `GAM`, `family` is *optional*
  (`_fit_gam` defaults it to `"gaussian"` via `spec.get("family") or "gaussian"`), but `link` is
  also optional and independently spec-able. A caller who supplies `link` without `family` skips
  the validation block entirely (since `"family" not in spec`), so an invalid link for the
  (implicitly-defaulted) `"gaussian"` family is never checked at the gate. `_fit_gam` then does
  `link_cls = _GLM_LINKS[family_key][link_key]`, which raises a bare `KeyError` instead of the
  module's documented `InvalidModelSpecError`. The same code path in `_fit_glm` is safe only
  because `family` is a *required* spec field for GLM, so the gate's check always fires there;
  GAM is the one model where `family` is optional and thus the gap is reachable.
- **Evidence / Reproduction:**
  ```python
  import pandas as pd, emergentflow as ef
  df = pd.DataFrame({"y": list(range(1, 11)), "x": list(range(1, 11))})
  spec = {"target": "y", "smooth_terms": [{"column": "x"}], "link": "logit"}
  ef.stats.fit_model(df, model="GAM", spec=spec)
  ```
  Raises `KeyError: 'logit'` from inside `_fit_gam`. As a positive control, the same invalid
  link with `family` explicitly given (`spec["family"] = "gaussian"`) correctly raises
  `InvalidModelSpecError: link 'logit' is not valid for family 'gaussian'; expected one of
  ['identity', 'inverse', 'log'].` — proving the validation logic itself is correct and the bug is
  purely that it's gated on the presence of `"family"` in `spec` rather than on the presence of
  `"link"`.
- **Impact:** A user of the GAM archetype who sets a link without also (redundantly) setting the
  default family gets an opaque `KeyError` instead of the typed, actionable `InvalidModelSpecError`
  every other invalid-spec path in this module produces — breaking the module's own documented
  contract ("Raises ... InvalidModelSpecError for ... link ... is not valid for family ...").
- **Remediation:** Trigger the compatibility check whenever *either* `family` or `link` is present,
  and resolve the effective family the same way `_fit_gam` does:
  ```python
  if ("family" in spec and spec["family"] is not None) or (
      "link" in spec and spec["link"] is not None
  ):
      from emergentflow.stats.catalog import _GLM_FAMILIES, _GLM_LINKS
      family = spec.get("family") or "gaussian"
      if family not in _GLM_FAMILIES:
          raise InvalidModelSpecError(...)
      link = spec.get("link")
      if link is not None and link not in _GLM_LINKS[family]:
          raise InvalidModelSpecError(...)
  ```
  Note this needs the model-appropriate default (`"gaussian"` matches GAM's own default); if this
  gate is ever reused for a model whose default family differs, that default must be resolved
  per-model rather than hardcoded.

### Low — `ef.clean.merge(..., suffixes=None)` crashes with a raw pandas `TypeError`
- **Location:** `emergentflow/clean/__init__.py:385-401` (`merge`)
- **Class:** API/contract misuse — dead validation branch
- **Confidence:** Confirmed
- **Description:** `merge`'s validation explicitly branches on `suffixes is not None`
  (`if suffixes is not None and len(suffixes) != 2: raise ValueError(...)`, and later
  `kwargs["suffixes"] = tuple(suffixes) if suffixes is not None else suffixes`), which only makes
  sense if the function intends `suffixes=None` to be an accepted, meaningful input. But
  `pandas.DataFrame.merge` does not accept `suffixes=None` at all — it always raises
  `TypeError: Passing 'suffixes' as a <class 'NoneType'>, is not supported.` So the `None` branch
  the wrapper explicitly wrote code to support is unreachable in practice and always surfaces an
  untyped pandas error instead of `clean.merge`'s own `ValueError` convention used everywhere else
  in this function (unknown `how`, mismatched key lengths, etc.).
- **Evidence / Reproduction:**
  ```python
  import pandas as pd, emergentflow as ef
  left = pd.DataFrame({"k": [1, 2, 3], "v": ["a", "b", "c"]})
  right = pd.DataFrame({"k": [1, 2, 3], "v": ["x", "y", "z"]})
  ef.clean.merge(left, right, on=["k"], suffixes=None)
  ```
  Raises `TypeError: Passing 'suffixes' as a <class 'NoneType'>, is not supported. Provide
  'suffixes' as a tuple instead.` — an unhandled library exception, not the module's own
  `ValueError` convention.
- **Impact:** Low — the `clean.merge` reference node (`emergentflow/nodes/examples/merge.py`)
  coalesces a falsy `suffixes` param to the default `["_x", "_y"]` before calling `clean.merge`
  (`values.get("suffixes") or ["_x", "_y"]`), so this is unreachable via the canvas/node graph.
  It only bites a caller using `ef.clean.merge` directly from Python with `suffixes=None`, which
  also violates the function's own type hint (`suffixes: tuple[str, str] = ("_x", "_y")`, not
  `Optional`).
- **Remediation:** Either drop the dead `is not None` branching and tighten the type hint to
  disallow `None` (raising the module's own `ValueError` up front, matching the type hint), or, if
  `None` is meant to be genuinely supported (to omit suffixing to let pandas raise on unresolved
  collisions), catch the case explicitly and give it a clear message:
  ```python
  if suffixes is not None and len(suffixes) != 2:
      raise ValueError(...)
  ```
  becomes
  ```python
  if suffixes is None:
      raise ValueError("suffixes must be a 2-tuple/list of exactly 2 strings; got None.")
  if len(suffixes) != 2:
      raise ValueError(...)
  ```

## Notes & unverified leads (optional)
- `emergentflow/stats/catalog.py`'s `term_map` rewriting (`_fit_ols`/`_fit_wls`/`_fit_gls`/
  `_fit_glm`/`_fit_mixedlm`) only undoes `Q(...)` quoting for terms that match a fixed-effect
  column name *exactly*. A quoted (space-containing) column used as a **categorical** fixed effect
  produces Patsy term names like `Q('my col')[T.b]`, which won't match the `term_map` key
  (`Q('my col')`) and would leak the internal `Q(...)` syntax into the tidy coefficient frame's
  `term` column instead of being cleanly rendered. Not verified end-to-end (didn't confirm Patsy's
  exact categorical-detection/term-naming behavior for quoted identifiers) — would need a
  concrete repro with a space-containing categorical column to confirm before reporting as a
  finding.
- `emergentflow/clean/__init__.py`'s `encode_lists` -> `_coerce_labels` treats `pd.NA` (as opposed
  to `None`/`np.nan`) as a literal label rather than a missing value, since the missing-check is
  `value is None or (isinstance(value, float) and pd.isna(value))` and `pd.NA` is not a `float`.
  Not verified against a realistic nullable-dtype list column — would need to confirm this is
  actually reachable (e.g. via a pandas nullable-object column) before reporting as a finding.

## Coverage & limitations
- Not reviewed in depth: `emergentflow/data/warehouse/*` (adapters, credentials, query
  compilation), `emergentflow/stats/registry.py`/`shapes.py`/`models.py` (mostly thin
  dataclasses/registries, lower bug density), and the full node-wrapper set for every `clean`/
  `stats` op (only `merge`, `semi_join`, `explode_lists`, `encode_lists` node wrappers were
  checked in detail against ADR-0002 equivalence).
- `emergentflow/clean/__init__.py`'s `impute_missing`, `drop_missing`, `select_columns`,
  `cast_types`, `filter_rows`, `explode_lists`, `encode_lists`, and `semi_join` were read in full
  and no further confirmable defects were found beyond what's reported above.
- Bayesian (`_fit_bayesian_glm`) and MixedLM fitters were read but not exercised end-to-end
  (require `pymc`/`bambi`/`arviz` or longer-running MCMC fits) — reasoning was limited to static
  review plus the one MixedLM `cov_re` indexing check that was verified.
