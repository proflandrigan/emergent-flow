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
from sklearn.preprocessing import MultiLabelBinarizer

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
    "explode_lists",
    "encode_lists",
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
        if axis == "columns":
            raise ValueError("subset is only supported when axis='rows'.")
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
        if value is None:
            raise ValueError(
                f"operator {operator!r} requires a non-None value; got None. "
                "Use drop_missing() to filter on missing values."
            )
        mask = _COMPARATORS[operator](df[column], value)
    else:
        raise ValueError(f"unknown operator {operator!r}; expected one of {list(OPERATORS)!r}.")
    return df[mask].copy()


def _is_empty_list_cell(value: Any) -> bool:
    """True for a cell that will explode to a placeholder NaN row: an empty list-like, or a
    scalar missing value (None/NaN). A real ``None``/NaN *element inside* a non-empty list is
    not an empty cell and must not be treated as one."""
    if isinstance(value, (list, tuple, set)):
        return len(value) == 0
    return bool(pd.isna(value))


@public_op(name="ef.clean.explode_lists")
def explode_lists(
    df: pd.DataFrame,
    *,
    columns: list[str],
    drop_empty: bool = True,
    ignore_index: bool = True,
) -> pd.DataFrame:
    """Explode one or more list-valued columns into long rows, returning a NEW DataFrame.

    Thin wrapper over ``pandas.DataFrame.explode``. A single column turns each list element into
    its own row; multiple ``columns`` are exploded **together** (index-aligned / zipped, not
    cross-joined), which requires the lists in a given row to be the same length — pandas raises
    ``ValueError`` otherwise. Empty lists / missing values explode to a single NaN row; when
    ``drop_empty`` is True (default) those placeholder rows are dropped **before** exploding, so
    a genuine ``None``/NaN *element* inside an otherwise non-empty list is preserved as its own
    row rather than being mistaken for an empty-list placeholder. ``ignore_index`` renumbers the
    result 0..n-1. Never mutates the input.
    """
    if not columns:
        raise ValueError("columns must be a non-empty list of column names.")
    unknown = [c for c in columns if c not in df.columns]
    if unknown:
        raise ValueError(f"unknown columns {unknown!r}; expected one of {list(df.columns)!r}.")
    if drop_empty:
        is_empty = df[columns].apply(lambda col: col.map(_is_empty_list_cell))
        df = df[~is_empty.all(axis=1)]
    result = df.explode(columns if len(columns) > 1 else columns[0], ignore_index=False)
    result = result.reset_index(drop=True) if ignore_index else result.copy()
    return result


def _coerce_labels(value: Any, sep: str | None) -> list[Any]:
    """Normalise one cell into a list of labels for multi-hot encoding.

    Lists/tuples/sets pass through; a missing value (None/NaN) becomes the empty set; a string is
    split on ``sep`` when ``sep`` is given, else treated as a single label; any other scalar is a
    single label.
    """
    if isinstance(value, (list, tuple, set)):
        return list(value)
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    if sep is not None and isinstance(value, str):
        return [part for part in value.split(sep) if part != ""]
    return [value]


@public_op(name="ef.clean.encode_lists")
def encode_lists(
    df: pd.DataFrame,
    *,
    column: str,
    prefix: str | None = None,
    drop: bool = True,
    sep: str | None = None,
) -> pd.DataFrame:
    """Multi-hot encode a list-valued column into wide 0/1 indicator columns; returns a NEW frame.

    Thin wrapper over ``sklearn.preprocessing.MultiLabelBinarizer``. Each distinct label across
    ``column`` becomes an integer indicator column named ``f"{prefix}_{label}"`` (``prefix``
    defaults to ``column``), in sorted label order. Missing/empty cells encode as all-zeros. When
    ``sep`` is given, string cells are first split on it (e.g. ``"rock|jazz"`` with ``sep="|"``);
    otherwise cells are expected to already hold Python lists. ``drop`` removes the original
    ``column`` from the output. Row order and index are preserved. Never mutates the input.
    """
    if column not in df.columns:
        raise ValueError(f"unknown column {column!r}; expected one of {list(df.columns)!r}.")
    resolved_prefix = prefix if prefix is not None else column
    labels = [_coerce_labels(v, sep) for v in df[column]]
    binarizer = MultiLabelBinarizer()
    try:
        encoded = binarizer.fit_transform(labels)
    except TypeError as exc:
        raise ValueError(
            f"column {column!r} has labels of mixed, mutually unsortable types "
            f"(e.g. str and int); encode_lists requires every label to be of a "
            f"consistently comparable type."
        ) from exc
    indicator = pd.DataFrame(
        encoded,
        columns=[f"{resolved_prefix}_{cls}" for cls in binarizer.classes_],
        index=df.index,
        dtype=int,
    )
    base = df.drop(columns=[column]) if drop else df.copy()
    return pd.concat([base, indicator], axis=1)
