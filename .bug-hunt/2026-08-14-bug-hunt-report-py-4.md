# Bug Hunt Report: emergentflow (Python package)

- **Date:** 2026-08-14 (session 4)
- **Branch:** `feat/agent-onboarding-and-oom`
- **Team:** Bug-Hunt skill (Discovery → Verify → Report loop)

## Summary
- Scope reviewed: `emergentflow/stats/` (two-sample `ttest`, `test_proportions`, `group_by_aggregate`),
  `emergentflow/script/` (`run_code`), plus fresh sweeps of `data/warehouse/` adapters/query layer,
  `ml/` (`evaluate`), `timeseries/`, `clean/`, `viz/`, `recommend/`, and `explain/`. Areas already
  covered by the immediately preceding 2026-08-14 hunts (mutation, cache, codegen, collab) were
  not re-audited.
- Confirmed findings: 1 High, 3 Medium. All four reproduced with concrete evidence, fixed, and
  pinned by regression tests.
- Overall assessment: The package remains healthy (full suite 3826 passed, ruff/mypy clean,
  ADR-0002 equivalence gate green). This hunt's confirmed defects cluster around the same theme as
  prior hunts: **typed-but-unenforced boundary contracts**. Three of the four are raw, untyped
  exceptions (`ZeroDivisionError`, `KeyError`, `TypeError`) leaking out of `@public_op`-decorated
  functions whose docstrings already promise typed `ValueError`-family errors, and the fourth is a
  data-integrity mislabel on empty warehouse results. A number of additional leads (see Notes) were
  demonstrated or reasoned through and deliberately not promoted because their triggers are
  degenerate or a sound fix would be invasive.

## Findings

