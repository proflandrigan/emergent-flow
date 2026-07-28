"""Tests for emergentflow.clean.reshaping (Epic 16, Story 5).

Covers ``ef.clean.reshape``: a thin wrapper over ``pandas.DataFrame.pivot`` /
``pivot_table`` / ``melt`` for long<->wide conversion, which flattens the pivot
result back to a flat-column, tidy DataFrame and never mutates its input.
"""

from __future__ import annotations

import pandas as pd
import pytest

from emergentflow.api import is_inspectable
from emergentflow.clean import CleanError, ColumnCollisionError, UnknownColumnError, reshape


def _long_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": ["2024-01-01", "2024-01-01", "2024-01-02", "2024-01-02"],
            "metric": ["clicks", "views", "clicks", "views"],
            "amount": [3, 10, 5, 12],
        }
    )


def _long_df_with_duplicates() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": ["2024-01-01", "2024-01-01", "2024-01-01", "2024-01-02"],
            "metric": ["clicks", "clicks", "views", "clicks"],
            "amount": [3, 4, 10, 5],
        }
    )


def _wide_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": ["2024-01-01", "2024-01-02"],
            "clicks": [3, 5],
            "views": [10, 12],
        }
    )


def test_pivot_long_to_wide() -> None:
    df = _long_df()
    result = reshape(df, mode="pivot", index=["date"], columns=["metric"], values=["amount"])
    # A list-valued ``values`` keeps pandas' value level, so flattening prefixes each output
    # column with the value column it came from -- unambiguous, and the only correct naming
    # once more than one value column is pivoted at a time.
    assert list(result.columns) == ["date", "amount_clicks", "amount_views"]
    row0 = result[result["date"] == "2024-01-01"].iloc[0]
    row1 = result[result["date"] == "2024-01-02"].iloc[0]
    assert row0["amount_clicks"] == 3
    assert row0["amount_views"] == 10
    assert row1["amount_clicks"] == 5
    assert row1["amount_views"] == 12


def test_pivot_is_non_mutating() -> None:
    df = _long_df()
    snapshot = df.copy()
    reshape(df, mode="pivot", index=["date"], columns=["metric"], values=["amount"])
    pd.testing.assert_frame_equal(df, snapshot)


def test_pivot_output_has_flat_columns() -> None:
    df = _long_df()
    result = reshape(df, mode="pivot", index=["date"], columns=["metric"], values=["amount"])
    assert not isinstance(result.columns, pd.MultiIndex)
    assert all(isinstance(c, str) for c in result.columns)


def test_pivot_duplicate_index_without_aggfunc_raises() -> None:
    df = _long_df_with_duplicates()
    with pytest.raises(CleanError, match="aggfunc"):
        reshape(df, mode="pivot", index=["date"], columns=["metric"], values=["amount"])


def test_pivot_duplicate_index_with_aggfunc_aggregates() -> None:
    df = _long_df_with_duplicates()
    result = reshape(
        df,
        mode="pivot",
        index=["date"],
        columns=["metric"],
        values=["amount"],
        aggfunc="sum",
    )
    row0 = result[result["date"] == "2024-01-01"].iloc[0]
    assert row0["amount_clicks"] == 7


def test_pivot_unknown_column_raises() -> None:
    df = _long_df()
    with pytest.raises(UnknownColumnError, match="unknown columns"):
        reshape(df, mode="pivot", index=["nope"], columns=["metric"], values=["amount"])


def test_pivot_unknown_aggfunc_raises() -> None:
    df = _long_df()
    with pytest.raises(CleanError, match="unknown aggfunc"):
        reshape(
            df,
            mode="pivot",
            index=["date"],
            columns=["metric"],
            values=["amount"],
            aggfunc="bogus",
        )


def test_pivot_requires_index_and_columns() -> None:
    df = _long_df()
    with pytest.raises(CleanError):
        reshape(df, mode="pivot", index=None, columns=["metric"], values=["amount"])
    with pytest.raises(CleanError):
        reshape(df, mode="pivot", index=["date"], columns=None, values=["amount"])


def test_melt_wide_to_long() -> None:
    df = _wide_df()
    result = reshape(df, mode="melt", id_vars=["date"], value_vars=["clicks", "views"])
    assert result.shape == (4, 3)
    assert "variable" in result.columns
    assert "value" in result.columns
    assert set(result["variable"]) == {"clicks", "views"}
    assert set(result["value"]) == {3, 5, 10, 12}


def test_melt_custom_names() -> None:
    df = _wide_df()
    result = reshape(
        df,
        mode="melt",
        id_vars=["date"],
        value_vars=["clicks", "views"],
        var_name="metric",
        value_name="amount",
    )
    assert "metric" in result.columns
    assert "amount" in result.columns


def test_melt_is_non_mutating() -> None:
    df = _wide_df()
    snapshot = df.copy()
    reshape(df, mode="melt", id_vars=["date"], value_vars=["clicks", "views"])
    pd.testing.assert_frame_equal(df, snapshot)


def test_melt_name_collision_raises() -> None:
    df = _wide_df()
    with pytest.raises(ColumnCollisionError, match="collide"):
        reshape(
            df,
            mode="melt",
            id_vars=["date"],
            value_vars=["clicks", "views"],
            var_name="date",
        )


def test_melt_unknown_column_raises() -> None:
    df = _wide_df()
    with pytest.raises(UnknownColumnError):
        reshape(df, mode="melt", id_vars=["nope"], value_vars=["clicks"])


def test_unknown_mode_raises() -> None:
    df = _wide_df()
    with pytest.raises(CleanError, match="unknown mode"):
        reshape(df, mode="bogus")


def test_reshape_result_is_inspectable() -> None:
    pivot_result = reshape(
        _long_df(), mode="pivot", index=["date"], columns=["metric"], values=["amount"]
    )
    melt_result = reshape(_wide_df(), mode="melt", id_vars=["date"], value_vars=["clicks", "views"])
    assert is_inspectable(pivot_result) is True
    assert is_inspectable(melt_result) is True
