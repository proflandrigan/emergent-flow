"""
emergentflow.clean.reshaping
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reshape verbs (Epic 16, Story 5): long<->wide conversion.

Thin wrapper over ``pandas.DataFrame.pivot`` / ``pivot_table`` / ``melt``. Never mutates the
input; always returns a NEW, flat, tidy DataFrame.
"""

from __future__ import annotations

import pandas as pd

from emergentflow.api import public_op

from .errors import CleanError, ColumnCollisionError, UnknownColumnError

RESHAPE_MODES = ("pivot", "melt")
PIVOT_AGGFUNCS = ("mean", "sum", "count", "min", "max", "median", "first", "last")


@public_op(name="ef.clean.reshape")
def reshape(
    df: pd.DataFrame,
    *,
    mode: str = "pivot",
    index: list[str] | None = None,
    columns: list[str] | None = None,
    values: list[str] | None = None,
    aggfunc: str | None = None,
    id_vars: list[str] | None = None,
    value_vars: list[str] | None = None,
    var_name: str = "variable",
    value_name: str = "value",
) -> pd.DataFrame:
    """Reshape a DataFrame long<->wide, returning a NEW DataFrame.

    ``mode="pivot"`` (long -> wide) is a thin wrapper over ``pandas.DataFrame.pivot``
    (when ``aggfunc is None``) or ``pandas.DataFrame.pivot_table`` (when ``aggfunc`` is
    given, to aggregate duplicate index/columns combinations). The raw pandas result is a
    MultiIndex frame; this op always **flattens** it back to a flat-column, tidy
    DataFrame with a fresh ``RangeIndex`` before returning, so the output renders cleanly
    on the canvas and round-trips through JSON.

    ``mode="melt"`` (wide -> long) is a thin wrapper over ``pandas.DataFrame.melt``.

    The input ``df`` is never mutated; a NEW DataFrame is always returned.
    """
    if mode not in RESHAPE_MODES:
        raise CleanError(f"unknown mode {mode!r}; expected one of {list(RESHAPE_MODES)!r}.")

    if mode == "pivot":
        return _pivot(
            df,
            index=index,
            columns=columns,
            values=values,
            aggfunc=aggfunc,
        )

    return _melt(
        df,
        id_vars=id_vars,
        value_vars=value_vars,
        var_name=var_name,
        value_name=value_name,
    )


def _pivot(
    df: pd.DataFrame,
    *,
    index: list[str] | None,
    columns: list[str] | None,
    values: list[str] | None,
    aggfunc: str | None,
) -> pd.DataFrame:
    if not index:
        raise CleanError("pivot requires a non-empty 'index' list of column names.")
    if not columns:
        raise CleanError("pivot requires a non-empty 'columns' list of column names.")

    named = list(index) + list(columns) + list(values or [])
    seen: set[str] = set()
    unknown = []
    for col in named:
        if col not in df.columns and col not in seen:
            unknown.append(col)
            seen.add(col)
    if unknown:
        raise UnknownColumnError(
            f"unknown columns {unknown!r}; expected one of {list(df.columns)!r}."
        )

    if aggfunc is not None and aggfunc not in PIVOT_AGGFUNCS:
        raise CleanError(f"unknown aggfunc {aggfunc!r}; expected one of {list(PIVOT_AGGFUNCS)!r}.")

    if aggfunc is None:
        try:
            result = df.pivot(index=index, columns=columns, values=values)
        except ValueError as exc:
            if "duplicate" in str(exc):
                raise CleanError(
                    "pivot found duplicate entries for the given index/columns combination, "
                    "so the reshape is ambiguous; pass an 'aggfunc' (one of "
                    f"{list(PIVOT_AGGFUNCS)!r}) to aggregate the duplicates instead."
                ) from exc
            raise CleanError(str(exc)) from exc
    else:
        result = df.pivot_table(index=index, columns=columns, values=values, aggfunc=aggfunc)

    result = result.reset_index()
    if isinstance(result.columns, pd.MultiIndex):
        result.columns = [
            "_".join(str(part) for part in tup if str(part) != "") for tup in result.columns
        ]
    else:
        result.columns = [str(c) for c in result.columns]
    result.columns.name = None

    # Unlike melt's var_name/value_name, pivot's output column names are only known after
    # flattening (they're built from the runtime values found in 'columns'), so this collision
    # check has to run post-hoc rather than as a pre-flight -- but the guarantee is the same one
    # ColumnCollisionError provides everywhere else in this family: never silently produce
    # duplicate-labeled output columns.
    seen_names: set[str] = set()
    duplicates: list[str] = []
    for name in result.columns:
        if name in seen_names and name not in duplicates:
            duplicates.append(name)
        seen_names.add(name)
    if duplicates:
        raise ColumnCollisionError(
            f"pivot produced duplicate output column name(s) {duplicates!r} after flattening; "
            "rename the colliding index/columns/values so every output column name is unique."
        )

    return result.reset_index(drop=True)


def _melt(
    df: pd.DataFrame,
    *,
    id_vars: list[str] | None,
    value_vars: list[str] | None,
    var_name: str,
    value_name: str,
) -> pd.DataFrame:
    named = list(id_vars or []) + list(value_vars or [])
    unknown = []
    seen: set[str] = set()
    for col in named:
        if col not in df.columns and col not in seen:
            unknown.append(col)
            seen.add(col)
    if unknown:
        raise UnknownColumnError(
            f"unknown columns {unknown!r}; expected one of {list(df.columns)!r}."
        )

    collisions = [name for name in (var_name, value_name) if name in (id_vars or [])]
    collisions += [name for name in (var_name, value_name) if name in (value_vars or [])]
    if var_name == value_name and var_name not in collisions:
        collisions.append(var_name)
    if collisions:
        raise ColumnCollisionError(
            f"melt output column(s) {list(dict.fromkeys(collisions))!r} collide with an id_vars/"
            "value_vars column or with each other; choose a different var_name/value_name."
        )

    result = df.melt(
        id_vars=id_vars, value_vars=value_vars, var_name=var_name, value_name=value_name
    )
    return result.reset_index(drop=True)
