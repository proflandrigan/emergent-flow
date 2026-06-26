"""Tests for ``emergentflow.stats`` (Epic 1, Story 8)."""

from __future__ import annotations

import pandas as pd
import pytest

from emergentflow.stats import AnovaResult, TTestResult, anova, correlation, describe, ttest


def _separable_groups_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "grp": ["a", "a", "a", "b", "b", "b", "c", "c", "c"],
            "score": [1.0, 1.1, 0.9, 5.0, 5.1, 4.9, 9.0, 9.1, 8.9],
        }
    )


def test_anova_returns_result() -> None:
    df = _separable_groups_df()

    result = anova(df, group_col="grp", value_col="score")

    assert isinstance(result, AnovaResult)
    assert isinstance(result.summary, pd.DataFrame)


def test_anova_pvalue_is_float_in_range() -> None:
    df = _separable_groups_df()

    result = anova(df, group_col="grp", value_col="score")

    assert isinstance(result.p_value, float)
    assert 0.0 <= result.p_value <= 1.0


def test_anova_detects_strong_effect() -> None:
    df = _separable_groups_df()

    result = anova(df, group_col="grp", value_col="score")

    assert result.p_value < 0.05
    assert result.f_statistic > 0


def test_anova_missing_column_raises() -> None:
    df = _separable_groups_df()

    with pytest.raises(ValueError):
        anova(df, group_col="nope", value_col="score")


def test_anova_same_column_raises() -> None:
    df = _separable_groups_df()

    with pytest.raises(ValueError, match="must differ"):
        anova(df, group_col="score", value_col="score")


def test_anova_single_group_raises() -> None:
    df = pd.DataFrame({"grp": ["a", "a", "a"], "score": [1.0, 2.0, 3.0]})

    with pytest.raises(ValueError, match="at least 2 distinct groups"):
        anova(df, group_col="grp", value_col="score")


def test_anova_deterministic() -> None:
    df = _separable_groups_df()

    first = anova(df, group_col="grp", value_col="score")
    second = anova(df, group_col="grp", value_col="score")

    assert first.f_statistic == second.f_statistic
    assert first.p_value == second.p_value


def test_anova_registered_as_public_op() -> None:
    from emergentflow.api import PUBLIC_OPS

    assert "ef.stats.anova" in PUBLIC_OPS


def test_describe_returns_dataframe() -> None:
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [4.0, 5.0, 6.0]})

    result = describe(df)

    assert isinstance(result, pd.DataFrame)


def test_describe_has_statistic_column() -> None:
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [4.0, 5.0, 6.0]})

    result = describe(df)

    assert "statistic" in result.columns


def test_describe_columns_subset() -> None:
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [4.0, 5.0, 6.0]})

    result = describe(df, columns=["a"])

    assert "a" in result.columns
    assert "b" not in result.columns


def test_describe_unknown_column_raises() -> None:
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0]})

    with pytest.raises(ValueError, match="unknown columns"):
        describe(df, columns=["nope"])


def test_describe_does_not_mutate_input() -> None:
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [4.0, 5.0, 6.0]})
    original_cols = list(df.columns)

    describe(df)

    assert list(df.columns) == original_cols


def test_describe_registered_as_public_op() -> None:
    from emergentflow.api import PUBLIC_OPS

    assert "ef.stats.describe" in PUBLIC_OPS


def test_correlation_returns_dataframe() -> None:
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [2.0, 4.0, 6.0]})

    result = correlation(df)

    assert isinstance(result, pd.DataFrame)


def test_correlation_has_column_field() -> None:
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [2.0, 4.0, 6.0]})

    result = correlation(df)

    assert "column" in result.columns


def test_correlation_diagonal_is_one() -> None:
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [2.0, 4.0, 6.0]})

    result = correlation(df)

    for col in df.select_dtypes(include="number").columns:
        assert result[result["column"] == col][col].iloc[0] == 1.0


def test_correlation_bad_method_raises() -> None:
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0]})

    with pytest.raises(ValueError, match="unknown method"):
        correlation(df, method="bogus")


