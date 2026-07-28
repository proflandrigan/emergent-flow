"""
emergentflow.clean.combine
~~~~~~~~~~~~~~~~~~~~~~~~~~
Row-combining and ordering verbs (Epic 16, Story 7): concat, deduplicate, sort.

Thin wrappers over ``pandas.concat`` / ``DataFrame.drop_duplicates`` / ``DataFrame.sort_values``.
None of them mutates its input; each returns a NEW DataFrame.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from emergentflow.api import public_op

from .errors import CleanError, ColumnCollisionError, UnknownColumnError

DEDUP_KEEP = ("first", "last", "none")
NA_POSITIONS = ("first", "last")


@public_op(name="ef.clean.concat")
def concat(
    frames: list[pd.DataFrame],
    *,
    source_column: str | None = None,
    keys: list[str] | None = None,
    ignore_index: bool = True,
) -> pd.DataFrame:
    """Row-wise union of two or more frames, returning a NEW DataFrame.

    Thin wrapper over ``pandas.concat``. The result is schema-aligned by column name:
    columns absent from a given input frame are filled with NaN for that frame's rows.
    When ``source_column`` is given, a new column of that name is added recording which
    input frame each row came from (``keys`` supplies the per-frame labels; default labels
    are ``"frame_0"``, ``"frame_1"``, ...). Never mutates any input.
    """
    if not isinstance(frames, list) or len(frames) < 2:
        raise CleanError(
            "concat requires a list of at least 2 DataFrames; got "
            f"{len(frames) if isinstance(frames, list) else type(frames).__name__}."
        )

    for i, frame in enumerate(frames):
        if not isinstance(frame, pd.DataFrame):
            raise CleanError(f"concat input {i} is not a DataFrame; got {type(frame).__name__}.")

    if keys is not None and len(keys) != len(frames):
        raise CleanError(
            f"keys must have one label per frame; got {len(keys)} keys for {len(frames)} frames."
        )
    labels = keys if keys is not None else [f"frame_{i}" for i in range(len(frames))]

    if source_column is not None:
        if any(source_column in frame.columns for frame in frames):
            raise ColumnCollisionError(
                f"source column {source_column!r} collides with an existing column in one of "
                "the input frames; choose a different source_column name."
            )
        tagged = [
            frame.assign(**{source_column: label})
            for frame, label in zip(frames, labels, strict=True)
        ]
    else:
        tagged = frames

    result = pd.concat(tagged, ignore_index=ignore_index, sort=False)
    if not ignore_index:
        result = result.copy()
    return result


@public_op(name="ef.clean.deduplicate")
def deduplicate(
    df: pd.DataFrame,
    *,
    subset: list[str] | None = None,
    keep: str = "first",
    ignore_index: bool = False,
) -> pd.DataFrame:
    """Drop duplicate rows, returning a NEW DataFrame.

    Thin wrapper over ``pandas.DataFrame.drop_duplicates``. ``subset`` limits which columns
    define a duplicate (default: all columns). ``keep="first"``/``"last"`` retains that
    occurrence; ``keep="none"`` drops every row that has any duplicate. The original index is
    preserved unless ``ignore_index=True`` (matching the existing ``filter_rows``/``semi_join``
    convention in this family). Never mutates the input.
    """
    if keep not in DEDUP_KEEP:
        raise CleanError(f"unknown keep {keep!r}; expected one of {list(DEDUP_KEEP)!r}.")

    if subset is not None:
        if not subset:
            raise CleanError("subset must be a non-empty list of column names.")
        unknown = [c for c in subset if c not in df.columns]
        if unknown:
            raise UnknownColumnError(
                f"unknown columns {unknown!r}; expected one of {list(df.columns)!r}."
            )

    pandas_keep: Any = False if keep == "none" else keep
    return df.drop_duplicates(subset=subset, keep=pandas_keep, ignore_index=ignore_index)


@public_op(name="ef.clean.sort")
def sort(
    df: pd.DataFrame,
    *,
    by: list[str],
    ascending: bool | list[bool] = True,
    na_position: str = "last",
    ignore_index: bool = False,
) -> pd.DataFrame:
    """Multi-key sort, returning a NEW DataFrame.

    Thin wrapper over ``pandas.DataFrame.sort_values``. ``ascending`` is either a single bool
    applied to every key or one bool per key. ``na_position`` places missing values first or
    last. The sort is **stable**, so rows that compare equal keep their original relative
    order. Never mutates the input.
    """
    if not by:
        raise CleanError("by must be a non-empty list of column names.")
    unknown = [c for c in by if c not in df.columns]
    if unknown:
        raise UnknownColumnError(
            f"unknown columns {unknown!r}; expected one of {list(df.columns)!r}."
        )
    if isinstance(ascending, list) and len(ascending) != len(by):
        raise CleanError(
            f"ascending must be a single bool or one bool per key; got {len(ascending)} "
            f"for {len(by)} keys."
        )
    if na_position not in NA_POSITIONS:
        raise CleanError(
            f"unknown na_position {na_position!r}; expected one of {list(NA_POSITIONS)!r}."
        )

    return df.sort_values(
        by=by,
        ascending=ascending,
        na_position=na_position,
        ignore_index=ignore_index,
        kind="stable",
    )
