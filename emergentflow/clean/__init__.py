"""
emergentflow.clean
~~~~~~~~~~~~~~~~~
Cleaning / imputation operations (Epic 1, Story 8).

Thin wrappers over scikit-learn for filling missing values in tidy DataFrames.
Each public operation validates its inputs at the boundary (fail fast, clear
typed errors) and otherwise defers entirely to the underlying, trusted
library — no reimplementation, no hidden transformation.

See ``docs/public-api-conventions.md`` and ``docs/sdk-design-philosophy.md``.
"""

from __future__ import annotations

import pandas as pd
from sklearn.impute import SimpleImputer

from emergentflow.api import public_op

STRATEGIES = ["mean", "median", "most_frequent"]

__all__ = ["impute_missing", "STRATEGIES"]


@public_op(name="ef.clean.impute_missing")
def impute_missing(
    df: pd.DataFrame,
    *,
    strategy: str = "mean",
    columns: list[str] | None = None,
) -> pd.DataFrame:
    """Impute missing values column-wise, returning a NEW DataFrame.

    Thin wrapper over ``sklearn.impute.SimpleImputer``. The input ``df`` is never
    mutated.

    When ``columns`` is given, exactly those columns are imputed. When
    ``columns is None`` the target defaults to the columns the strategy can act
    on: every column for ``"most_frequent"``, but only the numeric columns for
    ``"mean"``/``"median"`` (which are undefined on non-numeric data). Explicitly
    naming a non-numeric column for a numeric strategy is the caller's choice and
    will surface scikit-learn's own error.
    """
    if strategy not in STRATEGIES:
        raise ValueError(f"unknown strategy {strategy!r}; expected one of {STRATEGIES!r}.")

    if columns is not None:
        target = columns
        unknown = [col for col in target if col not in df.columns]
        if unknown:
            raise ValueError(f"unknown columns {unknown!r}; expected one of {list(df.columns)!r}.")
    elif strategy == "most_frequent":
        target = list(df.columns)
    else:
        target = list(df.select_dtypes(include="number").columns)

    result = df.copy()
    if not target:
        return result
    imputer = SimpleImputer(strategy=strategy)
    result[target] = imputer.fit_transform(result[target])
    return result
