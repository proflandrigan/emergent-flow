"""
emergentflow.causal.panel
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Panel / difference-in-differences effect estimation (issue #164 Gap 1).

``ef.causal.did`` fits a two-way fixed-effects DiD model (unit FE + time FE) with the
treated:post interaction estimated on an explicitly constructed ``did = treated * post``
column, and reports cluster-robust SEs (clustered on ``unit_col`` by default, via the
same ``_cov_kwargs`` machinery as ``ef.stats.fit_model``) plus a pre-trend /
parallel-trends test.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from emergentflow.api import public_op
from emergentflow.causal.errors import CausalError
from emergentflow.stats.catalog import _cov_kwargs, _patsy_term

__all__ = ["did"]


def _validate_column(df: pd.DataFrame, col: str, require_binary: bool = False) -> None:
    if col not in df.columns:
        raise CausalError(f"unknown column {col!r}; expected one of {list(df.columns)!r}.")
    if require_binary:
        vals = pd.unique(df[col].dropna())
        if not set(vals).issubset({0, 1}):
            raise CausalError(
                f"{col!r} must be binary (0/1 or True/False); found values {sorted(vals)!r}."
            )


def _scratch_name(df: pd.DataFrame, base: str) -> str:
    """A helper-column name that does not collide with any existing column of *df*."""
    name = base
    k = 0
    while name in df.columns:
        k += 1
        name = f"{base}_{k}"
    return name


def _pre_trend_p(
    df: pd.DataFrame,
    *,
    outcome: str,
    unit_col: str,
    time_col: str,
    treated_col: str,
    post_col: str,
    period_col: str,
) -> float:
    """Linear parallel-trends test over the pre-period only.

    Restricts to rows where ``post == 0`` and fits
    ``outcome ~ C(unit) + C(time) + period:treated`` with SEs clustered on ``unit_col``,
    where ``period`` is the 0-based numeric index of ``time_col``. The ``period:treated``
    coefficient is the treated arm's differential linear pre-trend; its two-sided
    cluster-robust p-value is the test. The period fixed effects absorb any *common* trend,
    so under staggered adoption (where the pre-period composition of the two arms shifts
    over time) a shared non-linear trend no longer loads onto the differential slope --
    without them the test rejected true parallel trends essentially always in that design.
    (The ``treated`` main effect is absorbed by the unit FE.) Returns ``nan`` when the
    pre-period cannot support the fit.
    """
    pre = df[df[post_col] == 0]
    if len(pre) < 4 or pre[time_col].nunique() < 2 or pre[treated_col].nunique() < 2:
        return float("nan")
    pre = pre.copy()
    pre[period_col] = pre[time_col].astype("category").cat.codes.astype(float)
    formula = (
        f"{_patsy_term(outcome)} ~ C({_patsy_term(unit_col)}) + C({_patsy_term(time_col)}) + "
        f"{period_col}:{treated_col}"
    )
    try:
        model = smf.ols(formula, data=pre).fit(
            cov_type="cluster", cov_kwds={"groups": pre[unit_col]}
        )
    except Exception:  # noqa: BLE001 - return NaN on rank-deficiency / too few clusters
        return float("nan")
    interact = f"{period_col}:{treated_col}"
    for name in model.params.index:
        if name == interact or name.endswith(f":{treated_col}"):
            return float(model.pvalues[name])
    return float("nan")


@public_op(name="ef.causal.did")
def did(
    df: pd.DataFrame,
    *,
    outcome: str,
    unit_col: str,
    time_col: str,
    treated_col: str,
    post_col: str,
    covariates: list[str] | None = None,
    cluster_col: str | None = None,
) -> pd.DataFrame:
    """Difference-in-differences with two-way fixed effects and cluster-robust SEs.

    ``unit_col`` pins the panel's units (subject/school/...), ``time_col`` the period.
    ``treated_col`` marks units ever treated; ``post_col`` marks post-treatment periods;
    the DiD estimate is the coefficient on the ``treated:post`` interaction. ``covariates``
    (optional) are added as adjustment regressors. SEs are cluster-robust, clustered on
    ``cluster_col`` when given and falling back to ``unit_col`` (so repeated measures per
    unit get honest SEs by default) -- the same ``cov_type="cluster"`` path as
    ``ef.stats.fit_model``.

    Rows with a missing value in any model column are dropped before fitting. The design
    must be identified: both arms present, ``post`` varying, the interaction non-constant,
    at least two clusters, and a full-rank design matrix -- otherwise a ``CausalError`` is
    raised instead of statsmodels' silent minimum-norm solution.

    Caveat -- staggered adoption: with units treated at different times the TWFE coefficient
    is a variance-weighted average of every 2x2 comparison, including ones where
    already-treated units act as controls (Goodman-Bacon 2021). When effects are
    heterogeneous across adoption cohorts it can fall outside the range of the cohort
    effects; prefer a common adoption date or an event-study / stacked design in that case.

    Returns a one-row, tidy ``pd.DataFrame`` with columns ``estimate``, ``std_err``,
    ``ci_low``, ``ci_high``, ``p_value``, ``n_obs`` (rows used), ``n_units_treated``,
    ``n_units_control``, ``pre_trend_p`` (the parallel-trends test). Never mutates ``df``.
    """
    for col in (outcome, unit_col, time_col, treated_col, post_col):
        _validate_column(df, col)
    _validate_column(df, treated_col, require_binary=True)
    _validate_column(df, post_col, require_binary=True)
    for c in covariates or []:
        _validate_column(df, c)
    if cluster_col is not None:
        _validate_column(df, cluster_col)

    model_cols = [outcome, unit_col, time_col, treated_col, post_col, *(covariates or [])]
    if cluster_col is not None:
        model_cols.append(cluster_col)
    # Drop incomplete rows up front: patsy drops them silently while the cluster groups
    # would keep their full length, and the two must line up.
    work = df.dropna(subset=model_cols).copy()
    if work.empty:
        raise CausalError("no complete rows remain after dropping missing values.")

    treated_num = _scratch_name(work, "_treated_num")
    post_num = _scratch_name(work, "_post_num")
    did_col = _scratch_name(work, "_did")
    period_col = _scratch_name(work, "_period")
    work[treated_num] = work[treated_col].astype(int)
    work[post_num] = work[post_col].astype(int)
    work[did_col] = work[treated_num] * work[post_num]

    if (work[treated_num] == 0).sum() == 0:
        raise CausalError(
            "the DiD design has no control (never-treated) units; the effect is not identified."
        )
    if work[post_num].nunique() < 2:
        raise CausalError("post_col must vary (both pre- and post-treatment periods are needed).")
    if work[did_col].nunique() < 2:
        raise CausalError(
            "the treated:post interaction is constant; check that treated units are observed in "
            "post-treatment periods."
        )
    group_col = cluster_col if cluster_col is not None else unit_col
    if work[group_col].nunique() < 2:
        raise CausalError(
            f"cluster-robust SEs need at least two clusters in {group_col!r}; found one."
        )

    rhs = [f"C({_patsy_term(unit_col)})", f"C({_patsy_term(time_col)})", did_col]
    rhs += [_patsy_term(c) for c in covariates or []]
    formula = f"{_patsy_term(outcome)} ~ " + " + ".join(rhs)
    spec: dict[str, object] = {"cov_type": "cluster", "cov_group": group_col}
    cov_kwargs = _cov_kwargs(work, spec)
    ols = smf.ols(formula, data=work)
    exog = np.asarray(ols.exog, dtype=float)
    if np.linalg.matrix_rank(exog) < exog.shape[1]:
        raise CausalError(
            "the DiD design matrix is rank deficient (the treated:post interaction is collinear "
            "with the unit/time fixed effects or covariates); the effect is not identified."
        )
    model = ols.fit(**cov_kwargs)

    estimate = float(model.params[did_col])
    se = float(model.bse[did_col])
    lo = float(model.conf_int().loc[did_col, 0])
    hi = float(model.conf_int().loc[did_col, 1])
    p_value = float(model.pvalues[did_col])

    n_units_treated = int(work.loc[work[treated_num] == 1, unit_col].nunique())
    n_units_control = int(work.loc[work[treated_num] == 0, unit_col].nunique())
    pre_trend_p = _pre_trend_p(
        work,
        outcome=outcome,
        unit_col=unit_col,
        time_col=time_col,
        treated_col=treated_num,
        post_col=post_num,
        period_col=period_col,
    )

    return pd.DataFrame(
        [
            {
                "estimate": estimate,
                "std_err": se,
                "ci_low": lo,
                "ci_high": hi,
                "p_value": p_value,
                "n_obs": int(len(work)),
                "n_units_treated": n_units_treated,
                "n_units_control": n_units_control,
                "pre_trend_p": pre_trend_p,
            }
        ]
    )