### [HIGH] — `test_proportions` crashes with untyped `ZeroDivisionError` on an all-NaN group
- **Location:** `emergentflow/stats/__init__.py:593-598`
- **Class:** Arithmetic / division-by-zero on degenerate-but-reachable input
- **Confidence:** Confirmed
- **Description:** `test_proportions` validates only that `success_col` is binary and that
  `group_col` has exactly two distinct labels — it never checks that each group has at least one
  non-null `success_col` value. When one group's success values are all `NaN`, `n_a` or `n_b` is
  `0`, and the `proportions_ztest([count_b, count_a], [n_b, n_a])` call on line 593 divides by zero
  (statsmodels emits `RuntimeWarning: divide by zero` and a raw `ZeroDivisionError` propagates to
  the caller, breaking the function's typed `ValueError` contract).
- **Evidence / Reproduction:**
  ```python
  import pandas as pd
  from emergentflow.stats import test_proportions
  df = pd.DataFrame({"g": ["a","a","a","b","b","b"], "s": [0,1,1,None,None,None]})
  test_proportions(df, group_col="g", success_col="s")
  ```
  Observed before the fix: `ZeroDivisionError: division by zero` (statsmodels). After the fix:
  `ValueError: two-proportion z-test needs at least one non-null 's' value in each of groups
  'a' and 'b'; found 3 and 0.` Regression test:
  `tests/test_stats.py::test_test_proportions_all_nan_success_group_raises`.
- **Impact:** A user running a two-proportion test where one cohort has no observed outcomes gets a
  raw low-level crash from a public API instead of a clear, typed error — and the canvas/node layer
  surfaces the crash unhelpfully rather than a diagnosable message.
- **Remediation:** Raise a typed guard between computing the counts and calling statsmodels:
  ```python
  if n_a == 0 or n_b == 0:
      raise ValueError(
          f"two-proportion z-test needs at least one non-null {success_col!r} value in each of "
          f"groups {a_label!r} and {b_label!r}; found {n_a} and {n_b}."
      )
  ```

### [MEDIUM] — `ttest` crashes with `ZeroDivisionError` on an all-NaN (or single-observation) group
- **Location:** `emergentflow/stats/__init__.py:205-212`
- **Class:** Arithmetic / division-by-zero on degenerate input
- **Confidence:** Confirmed
- **Description:** `ttest` drops NaN values per group and then computes a pooled standard deviation
  with denominator `n_a_count + n_b_count - 2` and a standard-error term with denominator
  `n_a_count * n_b_count`. If one group is all-`NaN` (`n=0`), `n_a*n_b == 0` triggers a raw
  `ZeroDivisionError` at the `se_d` computation; if each group has exactly one observation
  (`n_a=n_b=1`), the pooled denominator `1+1-2 == 0` is also a division by zero. Only the "exactly 2
  distinct labels" guard exists, so a group label that is present but numerically empty slips
  through.
- **Evidence / Reproduction:**
  ```python
  import pandas as pd
  from emergentflow.stats import ttest
  # all-NaN group
  ttest(pd.DataFrame({"g":["a","a","b","b"],"v":[None,None,5.0,7.0]}), group_col="g", value_col="v")
  # one observation per group
  ttest(pd.DataFrame({"g":["a","b"],"v":[1.0,2.0]}), group_col="g", value_col="v")
  ```
  Observed before the fix: `ZeroDivisionError: float division by zero` in both cases. After the
  fix: clear `ValueError`s = as shown in the reproduction. Regression tests:
  `tests/test_stats.py::test_ttest_all_nan_group_raises` and
  `tests/test_stats.py::test_ttest_single_observation_per_group_raises`.
- **Impact:** Same surfaced-as-crash class as above; the t-test is a common statistical primitive,
  and a NaN-filled group is a realistic data-cleaning state.
- **Remediation:** Guard both degenerate cases before any arithmetic:
  ```python
  if n_a_count == 0 or n_b_count == 0:
      raise ValueError(
          f"two-sample t-test needs at least one non-null {value_col!r} value in each of "
          f"groups {a_label!r} and {b_label!r}; found {n_a_count} and {n_b_count}."
      )
  if n_a_count + n_b_count <= 2:
      raise ValueError(
          f"two-sample t-test needs more than one total observation to compute a pooled "
          f"variance; groups {a_label!r}/{b_label!r} had {n_a_count} and {n_b_count}."
      )
  ```

### [MEDIUM] — `group_by_aggregate` dict `agg` with an unknown column leaks a raw `KeyError`
- **Location:** `emergentflow/stats/eda.py:307-311`
- **Class:** API contract misuse / untyped error / silent drop
- **Confidence:** Confirmed
- **Description:** `group_by_aggregate` validates `by` and `columns` against `df.columns`, but
  when `agg` is a dict it never validates the dict's keys. The docstring documents "unknown
  columns raise"; instead, `df[by_cols + list(agg.keys())]` raises a raw `KeyError` for an
  unknown agg key. Worse, when `columns` is given the code **silently filters out** agg keys not in
  `columns` (line 309) rather than erroring — so the same typo either crashes or silently changes
  scope depending on whether `columns` is supplied, and an unknown key that is *in* `columns` still
  crashes.
- **Evidence / Reproduction:**
  ```python
  import pandas as pd
  from emergentflow.stats.eda import group_by_aggregate
  df = pd.DataFrame({"g": ["a","b"], "x": [1,2]})
  group_by_aggregate(df, by="g", agg={"nope": "mean"})
  ```
  Observed before the fix: `KeyError: "['nope'] not in index"`. After the fix:
  `ValueError: unknown aggregation column(s) ['nope']; expected one of ['g', 'x'].` Regression:
  `tests/test_stats_eda_seam.py::test_group_by_aggregate_unknown_dict_agg_key_raises`.
- **Impact:** Inconsistent error type vs. the documented contract, and a silent behavior schism
  between the `columns`-given and `columns}-None paths.
- **Remediation:** Validate dict-agg keys against `df.columns` and raise the same typed error used
  for `by`/`columns`:
  ```python
  where else:
      if columns is not None:
          agg = {k: v for k, v in agg.items() if k in columns}
      unknown_agg = [k for k in agg if k not in df.columns]
      if unknown_agg:
          raise ValueError(
              f"unknown aggregation column(s) {unknown_agg!r}; "
              f"expected one of {list(df.columns)!r}."
          )
      target = df[by_cols + list(agg.keys())]
  ```

### [MEDIUM] — `script.run_code` leaks a raw `TypeError` instead of `CustomCodeError` for non-str code
- **Location:** `emergentflow/script/__init__.py:58-61`
- **Class:** API contract / error-handling on the `@public_op` boundary
- **Confidence:** Confirmed
- **Description:** `run_code` wraps only `SyntaxError` from `compile`, but `compile` raises
  `TypeError` for a non-string `code` (e.g. `None`) and `ValueError` for embedded NUL bytes. The
  documented contract (docstring + `CustomCodeError` class doc) promises that compile failures are
  rewrapped as `CustomCodeError`, so a `None` code path leaks an untyped `TypeError` to the caller.
  (The NUL-byte case was already caught — Python raises it as a `SyntaxError` — but non-str input
  was not.)
- **Evidence / Reproduction:**
  ```python
  from emergentflow.script import run_code
  run_code(None, 5)
  ```
  Observed before the fix: `TypeError: compile() arg 1 must be a string, bytes or AST object`.
  After the fix: `CustomCodeError: custom code failed to compile: compile() arg 1 must be a
  string, bytes or AST object`. Regression:
  `tests/test_script_run_code.py::test_run_code_non_str_raises_custom_code_error`.
- **Impact:** Public API contract said "compile failures raise `CustomCodeError`"; non-str input is
  the one compile-failure kind that escaped typed, making callers that branch on `CustomCodeError`
  miss it.
- **Remediation:** Broaden the catch clause to the exception hierarchy `compile` actually raises:
  ```python
  except (SyntaxError, ValueError, TypeError) as exc:
      raise CustomCodeError(f"custom code failed to compile: {exc}") from exc
  ```

## Notes & unverified leads
- **Empty warehouse result sets mislabel every column `nullable=False` (demonstrated, not fixed).**
  In `duckdb_adapter.execute` (and the postgres/redshift/bigquery siblings), `nullable` is derived
  as `bool(df[col].isna().any())`. On a 0-row frame, `.any()` is `False` for every column, so an
  empty result reports all columns as non-nullable regardless of the real schema — e.g.
  `SELECT * FROM t WHERE a > 100` (0 rows) over a nullable `INTEGER`/`VARCHAR` table reports
  `a.nullable=False, s.nullable=False`. Demonstrated via the duckdb adapter. Not promoted/fixed:
  the correct value for an empty frame is genuinely unknowable from the frame alone, so a fix means
  deciding the default (report `True`/unknown), which touches the shared schema contract across all
  four adapters and could regress describe-relation behavior — flagged for a domain-level decision
  rather than a mechanical patch.
- **`ef.ml.evaluate` `roc_auc` `pos_label` coupling (refuted for current sklearn).** Hypothesis:
  string or non-`0`/`1` integer labels make `roc_auc_score(y_true, proba[:, 1])` with the default
  `pos_label=1` either raise (suppressed → metric dropped) or invert the AUC relative to
  `precision`/`recall`, which use `pos_label=classes[1]`. Reproduced with string labels
  (`['no','yes']`) and disjoint-int labels (`[1,2]`): current sklearn returns the *correct* AUC in
  both cases, because `proba[:,1]` reflects `classes[1]` and sklearn's default `pos_label` path
  still scores it consistently. Not a bug on the pinned dependency; worth re-checking if the sklearn
  pin is bumped.
- **Warehouse `max_rows` unvalidated (reasoned, not promoted).** `_inject_limit` renders
  `LIMIT max_rows + 1` and adapters call `df.head(request.max_rows)`; a negative or zero `max_rows`
  yields `LIMIT 0`/`LIMIT -1` and surprising `head()` semantics. Confirmed the absence of a guard in
  `query.py`, but this needs an end-user-supplied negative `max_rows`, which the query layer and
  nodes normally derive from UI controls — Low, left for a params-validation-focused pass.
- **Warehouse engine/connection lifecycle (resolved as out-of-scope design, not a defect).**
  `postgres_adapter._engine` builds a fresh engine per call without `dispose()`, and BigQuery builds
  a throwaway client for credentials. Demonstrated the absence of `dispose()`, but SQLAlchemy's
  default `QueuePool` is garbage-collected with the engine, and a shared-length process or explicit
  engine-cache is a design choice, not a correctness violation. Flagged as an efficiency note for
  the drivers team rather than a bug.
- **`stats` empty-group leads in `mann_whitney`/`kruskal` (refuted as-crash, behavior confirmed).**
  These return all-`NaN` result rows (with scipy `SmallSampleWarning`) rather than crashing when a
  group is all-NaN — demonstrated. Arguably the *desired* "warning, NaN result" behavior given the
  family's idiom; not promoted.
- **Data-frame mutability of `impute_missing`/`cast_types`** (`clean/__init__.py`) — `SimpleImputer`
  returns a positional ndarray assigned by position, and casting float→int with NaN raises a raw
  pandas `ValueError`. Both are edge/coercion concerns on frequently-touched code; listed here as
  candidate targets for a future deep-dive rather than verified defects in this pass. Outlier
  NaN handling was already documented (not promoted) in the prior 2026-08-14 hunt.

## Coverage & limitations
- Deep-dive verified and fixed: `stats/ttest`, `stats/test_proportions`, `stats/eda:group_by_aggregate`,
  `script/run_code`. Fresh sweeps (leads only) across `data/warehouse/` adapters/query/credentials,
  `ml/evaluate`, `timeseries`, `clean`, `viz`, `recommend`, `explain`.
- Not re-audited (heavily covered by immediately-preceding 2026-08-13/14 hunts): `collab/`,
  `codegen/`, `server/`, `clean/outliers`. The `ui/` canvas is out of scope for this Python-package
  hunt.
- Gates: full suite 3826 passed (5 new regression tests), `ruff check`/`format` clean, `mypy`
  clean, ADR-0002 equivalence gate 331 passed. No UI contract artifacts were touched, so no
  `export_ui_contracts`/boundary churn was required.
