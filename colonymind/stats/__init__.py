"""
colonymind.stats
~~~~~~~~~~~~~~~~~
Statistical-analytics operations (Epic 1, Story 8).

Thin wrappers over Pingouin, chosen as the statistics backend precisely
because its tests already return clean, tidy ``DataFrame``s rather than
opaque result objects (see ``docs/sdk-design-philosophy.md``). Each public
operation validates its inputs at the boundary (fail fast, clear typed
errors) and otherwise defers entirely to the underlying, trusted library —
no reimplementation, no hidden transformation.

See ``docs/public-api-conventions.md`` and ``docs/sdk-design-philosophy.md``.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import pingouin as pg

from colonymind.api import public_op

__all__ = ["anova", "AnovaResult"]


@dataclass
class AnovaResult:
    """Structured, inspectable result of a one-way ANOVA.

    Attributes
    ----------
    f_statistic: the ANOVA F value.
    p_value: the uncorrected p-value (``p-unc``).
    effect_size: partial eta-squared (``np2``).
    summary: Pingouin's full tidy result table.
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

    Thin wrapper over ``pingouin.anova``. ``alpha`` is recorded for callers but
    does not change the computation (Pingouin reports the raw p-value).
    """
    if group_col not in df.columns:
        raise ValueError(f"unknown group_col {group_col!r}; expected one of {list(df.columns)!r}.")
    if value_col not in df.columns:
        raise ValueError(f"unknown value_col {value_col!r}; expected one of {list(df.columns)!r}.")

    table = pg.anova(data=df, dv=value_col, between=group_col, detailed=True)

    row = table.iloc[0]
    return AnovaResult(
        f_statistic=float(row["F"]),
        p_value=float(row["p_unc"]),
        effect_size=float(row["np2"]),
        summary=table,
    )
