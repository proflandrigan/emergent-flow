"""Tests for emergentflow.clean.derive (Epic 16, Story 6).

Covers ``ef.clean.derive_column``: computing derived columns from either an arithmetic
expression or a case-when spec, and the restricted ``ast``-based grammar
(``emergentflow.clean.expressions.validate_expression``) that pre-screens every expression
string before it reaches ``pandas.DataFrame.eval``.
"""

from __future__ import annotations

import pandas as pd
import pytest

from emergentflow.api import is_inspectable
from emergentflow.clean import CleanError, ColumnCollisionError, UnknownColumnError, derive_column
from emergentflow.clean.expressions import validate_expression


def _df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "revenue": [1500.0, 500.0, 50.0, 0.0],
            "cost": [500.0, 200.0, 20.0, 0.0],
            "region": ["us", "eu", "us", "eu"],
        }
    )


# -- Expression form ---------------------------------------------------------------


def test_derive_arithmetic() -> None:
    result = derive_column(_df(), columns=[{"name": "margin", "expr": "revenue - cost"}])
    assert list(result["margin"]) == [1000.0, 300.0, 30.0, 0.0]


def test_derive_is_non_mutating() -> None:
    df = _df()
    snapshot = df.copy()
    derive_column(df, columns=[{"name": "margin", "expr": "revenue - cost"}])
    pd.testing.assert_frame_equal(df, snapshot)


def test_derive_multiple_ordered() -> None:
    result = derive_column(
        _df(),
        columns=[
            {"name": "margin", "expr": "revenue - cost"},
            {"name": "double_margin", "expr": "margin * 2"},
        ],
    )
    assert list(result["margin"]) == [1000.0, 300.0, 30.0, 0.0]
    assert list(result["double_margin"]) == [2000.0, 600.0, 60.0, 0.0]


def test_derive_comparison_yields_boolean() -> None:
    result = derive_column(_df(), columns=[{"name": "big", "expr": "revenue > 100"}])
    assert list(result["big"]) == [True, True, False, False]


def test_derive_overwrite_guard() -> None:
    with pytest.raises(ColumnCollisionError, match="already exists"):
        derive_column(_df(), columns=[{"name": "revenue", "expr": "revenue * 2"}])


# -- Security / grammar (these are the important ones) -----------------------------


def test_derive_rejects_at_local_reference() -> None:
    with pytest.raises(CleanError):
        derive_column(_df(), columns=[{"name": "x", "expr": "revenue > @threshold"}])


def test_derive_rejects_function_call() -> None:
    with pytest.raises(CleanError, match="unsupported syntax"):
        derive_column(_df(), columns=[{"name": "x", "expr": "abs(revenue)"}])


def test_derive_rejects_attribute_access() -> None:
    with pytest.raises(CleanError, match="unsupported syntax"):
        derive_column(_df(), columns=[{"name": "x", "expr": "revenue.__class__"}])


def test_derive_rejects_dunder_reach() -> None:
    with pytest.raises(CleanError):
        derive_column(_df(), columns=[{"name": "x", "expr": "revenue.__class__.__bases__"}])


def test_derive_rejects_subscript() -> None:
    with pytest.raises(CleanError, match="unsupported syntax"):
        derive_column(_df(), columns=[{"name": "x", "expr": "revenue[0]"}])


def test_derive_rejects_lambda() -> None:
    with pytest.raises(CleanError):
        derive_column(_df(), columns=[{"name": "x", "expr": "lambda x: x"}])


def test_derive_rejects_unknown_column() -> None:
    with pytest.raises(UnknownColumnError, match="unknown column"):
        derive_column(_df(), columns=[{"name": "x", "expr": "revenue - nope"}])


def test_derive_rejects_empty_expression() -> None:
    with pytest.raises(CleanError):
        derive_column(_df(), columns=[{"name": "x", "expr": "  "}])


def test_validate_expression_accepts_literals() -> None:
    assert validate_expression("revenue > 0", available=["revenue"]) is None
    assert validate_expression("True", available=["revenue"]) is None
    assert validate_expression("None", available=["revenue"]) is None


# -- Case-when form -------------------------------------------------------------------


def test_derive_case_when_multi_branch() -> None:
    result = derive_column(
        _df(),
        columns=[
            {
                "name": "tier",
                "when": [
                    {"if": "revenue > 1000", "then": "gold"},
                    {"if": "revenue > 100", "then": "silver"},
                ],
                "else": "bronze",
            }
        ],
    )
    assert list(result["tier"]) == ["gold", "silver", "bronze", "bronze"]


def test_derive_case_when_first_match_wins() -> None:
    # The 1500-revenue row matches BOTH "revenue > 1000" and "revenue > 100"; the first
    # branch's value ("gold") must win, not the second's ("silver").
    result = derive_column(
        _df(),
        columns=[
            {
                "name": "tier",
                "when": [
                    {"if": "revenue > 1000", "then": "gold"},
                    {"if": "revenue > 100", "then": "silver"},
                ],
                "else": "bronze",
            }
        ],
    )
    assert result.loc[0, "tier"] == "gold"


def test_derive_case_when_default_none() -> None:
    result = derive_column(
        _df(),
        columns=[
            {
                "name": "tier",
                "when": [{"if": "revenue > 1000", "then": "gold"}],
            }
        ],
    )
    assert result.loc[0, "tier"] == "gold"
    assert pd.isna(result.loc[1, "tier"])
    assert pd.isna(result.loc[2, "tier"])
    assert pd.isna(result.loc[3, "tier"])


def test_derive_case_when_requires_boolean_condition() -> None:
    with pytest.raises(CleanError, match="boolean"):
        derive_column(_df(), columns=[{"name": "x", "when": [{"if": "revenue", "then": 1}]}])


def test_derive_case_when_empty_branches() -> None:
    with pytest.raises(CleanError):
        derive_column(_df(), columns=[{"name": "x", "when": []}])


def test_derive_case_when_validates_branch_expression() -> None:
    with pytest.raises(CleanError):
        derive_column(
            _df(),
            columns=[{"name": "x", "when": [{"if": "abs(revenue)", "then": 1}]}],
        )


# -- Spec validation ----------------------------------------------------------------


def test_derive_requires_exactly_one_form() -> None:
    with pytest.raises(CleanError, match="exactly one"):
        derive_column(
            _df(),
            columns=[
                {
                    "name": "x",
                    "expr": "revenue - cost",
                    "when": [{"if": "revenue > 0", "then": 1}],
                }
            ],
        )
    with pytest.raises(CleanError, match="exactly one"):
        derive_column(_df(), columns=[{"name": "x"}])


def test_derive_requires_name() -> None:
    with pytest.raises(CleanError):
        derive_column(_df(), columns=[{"expr": "revenue - cost"}])


def test_derive_empty_columns_raises() -> None:
    with pytest.raises(CleanError):
        derive_column(_df(), columns=[])


def test_derive_result_is_inspectable() -> None:
    result = derive_column(_df(), columns=[{"name": "margin", "expr": "revenue - cost"}])
    assert is_inspectable(result) is True
