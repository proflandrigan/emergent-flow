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

import pandas as pd
import statsmodels.formula.api as smf

from emergentflow.api import public_op
from emergentflow.causal.errors import CausalError
from emergentflow.stats.catalog import _cov_kwargs

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


def _pre_trend_p(
    df: pd.DataFrame,
    *,
    outcome: str,
    unit_col: str,
    time_col: str,
    treated_col: str,
    post_col: str,
) -> float:
    """Linear parallel-trends test over the pre-period only.

    Restricts to rows where ``post == 0``, converts ``time_col`` to a 0-based numeric
    period, and fits ``outcome ~ C(unit) + period + treated:period``. The
    ``treated:period`` coefficient captures whether the treated arm's pre-period trend
    deviates from the control arm's; its two-sided p-value is the parallel-trends test.
    (The ``treated`` main effect is absorbed by the unit FE and patsy drops it.)
    """
    pre = df[df[post_col] == 0].copy()
    if len(pre) < 4:
        return float("nan")
    pre["_period"] = pre[time_col].astype("category").cat.codes.astype(float)

    def _fit(sub: pd.DataFrame):
        if len(sub) < 3:
            return None
        try:
            # treated:period is estimable (unit FE absorbs the treated main effect); a
            # separate categorical period FE is unnecessary since _period is linear.
            formula = f"{outcome} ~ C({unit_col}) + _period + _period:{treated_col}"
            return smf.ols(formula, data=sub).fit()
        except Exception:  # noqa: BLE001 - return NaN on rank-deficiency
            return None

    model = _fit(pre)
    if model is None:
        return float("nan")
    interact = f"_period:{treated_col}"
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

    Returns a one-row, tidy ``pd.DataFrame`` with columns ``estimate``, ``std_err``,
    ``ci_low``, ``ci_high``, ``p_value``, ``n_obs``, ``n_units_treated``,
    ``n_units_control``, ``pre_trend_p`` (the parallel-trends test). Never mutates ``df``.
    """
    for col in (outcome, unit_col, time_col, treated_col, post_col):
        _validate_column(df, col)
    _validate_column(df, treated_col, require_binary=True)
    _validate_column(df, post_col, require_binary=True)
    for c in covariates or []:
        _validate_column(df, c)

    work = df.copy()
    # Explicit interaction column: treated (numeric) x post (numeric) => cleaner param name.
    work["_treated_num"] = work[treated_col].astype(int)
    work["_post_num"] = work[post_col].astype(int)
    work["_did"] = work["_treated_num"] * work["_post_num"]

    rhs = ["C(" + unit_col + ")", "C(" + time_col + ")", "_did"] + list(covariates or [])
    if cluster_col is not None:
        _validate_column(df, cluster_col)
    spec: dict[str, object] = {
        "cov_type": "cluster",
        "cov_group": cluster_col if cluster_col is not None else unit_col,
    }
    cov_kwargs = _cov_kwargs(work, spec)
    model = smf.ols(f"{outcome} ~ " + " + ".join(rhs), data=work).fit(**cov_kwargs)

    if "_did" not in model.params.index:
        raise CausalError(
            "the DiD interaction was not estimable; check that there are treated units "
            "with post-treatment observations."
        )
    estimate = float(model.params["_did"])
    se = float(model.bse["_did"])
    lo = float(model.conf_int().loc["_did", 0])
    hi = float(model.conf_int().loc["_did", 1])
    p_value = float(model.pvalues["_did"])

    n_units_treated = int(work.loc[work["_treated_num"] == 1, unit_col].nunique())
    n_units_control = int(work.loc[work["_treated_num"] == 0, unit_col].nunique())
    pre_trend_p = _pre_trend_p(
        work,
        outcome=outcome,
        unit_col=unit_col,
        time_col=time_col,
        treated_col="_treated_num",
        post_col="_post_num",
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
