"""
emergentflow.clean.text_dates
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
String and date cleaning verbs (Epic 16, Story 8): clean_text, parse_dates.

Thin wrappers over pandas' ``.str`` and ``.dt`` accessors and ``pandas.to_datetime``. Neither
mutates its input; each returns a NEW DataFrame.
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from emergentflow.api import public_op

from .errors import CleanError, ColumnCollisionError, UnknownColumnError

TEXT_OPERATIONS = ("trim", "lower", "upper", "title", "replace", "extract", "split")
DATE_COMPONENTS = (
    "year",
    "month",
    "day",
    "dayofweek",
    "dayofyear",
    "quarter",
    "hour",
    "minute",
    "second",
)
DATE_ERRORS = ("raise", "coerce")


@public_op(name="ef.clean.clean_text")
def clean_text(
    df: pd.DataFrame,
    *,
    columns: list[str],
    operations: list[dict[str, Any]],
    suffix: str | None = None,
) -> pd.DataFrame:
    """Apply an ordered pipeline of text operations to each named column; returns a NEW frame.

    By default each column is cleaned in place *in the returned copy*, but when ``suffix`` is
    given the results are written to new columns named ``f"{column}{suffix}"``, leaving the
    originals intact. Text columns come back as pandas' nullable ``string`` dtype (the
    ``split`` operation is the exception — it yields object cells holding Python lists, ready
    for ``ef.clean.explode_lists``). ``split`` should therefore be the last operation in a
    pipeline. The input ``df`` is never mutated.

    Each entry in ``operations`` is a mapping shaped like one of:
    - ``{"op": "trim"}`` — strip leading/trailing whitespace
    - ``{"op": "lower"}`` / ``{"op": "upper"}`` / ``{"op": "title"}`` — case normalisation
    - ``{"op": "replace", "pattern": str, "replacement": str, "regex": bool (default True)}``
    - ``{"op": "extract", "pattern": str}`` — the first capture group of the regex
    - ``{"op": "split", "sep": str}`` — split into a list per cell
    """
    if not columns:
        raise CleanError("columns must be a non-empty list of column names.")
    unknown = [c for c in columns if c not in df.columns]
    if unknown:
        raise UnknownColumnError(
            f"unknown columns {unknown!r}; expected one of {list(df.columns)!r}."
        )
    if not operations:
        raise CleanError("operations must be a non-empty list of operation specs.")

    for spec in operations:
        if not isinstance(spec, dict):
            raise CleanError(f"each operation spec must be a mapping; got {type(spec).__name__}.")
        op = spec.get("op")
        if op not in TEXT_OPERATIONS:
            raise CleanError(
                f"unknown operation {op!r}; expected one of {list(TEXT_OPERATIONS)!r}."
            )
        if op == "replace" and ("pattern" not in spec or "replacement" not in spec):
            raise CleanError("operation 'replace' requires both a 'pattern' and a 'replacement'.")
        if op == "extract" and "pattern" not in spec:
            raise CleanError(
                "operation 'extract' requires a 'pattern' with at least one capture group."
            )
        if op == "split" and "sep" not in spec:
            raise CleanError("operation 'split' requires a 'sep'.")

    targets = [f"{col}{suffix}" if suffix else col for col in columns]
    if suffix:
        collisions = [t for t in targets if t in df.columns]
        if collisions:
            raise ColumnCollisionError(
                f"clean_text output column(s) {collisions!r} already exist in the frame; "
                "choose a different suffix."
            )

    result = df.copy()
    for column, target in zip(columns, targets, strict=True):
        series = result[column].astype("string")
        for spec in operations:
            series = _apply_text_op(series, spec)
        result[target] = series
    return result


def _apply_text_op(series: pd.Series, spec: dict[str, Any]) -> pd.Series:
    """Apply one text operation spec to ``series``, returning the transformed Series."""
    op = spec["op"]
    try:
        if op == "trim":
            return series.str.strip()
        if op == "lower":
            return series.str.lower()
        if op == "upper":
            return series.str.upper()
        if op == "title":
            return series.str.title()
        if op == "replace":
            return series.str.replace(
                spec["pattern"], spec["replacement"], regex=spec.get("regex", True)
            )
        if op == "extract":
            return series.str.extract(spec["pattern"], expand=False)
        return series.str.split(spec["sep"])
    except (re.error, ValueError) as exc:
        raise CleanError(f"text operation {spec['op']!r} failed: {exc}") from exc


@public_op(name="ef.clean.parse_dates")
def parse_dates(
    df: pd.DataFrame,
    *,
    columns: list[str],
    format: str | None = None,
    errors: str = "raise",
    components: list[str] | None = None,
) -> pd.DataFrame:
    """Convert each named column to datetime, returning a NEW DataFrame.

    Thin wrapper over ``pandas.to_datetime``, using an explicit ``format`` when given, else
    letting pandas infer. Then optionally extracts calendar components into **new** columns
    named ``f"{column}_{component}"``. ``errors="raise"`` fails on an unparseable value;
    ``errors="coerce"`` turns it into ``NaT``. The input ``df`` is never mutated.
    """
    if not columns:
        raise CleanError("columns must be a non-empty list of column names.")
    unknown = [c for c in columns if c not in df.columns]
    if unknown:
        raise UnknownColumnError(
            f"unknown columns {unknown!r}; expected one of {list(df.columns)!r}."
        )
    if errors not in DATE_ERRORS:
        raise CleanError(f"unknown errors {errors!r}; expected one of {list(DATE_ERRORS)!r}.")
    if components:
        unknown_components = [c for c in components if c not in DATE_COMPONENTS]
        if unknown_components:
            raise CleanError(
                f"unknown component(s) {unknown_components!r}; "
                f"expected one of {list(DATE_COMPONENTS)!r}."
            )

    generated = [f"{column}_{component}" for column in columns for component in (components or [])]
    collisions = [name for name in generated if name in df.columns]
    if collisions:
        raise ColumnCollisionError(
            f"parse_dates component column(s) {collisions!r} already exist in the frame; "
            "rename them or drop the colliding component."
        )

    result = df.copy()
    for column in columns:
        try:
            parsed = pd.to_datetime(result[column], format=format, errors=errors)
        except (ValueError, TypeError) as exc:
            raise CleanError(f"failed to parse column {column!r} as datetime: {exc}") from exc
        result[column] = parsed
        for component in components or []:
            result[f"{column}_{component}"] = getattr(parsed.dt, component)
    return result