def test_correlation_unknown_column_raises() -> None:
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0]})

    with pytest.raises(ValueError, match="unknown columns"):
        correlation(df, columns=["nope"])


def test_correlation_columns_subset() -> None:
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [2.0, 4.0, 6.0], "c": [3.0, 6.0, 9.0]})

    result = correlation(df, columns=["a", "b"])

    assert "a" in result.columns
    assert "b" in result.columns
    assert "c" not in result.columns or result["c"].isna().all()


def test_correlation_does_not_mutate_input() -> None:
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [2.0, 4.0, 6.0]})
    original_cols = list(df.columns)

    correlation(df)

    assert list(df.columns) == original_cols


def test_correlation_registered_as_public_op() -> None:
    from emergentflow.api import PUBLIC_OPS

    assert "ef.stats.correlation" in PUBLIC_OPS


def _two_group_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "grp": ["a", "a", "a", "b", "b", "b"],
            "score": [1.0, 2.0, 3.0, 5.0, 6.0, 7.0],
        }
    )


def test_ttest_returns_result() -> None:
    df = _two_group_df()

    result = ttest(df, group_col="grp", value_col="score")

    assert isinstance(result, TTestResult)


def test_ttest_pvalue_in_range() -> None:
    df = _two_group_df()

    result = ttest(df, group_col="grp", value_col="score")

    assert isinstance(result.p_value, float)
    assert 0.0 <= result.p_value <= 1.0


def test_ttest_group_sizes_sum_to_row_count() -> None:
    df = _two_group_df()

    result = ttest(df, group_col="grp", value_col="score")

    assert result.n_a + result.n_b == len(df)


def test_ttest_group_labels_are_sorted() -> None:
    df = _two_group_df()

    result = ttest(df, group_col="grp", value_col="score")

    assert result.group_a == "a"
    assert result.group_b == "b"


def test_ttest_single_group_raises() -> None:
    df = pd.DataFrame({"grp": ["a", "a", "a"], "score": [1.0, 2.0, 3.0]})

    with pytest.raises(ValueError, match="exactly 2 distinct groups"):
        ttest(df, group_col="grp", value_col="score")


def test_ttest_three_groups_raises() -> None:
    df = pd.DataFrame(
        {"grp": ["a", "a", "b", "b", "c", "c"], "score": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]}
    )

    with pytest.raises(ValueError, match="exactly 2 distinct groups"):
        ttest(df, group_col="grp", value_col="score")


def test_ttest_missing_group_col_raises() -> None:
    df = _two_group_df()

    with pytest.raises(ValueError, match="unknown group_col"):
        ttest(df, group_col="nope", value_col="score")


def test_ttest_missing_value_col_raises() -> None:
    df = _two_group_df()

    with pytest.raises(ValueError, match="unknown value_col"):
        ttest(df, group_col="grp", value_col="nope")


def test_ttest_same_column_raises() -> None:
    df = _two_group_df()

    with pytest.raises(ValueError, match="must differ"):
        ttest(df, group_col="grp", value_col="grp")


def test_ttest_welch_path() -> None:
    df = _two_group_df()

    result = ttest(df, group_col="grp", value_col="score", equal_var=False)

    assert isinstance(result, TTestResult)
    assert result.equal_var is False


def test_ttest_registered_as_public_op() -> None:
    from emergentflow.api import PUBLIC_OPS

    assert "ef.stats.ttest" in PUBLIC_OPS


def test_ttest_does_not_mutate_input() -> None:
    df = _two_group_df()
    original_cols = list(df.columns)

    ttest(df, group_col="grp", value_col="score")

    assert list(df.columns) == original_cols


def test_ttest_deterministic() -> None:
    df = _two_group_df()

    first = ttest(df, group_col="grp", value_col="score")
    second = ttest(df, group_col="grp", value_col="score")

    assert first.t_statistic == second.t_statistic
    assert first.p_value == second.p_value
