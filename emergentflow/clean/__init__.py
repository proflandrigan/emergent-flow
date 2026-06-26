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

import operator as _op
from typing import Any

import pandas as pd
from sklearn.impute import SimpleImputer

from emergentflow.api import public_op

STRATEGIES = ["mean", "median", "most_frequent"]
AXES = {"rows": 0, "columns": 1}
HOWS = ("any", "all")
OPERATORS = ("==", "!=", "<", "<=", ">", ">=", "isin")
_COMPARATORS = {
    "==": _op.eq,
    "!=": _op.ne,
    "<": _op.lt,
    "<=": _op.le,
    ">": _op.gt,
    ">=": _op.ge,
}

__all__ = [
    "impute_missing",
    "drop_missing",
    "select_columns",
    "cast_types",
    "filter_rows",
    "STRATEGIES",
    "OPERATORS",
]


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


@public_op(name="ef.clean.drop_missing")
def drop_missing(
    df: pd.DataFrame,
    *,
    axis: str = "rows",
    how: str = "any",
    subset: list[str] | None = None,
) -> pd.DataFrame:
    """Drop rows (or columns) containing missing values, returning a NEW DataFrame.

    Thin wrapper over ``pandas.DataFrame.dropna``. ``axis="rows"`` drops rows with NA;
    ``axis="columns"`` drops columns. ``how="any"`` drops if any cell is NA; ``how="all"``
    only if all are. ``subset`` (row-axis only) limits which columns are considered.
    """
    if axis not in AXES:
        raise ValueError(f"unknown axis {axis!r}; expected one of {list(AXES)!r}.")
    if how not in HOWS:
        raise ValueError(f"unknown how {how!r}; expected one of {list(HOWS)!r}.")
    if subset is not None:
        unknown = [c for c in subset if c not in df.columns]
        if unknown:
            raise ValueError(f"unknown columns {unknown!r}; expected one of {list(df.columns)!r}.")
    return df.dropna(axis=AXES[axis], how=how, subset=subset)


@public_op(name="ef.clean.select_columns")
def select_columns(
    df: pd.DataFrame,
    *,
    columns: list[str],
    drop: bool = False,
) -> pd.DataFrame:
    """Keep (or drop) a subset of columns, returning a NEW DataFrame.

    Thin wrapper over pandas column selection. With ``drop=False`` (default) the result
    contains exactly ``columns`` in the given order; with ``drop=True`` those columns are
    removed and the rest kept in their original order. Never mutates the input.
    """
    if not columns:
        raise ValueError("columns must be a non-empty list of column names.")
    unknown = [c for c in columns if c not in df.columns]
    if unknown:
        raise ValueError(f"unknown columns {unknown!r}; expected one of {list(df.columns)!r}.")
    if drop:
        keep = [c for c in df.columns if c not in set(columns)]
        return df[keep].copy()
    return df[list(columns)].copy()


CAST_DTYPES = ("int", "float", "str", "bool", "category")


@public_op(name="ef.clean.cast_types")
def cast_types(
    df: pd.DataFrame,
    *,
    dtypes: dict[str, str],
) -> pd.DataFrame:
    """Cast selected columns to new dtypes, returning a NEW DataFrame.

    Thin wrapper over ``pandas.DataFrame.astype``. ``dtypes`` maps column name -> dtype token,
    each token one of ``int``/``float``/``str``/``bool``/``category``. Never mutates the input.
    """
    if not dtypes:
        raise ValueError("dtypes must be a non-empty mapping of column -> dtype.")
    unknown_cols = [c for c in dtypes if c not in df.columns]
    if unknown_cols:
        raise ValueError(f"unknown columns {unknown_cols!r}; expected one of {list(df.columns)!r}.")
    bad = {c: t for c, t in dtypes.items() if t not in CAST_DTYPES}
    if bad:
        raise ValueError(f"unknown dtype(s) {bad!r}; expected one of {list(CAST_DTYPES)!r}.")
    return df.astype(dtypes)


@public_op(name="ef.clean.filter_rows")
def filter_rows(
    df: pd.DataFrame,
    *,
    column: str,
    operator: str = "==",
    value: Any = None,
) -> pd.DataFrame:
    """Keep rows where ``column`` satisfies ``operator`` against ``value`` — returns a NEW frame.

    A single structured predicate (no expression strings). ``operator`` is one of
    ``== != < <= > >=`` (scalar ``value``) or ``isin`` (``value`` must be a list/tuple). The input
    is never mutated.
    """
    if column not in df.columns:
        raise ValueError(f"unknown column {column!r}; expected one of {list(df.columns)!r}.")
    if operator == "isin":
        if not isinstance(value, (list, tuple)):
            raise ValueError(f"operator 'isin' requires a list value; got {type(value).__name__}.")
        mask = df[column].isin(list(value))
    elif operator in _COMPARATORS:
        mask = _COMPARATORS[operator](df[column], value)
    else:
        raise ValueError(f"unknown operator {operator!r}; expected one of {list(OPERATORS)!r}.")
    return df[mask].copy()
