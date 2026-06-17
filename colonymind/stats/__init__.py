"""
colonymind.stats
~~~~~~~~~~~~~~~~~
Statistical-analytics operations (Epic 1, Story 8).

Thin wrappers over statsmodels, a BSD-3-Clause library chosen as the statistics
backend because its results are returned as clean, tidy ``DataFrame``s (e.g.
``anova_lm``) rather than opaque result objects (see
``docs/sdk-design-philosophy.md``). Each public operation validates its inputs
at the boundary (fail fast, clear typed errors) and otherwise defers entirely to
the underlying, trusted library — no reimplementation, no hidden transformation.

See ``docs/public-api-conventions.md`` and ``docs/sdk-design-philosophy.md``.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import statsmodels.api as sm
from statsmodels.formula.api import ols

from colonymind.api import public_op

__all__ = ["anova", "AnovaResult"]


@dataclass
class AnovaResult:
    """Structured, inspectable result of a one-way ANOVA.

    Attributes
    ----------
    f_statistic: the ANOVA F value.
    p_value: the uncorrected p-value.
    effect_size: partial eta-squared.
    summary: statsmodels' full tidy ANOVA result table.
    """

    f_statistic: float
    p_value: float
    effect_size: float
    summary: pd.DataFrame


@public_op(name="cm.stats.anova")
def anova(
    df: pd.DataFrame,
    *,
    group_col: str,
    value_col: str,
    alpha: float = 0.05,
) -> AnovaResult:
    """Perform a one-way ANOVA of ``value_col`` across groups in ``group_col``.

    Thin wrapper over ``statsmodels`` (OLS + ``anova_lm``). ``alpha`` is recorded
    for callers but does not change the computation (the raw p-value is reported).
    """
    if group_col not in df.columns:
        raise ValueError(f"unknown group_col {group_col!r}; expected one of {list(df.columns)!r}.")
    if value_col not in df.columns:
        raise ValueError(f"unknown value_col {value_col!r}; expected one of {list(df.columns)!r}.")

    # Rename to fixed, safe tokens so arbitrary column names (spaces, dots,
    # reserved words) cannot break the patsy/statsmodels formula parser.
    work = df[[group_col, value_col]].rename(columns={value_col: "_dv", group_col: "_grp"})
    model = ols("_dv ~ C(_grp)", data=work).fit()
    table = sm.stats.anova_lm(model, typ=2)

    effect = table.loc["C(_grp)"]
    effect_ss = float(effect["sum_sq"])
    resid_ss = float(table.loc["Residual", "sum_sq"])
    partial_eta_sq = effect_ss / (effect_ss + resid_ss)

    return AnovaResult(
        f_statistic=float(effect["F"]),
        p_value=float(effect["PR(>F)"]),
        effect_size=partial_eta_sq,
        summary=table,
    )
