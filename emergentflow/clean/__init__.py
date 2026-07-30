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

from .combine import DEDUP_KEEP, NA_POSITIONS, concat, deduplicate, sort
from .derive import derive_column
from .errors import (
    CleanError,
    ColumnCollisionError,
    MissingOptionalDependencyError,
    UnknownColumnError,
)
from .outliers import detect_outliers
from .pii import DEFAULT_MASK, PII_CATEGORIES, PRESIDIO_ENTITY_MAP, REDACT_ENGINES, redact_pii
from .reshaping import PIVOT_AGGFUNCS, RESHAPE_MODES, reshape
from .sampling import FUZZY_HOWS, FUZZY_SCORERS, SAMPLE_MODES, fuzzy_join, sample_rows
from .text_dates import DATE_COMPONENTS, DATE_ERRORS, TEXT_OPERATIONS, clean_text, parse_dates

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
    "detect_outliers",
    "explode_lists",
    "encode_lists",
    "merge",
    "semi_join",
    "reshape",
    "derive_column",
    "concat",
    "deduplicate",
    "sort",
    "clean_text",
    "parse_dates",
    "sample_rows",
    "fuzzy_join",
    "redact_pii",
    "PII_CATEGORIES",
    "PRESIDIO_ENTITY_MAP",
    "REDACT_ENGINES",
    "DEFAULT_MASK",
    "TEXT_OPERATIONS",
    "DATE_COMPONENTS",
    "DATE_ERRORS",
    "STRATEGIES",
    "OPERATORS",
    "RESHAPE_MODES",
    "PIVOT_AGGFUNCS",
    "DEDUP_KEEP",
    "NA_POSITIONS",
    "SAMPLE_MODES",
    "FUZZY_SCORERS",
    "FUZZY_HOWS",
    "CleanError",
    "ColumnCollisionError",
    "MissingOptionalDependencyError",
    "UnknownColumnError",
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
        raise CleanError(f"unknown strategy {strategy!r}; expected one of {STRATEGIES!r}.")

    if columns is not None:
        target = columns
        unknown = [col for col in target if col not in df.columns]
        if unknown:
            raise UnknownColumnError(
                f"unknown columns {unknown!r}; expected one of {list(df.columns)!r}."
            )
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
        raise CleanError(f"unknown axis {axis!r}; expected one of {list(AXES)!r}.")
    if how not in HOWS:
        raise CleanError(f"unknown how {how!r}; expected one of {list(HOWS)!r}.")
    if subset is not None:
        if axis == "columns":
            raise CleanError("subset is only supported when axis='rows'.")
        unknown = [c for c in subset if c not in df.columns]
        if unknown:
            raise UnknownColumnError(
                f"unknown columns {unknown!r}; expected one of {list(df.columns)!r}."
            )
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
        raise CleanError("columns must be a non-empty list of column names.")
    unknown = [c for c in columns if c not in df.columns]
    if unknown:
        raise UnknownColumnError(
            f"unknown columns {unknown!r}; expected one of {list(df.columns)!r}."
        )
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
        raise CleanError("dtypes must be a non-empty mapping of column -> dtype.")
    unknown_cols = [c for c in dtypes if c not in df.columns]
    if unknown_cols:
        raise UnknownColumnError(
            f"unknown columns {unknown_cols!r}; expected one of {list(df.columns)!r}."
        )
    bad = {c: t for c, t in dtypes.items() if t not in CAST_DTYPES}
    if bad:
        raise CleanError(f"unknown dtype(s) {bad!r}; expected one of {list(CAST_DTYPES)!r}.")
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
        raise UnknownColumnError(
            f"unknown column {column!r}; expected one of {list(df.columns)!r}."
        )
    if operator == "isin":
        if not isinstance(value, (list, tuple)):
            raise CleanError(f"operator 'isin' requires a list value; got {type(value).__name__}.")
        mask = df[column].isin(list(value))
    elif operator in _COMPARATORS:
        if value is None:
            raise CleanError(
                f"operator {operator!r} requires a non-None value; got None. "
                "Use drop_missing() to filter on missing values."
            )
        mask = _COMPARATORS[operator](df[column], value)
    else:
        raise CleanError(f"unknown operator {operator!r}; expected one of {list(OPERATORS)!r}.")
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
        raise CleanError("columns must be a non-empty list of column names.")
    unknown = [c for c in columns if c not in df.columns]
    if unknown:
        raise UnknownColumnError(
            f"unknown columns {unknown!r}; expected one of {list(df.columns)!r}."
        )
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
    Raises ``ColumnCollisionError`` if a generated indicator column name collides with an
    existing column in the output (after ``drop``) instead of silently producing duplicate
    labels.
    """
    if column not in df.columns:
        raise UnknownColumnError(
            f"unknown column {column!r}; expected one of {list(df.columns)!r}."
        )
    resolved_prefix = prefix if prefix is not None else column
    labels = [_coerce_labels(v, sep) for v in df[column]]
    binarizer = MultiLabelBinarizer()
    try:
        encoded = binarizer.fit_transform(labels)
    except TypeError as exc:
        raise CleanError(
            f"column {column!r} has labels of mixed, mutually unsortable types "
            f"(e.g. str and int); encode_lists requires every label to be of a "
            f"consistently comparable type."
        ) from exc
    indicator_columns = [f"{resolved_prefix}_{cls}" for cls in binarizer.classes_]
    base = df.drop(columns=[column]) if drop else df.copy()
    collisions = [c for c in indicator_columns if c in base.columns]
    if collisions:
        raise ColumnCollisionError(
            f"generated indicator column(s) {collisions!r} collide with existing column(s) "
            f"in the input frame; choose a different prefix."
        )
    indicator = pd.DataFrame(
        encoded,
        columns=indicator_columns,
        index=df.index,
        dtype=int,
    )
    return pd.concat([base, indicator], axis=1)


_MERGE_HOWS = ("inner", "left", "right", "outer", "cross")


@public_op(name="ef.clean.merge")
def merge(
    left: pd.DataFrame,
    right: pd.DataFrame,
    *,
    on: list[str] | None = None,
    left_on: list[str] | None = None,
    right_on: list[str] | None = None,
    how: str = "inner",
    suffixes: tuple[str, str] = ("_x", "_y"),
    validate: str | None = None,
) -> pd.DataFrame:
    """Join two DataFrames on key column(s), returning a NEW DataFrame.

    Thin wrapper over ``pandas.DataFrame.merge``. Exactly one key spec is required
    (unless ``how="cross"``, which takes none): either ``on`` (column name(s) present
    in both frames) or ``left_on``/``right_on`` together (differently-named or
    composite keys — one list per side, equal length). ``how`` is one of
    ``inner``/``left``/``right``/``outer``/``cross``. ``suffixes`` disambiguates
    overlapping non-key column names between the two frames. ``validate``, when
    given, is one of ``"1:1"``/``"1:m"``/``"m:1"``/``"m:m"`` and is passed through
    to pandas, which raises if the declared relationship does not hold. Neither
    input is mutated.
    """
    if how not in _MERGE_HOWS:
        raise CleanError(f"unknown how {how!r}; expected one of {_MERGE_HOWS!r}.")

    if how == "cross":
        if on is not None or left_on is not None or right_on is not None:
            raise CleanError("cross join takes no key columns; on/left_on/right_on must be None.")
    else:
        if on is not None and (left_on is not None or right_on is not None):
            raise CleanError("pass either 'on' or 'left_on'/'right_on', not both.")
        if (left_on is None) != (right_on is None):
            raise CleanError("left_on and right_on must be given together.")
        if on is None and left_on is None:
            raise CleanError("must specify 'on' or 'left_on'/'right_on' (unless how='cross').")
        if on is not None and len(on) == 0:
            raise CleanError("'on' must be a non-empty list of column names.")
        if on is not None:
            unknown_left = [c for c in on if c not in left.columns]
            unknown_right = [c for c in on if c not in right.columns]
            if unknown_left:
                raise UnknownColumnError(
                    f"unknown column(s) {unknown_left!r} in left; "
                    f"expected one of {list(left.columns)!r}."
                )
            if unknown_right:
                raise UnknownColumnError(
                    f"unknown column(s) {unknown_right!r} in right; "
                    f"expected one of {list(right.columns)!r}."
                )
        else:
            assert left_on is not None and right_on is not None
            if len(left_on) == 0 or len(right_on) == 0:
                raise CleanError("'left_on'/'right_on' must be non-empty lists of column names.")
            if len(left_on) != len(right_on):
                raise CleanError(
                    f"left_on and right_on must be the same length; "
                    f"got {len(left_on)} and {len(right_on)}."
                )
            unknown_left = [c for c in left_on if c not in left.columns]
            unknown_right = [c for c in right_on if c not in right.columns]
            if unknown_left:
                raise UnknownColumnError(
                    f"unknown column(s) {unknown_left!r} in left; "
                    f"expected one of {list(left.columns)!r}."
                )
            if unknown_right:
                raise UnknownColumnError(
                    f"unknown column(s) {unknown_right!r} in right; "
                    f"expected one of {list(right.columns)!r}."
                )

    if suffixes is None or len(suffixes) != 2:
        raise CleanError(f"suffixes must be a 2-tuple/list of exactly 2 strings; got {suffixes!r}.")

    kwargs: dict[str, Any] = {
        "how": how,
        "suffixes": tuple(suffixes),
    }
    if validate is not None:
        kwargs["validate"] = validate
    if how != "cross":
        if on is not None:
            kwargs["on"] = on
        else:
            kwargs["left_on"] = left_on
            kwargs["right_on"] = right_on

    return left.merge(right, **kwargs)


_SEMI_JOIN_MODES = ("keep", "exclude")


@public_op(name="ef.clean.semi_join")
def semi_join(
    frame: pd.DataFrame,
    keys: pd.DataFrame,
    *,
    on: list[str] | None = None,
    left_on: list[str] | None = None,
    right_on: list[str] | None = None,
    mode: str = "keep",
) -> pd.DataFrame:
    """Filter ``frame``'s rows by key membership against ``keys``; returns a NEW DataFrame.

    A membership test, not a join: columns from ``keys`` are never added to the output,
    and duplicate key rows in ``keys`` never fan out rows in ``frame`` (each ``frame`` row
    appears at most once in the result). Exactly one key spec is required: either ``on``
    (column name(s) present in both frames) or ``left_on``/``right_on`` together
    (differently-named or composite keys — one list per side, equal length).
    ``mode="keep"`` (semi-join) keeps ``frame`` rows whose key tuple appears anywhere in
    ``keys``; ``mode="exclude"`` (anti-join) keeps rows whose key tuple does NOT appear.
    Neither ``frame`` nor ``keys`` is mutated; the original row order and index of
    ``frame`` are preserved.
    """
    if mode not in _SEMI_JOIN_MODES:
        raise CleanError(f"unknown mode {mode!r}; expected one of {_SEMI_JOIN_MODES!r}.")
    if on is not None and (left_on is not None or right_on is not None):
        raise CleanError("pass either 'on' or 'left_on'/'right_on', not both.")
    if (left_on is None) != (right_on is None):
        raise CleanError("left_on and right_on must be given together.")
    if on is None and left_on is None:
        raise CleanError("must specify 'on' or 'left_on'/'right_on'.")

    if on is not None:
        left_keys, right_keys = list(on), list(on)
    else:
        assert left_on is not None and right_on is not None
        left_keys, right_keys = list(left_on), list(right_on)
        if len(left_keys) != len(right_keys):
            raise CleanError(
                f"left_on and right_on must be the same length; "
                f"got {len(left_keys)} and {len(right_keys)}."
            )

    if not left_keys or not right_keys:
        raise CleanError("key column list(s) must be non-empty.")

    unknown_left = [c for c in left_keys if c not in frame.columns]
    if unknown_left:
        raise UnknownColumnError(
            f"unknown column(s) {unknown_left!r} in frame; expected one of {list(frame.columns)!r}."
        )
    unknown_right = [c for c in right_keys if c not in keys.columns]
    if unknown_right:
        raise UnknownColumnError(
            f"unknown column(s) {unknown_right!r} in keys; expected one of {list(keys.columns)!r}."
        )

    right_subset = keys[right_keys].drop_duplicates()
    temp_names = [f"__semi_join_key_{i}__" for i in range(len(right_keys))]
    right_subset = right_subset.rename(columns=dict(zip(right_keys, temp_names, strict=True)))

    probe = frame[left_keys].merge(
        right_subset,
        how="left",
        left_on=left_keys,
        right_on=temp_names,
        indicator="__semi_join_indicator__",
    )
    matched = (probe["__semi_join_indicator__"] == "both").to_numpy()
    keep_mask = matched if mode == "keep" else ~matched
    return frame[keep_mask].copy()
