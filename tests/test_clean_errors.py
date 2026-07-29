"""Tests for the ``emergentflow.clean`` typed error hierarchy.

Covers the ``CleanError`` root and its subclasses (``UnknownColumnError``,
``ColumnCollisionError``, ``MissingOptionalDependencyError``), and confirms the retrofit of
existing ``ef.clean`` operations to raise these typed errors is non-breaking: every failure is
still catchable as a plain ``ValueError``.
"""

from __future__ import annotations

import pandas as pd
import pytest

from emergentflow.clean import (
    CleanError,
    ColumnCollisionError,
    MissingOptionalDependencyError,
    UnknownColumnError,
    encode_lists,
    filter_rows,
    select_columns,
)


def test_clean_error_is_value_error() -> None:
    assert issubclass(CleanError, ValueError)


@pytest.mark.parametrize(
    "cls",
    [UnknownColumnError, ColumnCollisionError, MissingOptionalDependencyError],
)
def test_subclasses_root_at_clean_error(cls: type[CleanError]) -> None:
    assert issubclass(cls, CleanError)


def test_missing_optional_dependency_message() -> None:
    exc = MissingOptionalDependencyError("emergentflow[fuzzy]")
    assert exc.extra == "emergentflow[fuzzy]"
    assert "pip install emergentflow[fuzzy]" in str(exc)


def test_unknown_column_raised_by_select_columns() -> None:
    df = pd.DataFrame({"a": [1, 2]})
    with pytest.raises(UnknownColumnError):
        select_columns(df, columns=["nope"])


def test_column_collision_raised_by_encode_lists() -> None:
    df = pd.DataFrame({"u": [1, 2], "g_rock": [10, 20], "g": [["rock"], ["jazz"]]})
    with pytest.raises(ColumnCollisionError):
        encode_lists(df, column="g")


def test_clean_error_raised_by_filter_rows_unknown_operator() -> None:
    df = pd.DataFrame({"a": [1, 2]})
    with pytest.raises(CleanError):
        filter_rows(df, column="a", operator="nope", value=1)


def test_legacy_value_error_catch_still_works() -> None:
    df = pd.DataFrame({"a": [1, 2]})
    with pytest.raises(ValueError):
        select_columns(df, columns=["nope"])
