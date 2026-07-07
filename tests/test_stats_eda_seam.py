"""Seam tests for the EDA wrapper functions in ``ef.stats`` (Epic 12, Story 11).

Covers the single seam every EDA node (Task 5) will route through: each function is a registered
public op, returns an inspectable/payload-round-trippable tidy DataFrame, never mutates its input,
raises typed errors on unknown columns/grouping keys, and produces a couple of hand-checkable
values.
"""

from __future__ import annotations

import pandas as pd
import pytest

from emergentflow.api import PUBLIC_OPS, is_inspectable
from emergentflow.server.payload import to_payload
from emergentflow.stats import (
    co_missingness,
    distribution_summary,
    group_by_aggregate,
    missingness,
    profile,
)


def _make_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "a": [1.0, 2.0, None],
            "b": ["x", "x", "y"],
            "c": [10.0, None, 30.0],
        }
    )


@pytest.mark.parametrize(
    "op_name",
    [
        "ef.stats.profile",
        "ef.stats.missingness",
        "ef.stats.co_missingness",
        "ef.stats.distribution_summary",
        "ef.stats.group_by_aggregate",
    ],
)
def test_is_registered_public_op(op_name):
    assert op_name in PUBLIC_OPS


def test_profile_is_inspectable_and_round_trips():
    df = _make_df()
    result = profile(df)
    assert isinstance(result, pd.DataFrame)
    assert is_inspectable(result)
    payload = to_payload(result)
    assert payload["kind"] == "table"
    assert list(result["column"]) == ["a", "b", "c"]


def test_missingness_is_inspectable_and_round_trips():
    df = _make_df()
    result = missingness(df)
    assert is_inspectable(result)
    payload = to_payload(result)
    assert payload["kind"] == "table"


def test_co_missingness_is_inspectable_and_round_trips():
    df = _make_df()
    result = co_missingness(df)
    assert is_inspectable(result)
    payload = to_payload(result)
    assert payload["kind"] == "table"


def test_distribution_summary_is_inspectable_and_round_trips():
    df = _make_df()
    result = distribution_summary(df)
    assert is_inspectable(result)
    payload = to_payload(result)
    assert payload["kind"] == "table"


def test_group_by_aggregate_is_inspectable_and_round_trips():
    df = _make_df()
    result = group_by_aggregate(df, by="b", agg="mean")
    assert is_inspectable(result)
    payload = to_payload(result)
    assert payload["kind"] == "table"


def test_profile_does_not_mutate_input():
    df = _make_df()
    before = df.copy(deep=True)
    profile(df)
    assert df.equals(before)


def test_missingness_does_not_mutate_input():
    df = _make_df()
    before = df.copy(deep=True)
    missingness(df)
    assert df.equals(before)


def test_co_missingness_does_not_mutate_input():
    df = _make_df()
    before = df.copy(deep=True)
    co_missingness(df)
    assert df.equals(before)


def test_distribution_summary_does_not_mutate_input():
    df = _make_df()
    before = df.copy(deep=True)
    distribution_summary(df)
    assert df.equals(before)


def test_group_by_aggregate_does_not_mutate_input():
    df = _make_df()
    before = df.copy(deep=True)
    group_by_aggregate(df, by="b", agg="mean")
    assert df.equals(before)


def test_profile_unknown_column_raises():
    df = _make_df()
    with pytest.raises(ValueError):
        profile(df, columns=["nope"])


def test_missingness_unknown_column_raises():
    df = _make_df()
    with pytest.raises(ValueError):
        missingness(df, columns=["nope"])


def test_co_missingness_unknown_column_raises():
    df = _make_df()
    with pytest.raises(ValueError):
        co_missingness(df, columns=["nope"])


def test_distribution_summary_unknown_column_raises():
    df = _make_df()
    with pytest.raises(ValueError):
        distribution_summary(df, columns=["nope"])


def test_group_by_aggregate_unknown_by_column_raises():
    df = _make_df()
    with pytest.raises(ValueError):
        group_by_aggregate(df, by="nope", agg="mean")


def test_group_by_aggregate_unknown_value_column_raises():
    df = _make_df()
    with pytest.raises(ValueError):
        group_by_aggregate(df, by="b", agg="mean", columns=["nope"])


def test_missingness_pct_value():
    df = _make_df()
    result = missingness(df).set_index("column")
    assert result.loc["a", "pct_missing"] == pytest.approx(33.3333, abs=1e-3)


def test_co_missingness_diagonal_equals_own_missing_fraction():
    df = _make_df()
    result = co_missingness(df).set_index("column")
    miss = missingness(df).set_index("column")
    for col in df.columns:
        assert result.loc[col, col] == pytest.approx(miss.loc[col, "pct_missing"] / 100.0, abs=1e-4)


def test_group_by_aggregate_one_row_per_group():
    df = _make_df()
    result = group_by_aggregate(df, by="b", agg="mean")
    assert len(result) == df["b"].nunique()
    assert set(result["b"]) == set(df["b"].unique())


def test_distribution_summary_skips_non_numeric_column():
    df = _make_df()
    result = distribution_summary(df)
    assert "b" not in set(result["column"])
    assert set(result["column"]) == {"a", "c"}
