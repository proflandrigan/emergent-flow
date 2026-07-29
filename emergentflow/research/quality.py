"""
emergentflow.research.quality
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Data-quality gate (Epic 16, Story 19).

``check_data_quality`` runs a declarative list of expectations against a DataFrame -- non-null,
range, uniqueness, allowed-values, regex-match, row-count (optionally "vs upstream" via
``expected``/``tolerance``), and schema-on-load column/dtype checks (reusing
``emergentflow.data.contract.detect_schema_violations``, the same logic the loaders' schema
contract uses). Passing returns *frame* unchanged (non-mutating passthrough); failing raises a
typed :class:`~emergentflow.research.errors.DataQualityError` carrying a tidy violations frame,
so a caller can show exactly what failed rather than just an opaque message.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from emergentflow.api import public_op
from emergentflow.data.contract import detect_schema_violations
from emergentflow.research.errors import DataQualityError, ResearchError

__all__ = ["EXPECTATION_TYPES", "check_data_quality"]

EXPECTATION_TYPES = (
    "non_null",
    "range",
    "unique",
    "allowed_values",
    "regex_match",
    "row_count",
    "schema",
)


def _check_non_null(frame: pd.DataFrame, exp: dict[str, Any]) -> dict[str, Any] | None:
    column = exp["column"]
    null_count = int(frame[column].isna().sum())
    if null_count == 0:
        return None
    return {
        "expectation": "non_null",
        "column": column,
        "detail": f"{null_count} null value(s) found",
    }


def _check_range(frame: pd.DataFrame, exp: dict[str, Any]) -> dict[str, Any] | None:
    column = exp["column"]
    lo, hi = exp.get("min"), exp.get("max")
    series = frame[column]
    mask = pd.Series(False, index=series.index)
    if lo is not None:
        mask = mask | (series < lo)
    if hi is not None:
        mask = mask | (series > hi)
    bad = int(mask.sum())
    if bad == 0:
        return None
    return {
        "expectation": "range",
        "column": column,
        "detail": f"{bad} value(s) outside [{lo}, {hi}]",
    }


def _check_unique(frame: pd.DataFrame, exp: dict[str, Any]) -> dict[str, Any] | None:
    column = exp["column"]
    dup_count = int(frame[column].duplicated().sum())
    if dup_count == 0:
        return None
    return {
        "expectation": "unique",
        "column": column,
        "detail": f"{dup_count} duplicate value(s) found",
    }


def _check_allowed_values(frame: pd.DataFrame, exp: dict[str, Any]) -> dict[str, Any] | None:
    column = exp["column"]
    allowed = set(exp.get("values", []))
    bad = int((~frame[column].isin(allowed)).sum())
    if bad == 0:
        return None
    return {
        "expectation": "allowed_values",
        "column": column,
        "detail": f"{bad} value(s) not in {sorted(allowed, key=str)!r}",
    }


def _check_regex_match(frame: pd.DataFrame, exp: dict[str, Any]) -> dict[str, Any] | None:
    column = exp["column"]
    pattern = exp["pattern"]
    bad = int((~frame[column].astype(str).str.match(pattern)).sum())
    if bad == 0:
        return None
    return {
        "expectation": "regex_match",
        "column": column,
        "detail": f"{bad} value(s) not matching {pattern!r}",
    }


def _check_row_count(frame: pd.DataFrame, exp: dict[str, Any]) -> dict[str, Any] | None:
    n = len(frame)
    lo, hi = exp.get("min"), exp.get("max")
    expected = exp.get("expected")
    tolerance = exp.get("tolerance", 0)
    if expected is not None:
        lo, hi = expected - tolerance, expected + tolerance
    if (lo is not None and n < lo) or (hi is not None and n > hi):
        return {
            "expectation": "row_count",
            "column": None,
            "detail": f"row count {n} outside [{lo}, {hi}]",
        }
    return None


def _check_schema(frame: pd.DataFrame, exp: dict[str, Any]) -> list[dict[str, Any]]:
    result = detect_schema_violations(
        frame,
        expect_columns=exp.get("columns"),
        expect_dtypes=exp.get("dtypes"),
        allow_extra_columns=exp.get("allow_extra_columns", True),
    )
    found: list[dict[str, Any]] = []
    if result["missing"]:
        found.append(
            {
                "expectation": "schema",
                "column": None,
                "detail": f"missing columns: {result['missing']}",
            }
        )
    if result["extra"]:
        found.append(
            {
                "expectation": "schema",
                "column": None,
                "detail": f"unexpected columns: {result['extra']}",
            }
        )
    if result["mistyped"]:
        found.append(
            {
                "expectation": "schema",
                "column": None,
                "detail": f"mistyped columns: {result['mistyped']}",
            }
        )
    return found


_SINGLE_VIOLATION_CHECKS = {
    "non_null": _check_non_null,
    "range": _check_range,
    "unique": _check_unique,
    "allowed_values": _check_allowed_values,
    "regex_match": _check_regex_match,
    "row_count": _check_row_count,
}

#: Expectation types whose dict carries a ``"column"`` key that must name a real column
#: (i.e. every check above except frame-scoped ``"row_count"``). ``"schema"`` is excluded
#: too: reporting missing columns is precisely what it is for.
_COLUMN_SCOPED_CHECKS = frozenset(_SINGLE_VIOLATION_CHECKS) - {"row_count"}


@public_op(name="ef.research.check_data_quality")
def check_data_quality(frame: pd.DataFrame, expectations: list[dict[str, Any]]) -> pd.DataFrame:
    """Run *expectations* against *frame*; return it unchanged on pass, raise on fail.

    Parameters
    ----------
    frame:
        The DataFrame to check. Never mutated -- returned as-is on a passing check.
    expectations:
        An ordered list of expectation dicts, each with a ``"type"`` key naming one of
        :data:`EXPECTATION_TYPES` plus type-specific keys:

        - ``{"type": "non_null", "column": str}``
        - ``{"type": "range", "column": str, "min": number | None, "max": number | None}``
        - ``{"type": "unique", "column": str}``
        - ``{"type": "allowed_values", "column": str, "values": list}``
        - ``{"type": "regex_match", "column": str, "pattern": str}``
        - ``{"type": "row_count", "min": int | None, "max": int | None}`` OR
          ``{"type": "row_count", "expected": int, "tolerance": int}`` (the "row-count delta
          vs upstream" form: pass the upstream frame's row count as ``expected``).
        - ``{"type": "schema", "columns": list[str] | None, "dtypes": dict[str, str] | None,
          "allow_extra_columns": bool}`` -- reuses the Story 4 schema-on-load contract
          (:func:`emergentflow.data.contract.detect_schema_violations`).

        All expectations are checked (not short-circuited on the first failure), so every
        violation is reported together in one error.

    Returns
    -------
    pd.DataFrame
        *frame*, unchanged, when every expectation passes.

    Raises
    ------
    DataQualityError
        If any expectation fails. Carries a tidy violations frame (columns: ``expectation``,
        ``column``, ``detail``) as ``exc.violations``, one row per violation found.
    ResearchError
        If an expectation dict names a ``"type"`` not in :data:`EXPECTATION_TYPES`, or if a
        column-scoped expectation names a ``"column"`` that is not in *frame*.
    """
    violations: list[dict[str, Any]] = []

    for exp in expectations:
        etype = exp.get("type")
        if etype not in EXPECTATION_TYPES:
            raise ResearchError(
                f"unknown expectation type {etype!r}; expected one of {EXPECTATION_TYPES!r}."
            )
        # Every column-scoped check indexes `frame[column]` directly, which raises a bare,
        # undocumented `KeyError` for a column that isn't there -- opaque next to this
        # module's own typed errors and out of step with the rest of the SDK (clean's
        # UnknownColumnError, stats' "unknown columns [...]; expected one of [...]"). Reject
        # it up front with the same shape. "row_count" is frame-scoped and "schema" reports
        # missing columns as violations, so neither carries a "column" to check.
        if etype in _COLUMN_SCOPED_CHECKS:
            column = exp.get("column")
            if column not in frame.columns:
                raise ResearchError(
                    f"expectation {etype!r} names unknown column {column!r}; "
                    f"expected one of {list(frame.columns)!r}."
                )
        if etype == "schema":
            violations.extend(_check_schema(frame, exp))
        else:
            result = _SINGLE_VIOLATION_CHECKS[etype](frame, exp)
            if result is not None:
                violations.append(result)

    if not violations:
        return frame

    violations_frame = pd.DataFrame(violations, columns=["expectation", "column", "detail"])
    raise DataQualityError(
        f"data quality check failed: {len(violations)} violation(s) found",
        violations=violations_frame,
    )
