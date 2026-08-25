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
from emergentflow.stats.errors import StatsScaleError


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


def test_co_missingness_duplicate_columns_dedupe():
    df = _make_df()
    result = co_missingness(df, columns=["a", "a"])
    assert result.columns.tolist() == ["column", "a"]
    assert result.equals(co_missingness(df, columns=["a"]))


def test_co_missingness_scale_guard_raises():
    df = _make_df()
    with pytest.raises(StatsScaleError):
        co_missingness(df, max_footprint_bytes=1)


def test_co_missingness_scale_guard_pass_large_cap():
    df = _make_df()
    result = co_missingness(df, max_footprint_bytes=1 << 60)
    assert result.equals(co_missingness(df))


def test_co_missingness_default_guard_does_not_trigger():
    df = _make_df()
    result = co_missingness(df)
    assert result.equals(co_missingness(df, max_footprint_bytes=1 << 60))


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


def test_group_by_aggregate_unknown_dict_agg_key_raises():
    df = _make_df()
    with pytest.raises(ValueError, match="unknown aggregation column"):
        group_by_aggregate(df, by="b", agg={"nope": "mean"})
    with pytest.raises(ValueError, match="unknown aggregation column"):
        group_by_aggregate(df, by="b", agg={"a": "mean", "nope": "sum"})


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


def test_group_by_aggregate_dict_agg_honors_columns_filter():
    # Regression: with a dict ``agg``, the ``columns`` filter must still restrict which value
    # columns are aggregated (it previously only applied on the str-agg path).
    df = _make_df()
    result = group_by_aggregate(df, by="b", agg={"a": "mean", "c": "sum"}, columns=["a"])
    assert "a" in result.columns
    assert "c" not in result.columns


def test_group_by_aggregate_list_valued_agg_flattens_multiindex_columns():
    # Regression: a dict ``agg`` mapping a column to a *list* of aggregation functions makes
    # pandas emit MultiIndex columns (e.g. ("a", "mean")); these must be flattened to single
    # tidy names (e.g. "a_mean") rather than leaking a MultiIndex into the result.
    df = _make_df()
    result = group_by_aggregate(df, by="b", agg={"a": ["mean", "sum"], "c": "sum"})
    assert not isinstance(result.columns, pd.MultiIndex)
    assert set(result.columns) == {"b", "a_mean", "a_sum", "c_sum"}
    assert is_inspectable(result)
    payload = to_payload(result)
    assert payload["columns"] == ["b", "a_mean", "a_sum", "c_sum"]


def test_distribution_summary_skips_non_numeric_column():
    df = _make_df()
    result = distribution_summary(df)
    assert "b" not in set(result["column"])
    assert set(result["column"]) == {"a", "c"}


def test_plot_missingness_heatmap_is_registered_public_op():
    assert "ef.viz.plot_missingness_heatmap" in PUBLIC_OPS


def test_plot_missingness_heatmap_renders_co_missingness_matrix():
    from emergentflow.viz import plot_missingness_heatmap

    df = _make_df()
    matrix = co_missingness(df)
    plot = plot_missingness_heatmap(matrix)

    assert is_inspectable(plot)
    heatmap = plot.spec["data"][0]
    assert heatmap["x"] == list(df.columns)
    assert heatmap["y"] == list(df.columns)
    assert heatmap["zmin"] == 0
    assert heatmap["zmax"] == 1


def test_auto_eda_missingness_plot_is_the_co_missingness_heatmap():
    from emergentflow.stats import auto_eda
    from emergentflow.viz import plot_missingness_heatmap

    df = _make_df()
    result = auto_eda(df)

    assert result.frames["co_missingness"].equals(co_missingness(df))
    assert result.plots["missingness"].spec == plot_missingness_heatmap(co_missingness(df)).spec


def test_group_by_aggregate_list_agg_flattens_multiindex():
    df = pd.DataFrame({"g": ["a", "a", "b"], "x": [1.0, 2.0, 3.0]})
    result = group_by_aggregate(df, by="g", agg=["mean", "sum"])
    assert not isinstance(result.columns, pd.MultiIndex)
    assert set(result.columns) == {"g", "x_mean", "x_sum"}
    assert len(result) == 2
    assert is_inspectable(result)
    payload = to_payload(result)
    assert payload["kind"] == "table"


def test_group_by_aggregate_list_agg_does_not_mutate():
    df = pd.DataFrame({"g": ["a", "a", "b"], "x": [1.0, 2.0, 3.0]})
    before = df.copy(deep=True)
    group_by_aggregate(df, by="g", agg=["mean", "sum"])
    assert df.equals(before)


def test_register_aggregation_direct_call():
    from emergentflow.stats.eda import _AGG_REGISTRY, register_aggregation

    _AGG_REGISTRY.clear()

    def iqr(s):
        return float(s.quantile(0.75) - s.quantile(0.25))

    register_aggregation("iqr", iqr)
    assert "iqr" in _AGG_REGISTRY
    assert _AGG_REGISTRY["iqr"] is iqr


def test_register_aggregation_decorator():
    from emergentflow.stats.eda import _AGG_REGISTRY, register_aggregation

    _AGG_REGISTRY.clear()

    @register_aggregation("range")
    def _range(s):
        return float(s.max() - s.min())

    assert "range" in _AGG_REGISTRY
    assert _AGG_REGISTRY["range"] is _range


def test_group_by_aggregate_custom_agg_resolves_registered_name():
    from emergentflow.stats.eda import _AGG_REGISTRY, register_aggregation

    _AGG_REGISTRY.clear()

    def iqr(s):
        return float(s.quantile(0.75) - s.quantile(0.25))

    register_aggregation("iqr", iqr)

    df = pd.DataFrame({"g": ["a", "a", "b"], "x": [1.0, 5.0, 3.0]})
    result = group_by_aggregate(df, by="g", agg=["iqr"])
    assert result.loc[result["g"] == "a", "x_iqr"].iloc[0] == pytest.approx(2.0)
    assert is_inspectable(result)


def test_group_by_aggregate_custom_agg_in_dict():
    from emergentflow.stats.eda import _AGG_REGISTRY, register_aggregation

    _AGG_REGISTRY.clear()

    def iqr(s):
        return float(s.quantile(0.75) - s.quantile(0.25))

    register_aggregation("iqr", iqr)

    df = pd.DataFrame({"g": ["a", "a", "b"], "x": [1.0, 5.0, 3.0], "y": [10.0, 20.0, 30.0]})
    result = group_by_aggregate(df, by="g", agg={"x": ["mean", "iqr"], "y": "sum"})
    assert not isinstance(result.columns, pd.MultiIndex)
    assert "x_mean" in result.columns
    assert "x_iqr" in result.columns
    assert "y_sum" in result.columns
