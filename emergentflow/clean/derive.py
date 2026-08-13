"""
emergentflow.clean.derive
~~~~~~~~~~~~~~~~~~~~~~~~~
Derived-column computation (Epic 16, Story 6): arithmetic and case-when expressions.

Thin wrapper over ``pandas.DataFrame.eval`` and ``numpy.select``. Every expression string is
first validated by :func:`emergentflow.clean.expressions.validate_expression` before it is
handed to pandas — see that module's docstring for why the pre-screen exists. Never mutates
the input; always returns a NEW DataFrame.
"""

from __future__ import annotations

from typing import Any, cast

import numpy as np
import pandas as pd

from emergentflow.api import public_op

from .errors import CleanError, ColumnCollisionError
from .expressions import validate_expression

#: Literal types a case-when branch may produce. Values arrive from the IR, so they must be
#: JSON-native to survive the round trip.
_LITERAL_TYPES = (str, int, float, bool, type(None))


@public_op(name="ef.clean.derive_column")
def derive_column(
    df: pd.DataFrame,
    *,
    columns: list[dict[str, Any]],
) -> pd.DataFrame:
    """Compute one or more derived columns, returning a NEW DataFrame.

    ``columns`` is an ordered list of column specs; each spec is either an
    **expression** form ``{"name": ..., "expr": ...}`` or a **case-when** form
    ``{"name": ..., "when": [{"if": ..., "then": ...}, ...], "else": ...}``. Specs are
    applied in order, so a later spec may reference a column derived by an earlier one
    in the same call. The input ``df`` is never mutated.

    Every expression string (an ``"expr"`` or a branch ``"if"``) is first validated by
    :func:`emergentflow.clean.expressions.validate_expression` against a restricted
    grammar, and only then evaluated by ``pandas.DataFrame.eval`` — never by Python's
    builtin ``eval()``.
    """
    if not columns:
        raise CleanError("columns must be a non-empty list of column specs.")

    result = df.copy()
    for spec in columns:
        if not isinstance(spec, dict):
            raise CleanError(f"each column spec must be a mapping; got {type(spec).__name__}.")

        name = spec.get("name")
        if not isinstance(name, str) or not name:
            raise CleanError("each column spec requires a non-empty 'name'.")

        if name in result.columns:
            raise ColumnCollisionError(
                f"derived column {name!r} already exists in the frame; derive_column never "
                "overwrites an existing column — choose a different name."
            )

        has_expr = "expr" in spec
        has_when = "when" in spec
        if has_expr == has_when:
            raise CleanError(f"column spec {name!r} must have exactly one of 'expr' or 'when'.")

        if has_expr:
            validate_expression(spec["expr"], available=list(result.columns))
            series = _eval(result, spec["expr"])
        else:
            series = _case_when(result, name, spec)

        result[name] = series

    return result


def _eval(frame: pd.DataFrame, expr: str) -> Any:
    """Evaluate a pre-validated expression against *frame* via pandas' own evaluator.

    ``engine="python"`` is pinned deliberately: the default engine is numexpr when it is
    installed, and the two can differ in floating-point results, which would break the
    ADR-0002 equivalence gate between ``execute`` and compiled code on machines with
    differing optional dependencies. ``local_dict``/``global_dict`` are emptied so nothing
    from an enclosing Python scope can leak in even if the pre-screen were bypassed.
    """
    try:
        return frame.eval(expr, engine="python", parser="pandas", local_dict={}, global_dict={})
    except Exception as exc:  # noqa: BLE001 -- pandas raises many types; all mean "bad expression"
        raise CleanError(f"failed to evaluate expression {expr!r}: {exc}") from exc


def _case_when(frame: pd.DataFrame, name: str, spec: dict[str, Any]) -> Any:
    branches = spec["when"]
    if not isinstance(branches, list) or not branches:
        raise CleanError(
            f"column spec {name!r} has an empty 'when' list; provide at least one branch."
        )

    default: Any = spec.get("else")
    if not isinstance(default, _LITERAL_TYPES):
        raise CleanError(
            f"column spec {name!r} has a non-literal 'else' value; got {type(default).__name__}."
        )

    conditions: list[Any] = []
    choices: list[Any] = []
    for i, branch in enumerate(branches):
        if not isinstance(branch, dict) or "if" not in branch or "then" not in branch:
            raise CleanError(
                f"each 'when' branch of column spec {name!r} requires an 'if' expression and "
                "a 'then' value."
            )
        then = branch["then"]
        if not isinstance(then, _LITERAL_TYPES):
            raise CleanError(
                f"branch {i} of column spec {name!r} has a non-literal 'then' value; got "
                f"{type(then).__name__}."
            )

        validate_expression(branch["if"], available=list(frame.columns))
        mask = _eval(frame, branch["if"])
        if not isinstance(mask, pd.Series) or mask.dtype != bool:
            raise CleanError(
                f"branch condition {branch['if']!r} of column spec {name!r} must evaluate to a "
                "boolean condition over the frame's rows."
            )
        conditions.append(mask.to_numpy())
        choices.append(then)

    if len(frame) == 0:
        return pd.Series([], index=frame.index, dtype=object)

    # numpy.select needs a common dtype across choices + default. A spec mixing a string with
    # a numeric/bool literal has none, so numpy 2.x raises a bare TypeError ("Choicelist and
    # default value do not have a common dtype") -- e.g. choices [100, "unknown"] with else 0.
    # That is a legitimate case-when though (a numeric result with a string fallback label), so
    # force object dtype for the mixed case: every value then keeps its original Python type.
    # A single consistent type never hits the promotion, and None is already object-compatible.
    all_values: list[Any] = [*choices, default]
    has_str = any(isinstance(v, str) for v in all_values)
    has_non_str = any(not isinstance(v, str) and v is not None for v in all_values)
    has_bool = any(isinstance(v, bool) for v in all_values)
    is_mixed_bool = has_bool and any(v is not None and not isinstance(v, bool) for v in all_values)
    if (has_str and has_non_str) or is_mixed_bool:
        choices = [np.full(len(frame), choice, dtype=object) for choice in choices]
        default = np.array(default, dtype=object)

    # ``cast`` only undoes the isinstance narrowing above: numpy's stubs reject ``None`` as a
    # default, but it is a legitimate (and the default) case-when fallback at runtime.
    return np.select(conditions, choices, default=cast(Any, default))
