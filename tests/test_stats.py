"""Tests for ``emergentflow.stats`` (Epic 1, Story 8)."""

from __future__ import annotations

import pandas as pd
import pytest

from emergentflow.stats import (
    AnovaResult,
    CohortRetentionResult,
    CrosstabResult,
    TTestResult,
    anova,
    chi_square,
    cohort_retention,
    correct_pvalues,
    correlation,
    crosstab,
    describe,
    funnel,
    kruskal,
    mann_whitney,
    power_analysis,
    test_proportions,
    ttest,
    wilcoxon,
)
from emergentflow.stats.errors import StatsScaleError

# pytest collects top-level ``test_`` names; mark this imported function
# so pytest skips it (it is not an actual test case).
test_proportions.__test__ = False  # type: ignore[attr-defined]


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


# ---------------------------------------------------------------------------
# Mann-Whitney U tests
# ---------------------------------------------------------------------------


def _two_group_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "grp": ["a", "a", "a", "b", "b", "b"],
            "score": [1.0, 2.0, 3.0, 5.0, 6.0, 7.0],
        }
    )


def test_mann_whitney_returns_dataframe() -> None:
    df = _two_group_df()
    result = mann_whitney(df, group_col="grp", value_col="score")
    assert isinstance(result, pd.DataFrame)
    assert result.shape[0] == 1


def test_mann_whitney_pvalue_in_range() -> None:
    df = _two_group_df()
    result = mann_whitney(df, group_col="grp", value_col="score")
    assert isinstance(result["p_value"].iloc[0], float)
    assert 0.0 <= result["p_value"].iloc[0] <= 1.0


def test_mann_whitney_unknown_column_raises() -> None:
    df = _two_group_df()
    with pytest.raises(ValueError, match="unknown group_col"):
        mann_whitney(df, group_col="nope", value_col="score")


def test_mann_whitney_missing_value_col_raises() -> None:
    df = _two_group_df()
    with pytest.raises(ValueError, match="unknown value_col"):
        mann_whitney(df, group_col="grp", value_col="nope")


def test_mann_whitney_same_column_raises() -> None:
    df = _two_group_df()
    with pytest.raises(ValueError, match="must differ"):
        mann_whitney(df, group_col="grp", value_col="grp")


def test_mann_whitney_single_group_raises() -> None:
    df = pd.DataFrame({"grp": ["a", "a", "a"], "score": [1.0, 2.0, 3.0]})
    with pytest.raises(ValueError, match="exactly 2 distinct groups"):
        mann_whitney(df, group_col="grp", value_col="score")


def test_mann_whitney_bad_alternative_raises() -> None:
    df = _two_group_df()
    with pytest.raises(ValueError, match="unknown alternative"):
        mann_whitney(df, group_col="grp", value_col="score", alternative="bogus")


def test_mann_whitney_deterministic() -> None:
    df = _two_group_df()
    first = mann_whitney(df, group_col="grp", value_col="score")
    second = mann_whitney(df, group_col="grp", value_col="score")
    assert first["statistic"].iloc[0] == second["statistic"].iloc[0]
    assert first["p_value"].iloc[0] == second["p_value"].iloc[0]


def test_mann_whitney_nan_values_are_excluded() -> None:
    """NaN value rows must not inflate n_a/n_b or poison the statistic to NaN.

    Regression: scipy's mannwhitneyu strips NaN internally, so passing NaN rows
    through made both `statistic` and `p_value` come back NaN (a silently useless
    result) while n_a/n_b still counted the NaN rows -- the exact inconsistency
    `ttest` was fixed for.
    """
    df = pd.DataFrame(
        {
            "grp": ["a", "a", "a", "b", "b", "b"],
            "score": [1.0, 2.0, float("nan"), 4.0, 5.0, 6.0],
        }
    )

    result = mann_whitney(df, group_col="grp", value_col="score")

    row = result.iloc[0]
    assert row["n_a"] == 2
    assert row["n_b"] == 3
    assert not pd.isna(row["statistic"])
    assert not pd.isna(row["p_value"])
    assert 0.0 <= row["p_value"] <= 1.0


def test_mann_whitney_registered_as_public_op() -> None:
    from emergentflow.api import PUBLIC_OPS

    assert "ef.stats.mann_whitney" in PUBLIC_OPS


# ---------------------------------------------------------------------------
# Wilcoxon signed-rank tests
# ---------------------------------------------------------------------------


def _paired_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "before": [10.0, 12.0, 9.0, 11.0, 13.0],
            "after": [12.0, 14.0, 10.0, 13.0, 15.0],
        }
    )


def test_wilcoxon_returns_dataframe() -> None:
    df = _paired_df()
    result = wilcoxon(df, col_a="before", col_b="after")
    assert isinstance(result, pd.DataFrame)
    assert result.shape[0] == 1


def test_wilcoxon_pvalue_in_range() -> None:
    df = _paired_df()
    result = wilcoxon(df, col_a="before", col_b="after")
    assert isinstance(result["p_value"].iloc[0], float)
    assert 0.0 <= result["p_value"].iloc[0] <= 1.0


def test_wilcoxon_unknown_column_raises() -> None:
    df = _paired_df()
    with pytest.raises(ValueError, match="unknown col_a"):
        wilcoxon(df, col_a="nope", col_b="after")


def test_wilcoxon_missing_col_b_raises() -> None:
    df = _paired_df()
    with pytest.raises(ValueError, match="unknown col_b"):
        wilcoxon(df, col_a="before", col_b="nope")


def test_wilcoxon_same_column_raises() -> None:
    df = _paired_df()
    with pytest.raises(ValueError, match="must differ"):
        wilcoxon(df, col_a="before", col_b="before")


def test_wilcoxon_bad_alternative_raises() -> None:
    df = _paired_df()
    with pytest.raises(ValueError, match="unknown alternative"):
        wilcoxon(df, col_a="before", col_b="after", alternative="bogus")


def test_wilcoxon_all_nan_raises() -> None:
    df = pd.DataFrame({"a": [None, None], "b": [None, None]})
    with pytest.raises(ValueError, match="at least 1 complete pair"):
        wilcoxon(df, col_a="a", col_b="b")


def test_wilcoxon_deterministic() -> None:
    df = _paired_df()
    first = wilcoxon(df, col_a="before", col_b="after")
    second = wilcoxon(df, col_a="before", col_b="after")
    assert first["statistic"].iloc[0] == second["statistic"].iloc[0]
    assert first["p_value"].iloc[0] == second["p_value"].iloc[0]


def test_wilcoxon_registered_as_public_op() -> None:
    from emergentflow.api import PUBLIC_OPS

    assert "ef.stats.wilcoxon" in PUBLIC_OPS


# ---------------------------------------------------------------------------
# Kruskal-Wallis tests
# ---------------------------------------------------------------------------


def _three_group_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "grp": ["a", "a", "a", "b", "b", "b", "c", "c", "c"],
            "score": [1.0, 1.1, 0.9, 5.0, 5.1, 4.9, 9.0, 9.1, 8.9],
        }
    )


def test_kruskal_returns_dataframe() -> None:
    df = _three_group_df()
    result = kruskal(df, group_col="grp", value_col="score")
    assert isinstance(result, pd.DataFrame)
    assert result.shape[0] == 1


def test_kruskal_pvalue_in_range() -> None:
    df = _three_group_df()
    result = kruskal(df, group_col="grp", value_col="score")
    assert isinstance(result["p_value"].iloc[0], float)
    assert 0.0 <= result["p_value"].iloc[0] <= 1.0


def test_kruskal_unknown_group_col_raises() -> None:
    df = _three_group_df()
    with pytest.raises(ValueError, match="unknown group_col"):
        kruskal(df, group_col="nope", value_col="score")


def test_kruskal_unknown_value_col_raises() -> None:
    df = _three_group_df()
    with pytest.raises(ValueError, match="unknown value_col"):
        kruskal(df, group_col="grp", value_col="nope")


def test_kruskal_same_column_raises() -> None:
    df = _three_group_df()
    with pytest.raises(ValueError, match="must differ"):
        kruskal(df, group_col="score", value_col="score")


def test_kruskal_single_group_raises() -> None:
    df = pd.DataFrame({"grp": ["a", "a", "a"], "score": [1.0, 2.0, 3.0]})
    with pytest.raises(ValueError, match="at least 2 distinct groups"):
        kruskal(df, group_col="grp", value_col="score")


def test_kruskal_deterministic() -> None:
    df = _three_group_df()
    first = kruskal(df, group_col="grp", value_col="score")
    second = kruskal(df, group_col="grp", value_col="score")
    assert first["statistic"].iloc[0] == second["statistic"].iloc[0]
    assert first["p_value"].iloc[0] == second["p_value"].iloc[0]


def test_kruskal_group_with_no_non_null_values_raises() -> None:
    """A group whose value column is entirely NaN would pass scipy an empty sample
    and silently yield a NaN statistic/p-value; it must raise a typed error instead."""
    df = pd.DataFrame({"grp": ["a", "a", "b", "b"], "score": [1.0, 2.0, None, None]})
    with pytest.raises(ValueError, match="no non-null values"):
        kruskal(df, group_col="grp", value_col="score")


def test_kruskal_registered_as_public_op() -> None:
    from emergentflow.api import PUBLIC_OPS

    assert "ef.stats.kruskal" in PUBLIC_OPS


# ---------------------------------------------------------------------------
# Chi-square tests
# ---------------------------------------------------------------------------


def _contingency_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "treatment": ["A", "A", "B", "B", "B", "A", "B", "A"],
            "outcome": ["good", "bad", "good", "bad", "bad", "good", "good", "bad"],
        }
    )


def test_chi_square_returns_dataframe() -> None:
    df = _contingency_df()
    result = chi_square(df, row_col="treatment", col_col="outcome")
    assert isinstance(result, pd.DataFrame)
    assert result.shape[0] == 1


def test_chi_square_pvalue_in_range() -> None:
    df = _contingency_df()
    result = chi_square(df, row_col="treatment", col_col="outcome")
    assert isinstance(result["p_value"].iloc[0], float)
    assert 0.0 <= result["p_value"].iloc[0] <= 1.0


def test_chi_square_unknown_row_col_raises() -> None:
    df = _contingency_df()
    with pytest.raises(ValueError, match="unknown row_col"):
        chi_square(df, row_col="nope", col_col="outcome")


def test_chi_square_unknown_col_col_raises() -> None:
    df = _contingency_df()
    with pytest.raises(ValueError, match="unknown col_col"):
        chi_square(df, row_col="treatment", col_col="nope")


def test_chi_square_same_column_raises() -> None:
    df = _contingency_df()
    with pytest.raises(ValueError, match="must differ"):
        chi_square(df, row_col="treatment", col_col="treatment")


def test_chi_square_too_small_raises() -> None:
    df = pd.DataFrame({"a": ["x", "x"], "b": ["y", "y"]})
    with pytest.raises(ValueError, match="at least a 2x2"):
        chi_square(df, row_col="a", col_col="b")


def test_chi_square_2x2_fisher_included() -> None:
    df = _contingency_df()
    result = chi_square(df, row_col="treatment", col_col="outcome", correction=False)
    assert result["fisher_p"].iloc[0] is not None
    assert result["fisher_odds_ratio"].iloc[0] is not None


def test_chi_square_deterministic() -> None:
    df = _contingency_df()
    first = chi_square(df, row_col="treatment", col_col="outcome")
    second = chi_square(df, row_col="treatment", col_col="outcome")
    assert first["statistic"].iloc[0] == second["statistic"].iloc[0]
    assert first["p_value"].iloc[0] == second["p_value"].iloc[0]


def test_chi_square_registered_as_public_op() -> None:
    from emergentflow.api import PUBLIC_OPS

    assert "ef.stats.chi_square" in PUBLIC_OPS


# ---------------------------------------------------------------------------
# describe
# ---------------------------------------------------------------------------


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


def test_correlation_scale_guard_raises() -> None:
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [2.0, 4.0, 6.0], "c": [3.0, 6.0, 9.0]})

    with pytest.raises(StatsScaleError):
        correlation(df, max_footprint_bytes=1)


def test_correlation_scale_guard_pass_large_cap() -> None:
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [2.0, 4.0, 6.0], "c": [3.0, 6.0, 9.0]})

    result = correlation(df, max_footprint_bytes=1 << 60)

    assert isinstance(result, pd.DataFrame)
    assert set(result.columns) == {"column", "a", "b", "c"}


def test_correlation_default_guard_does_not_trigger() -> None:
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [2.0, 4.0, 6.0], "c": [3.0, 6.0, 9.0]})

    result = correlation(df)

    assert isinstance(result, pd.DataFrame)
    assert set(result.columns) == {"column", "a", "b", "c"}


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


def test_ttest_all_nan_group_raises() -> None:
    df = pd.DataFrame({"grp": ["a", "a", "b", "b"], "score": [None, None, 5.0, 7.0]})

    with pytest.raises(ValueError, match="at least one non-null"):
        ttest(df, group_col="grp", value_col="score")


def test_ttest_single_observation_per_group_raises() -> None:
    df = pd.DataFrame({"grp": ["a", "b"], "score": [1.0, 2.0]})

    with pytest.raises(ValueError, match="more than one total observation"):
        ttest(df, group_col="grp", value_col="score")


def test_ttest_deterministic() -> None:
    df = _two_group_df()

    first = ttest(df, group_col="grp", value_col="score")
    second = ttest(df, group_col="grp", value_col="score")

    assert first.t_statistic == second.t_statistic
    assert first.p_value == second.p_value


def test_ttest_alpha_is_recorded() -> None:
    df = _two_group_df()

    result = ttest(df, group_col="grp", value_col="score", alpha=0.01)

    assert result.alpha == 0.01


def test_ttest_alpha_default_is_stored() -> None:
    df = _two_group_df()

    result = ttest(df, group_col="grp", value_col="score")

    assert result.alpha == 0.05


def test_ttest_effect_size_fields_exist() -> None:
    df = _two_group_df()

    result = ttest(df, group_col="grp", value_col="score")

    assert isinstance(result.effect_size, float)
    assert isinstance(result.ci_low, float)
    assert isinstance(result.ci_high, float)
    assert result.ci_low <= result.ci_high
    assert result.ci_low <= result.effect_size <= result.ci_high


def test_ttest_effect_size_large_for_strongly_separated_groups() -> None:
    df = pd.DataFrame(
        {
            "grp": ["a", "a", "a", "b", "b", "b"],
            "score": [10.0, 10.1, 9.9, 1.0, 1.1, 0.9],
        }
    )

    result = ttest(df, group_col="grp", value_col="score")

    assert result.effect_size > 1.0


def test_ttest_nan_values_are_excluded_from_sample_sizes() -> None:
    """NaN value rows must not inflate n_a/n_b or the reported means (regression)."""
    df = pd.DataFrame(
        {
            "grp": ["a", "a", "a", "b", "b", "b"],
            "score": [1.0, 2.0, float("nan"), 5.0, 6.0, 7.0],
        }
    )

    result = ttest(df, group_col="grp", value_col="score")

    # Group a has 3 rows but only 2 non-NaN values; group b has 3 non-NaN values.
    assert result.n_a == 2
    assert result.n_b == 3
    assert result.mean_a == 1.5
    assert result.mean_b == 6.0


# ---------------------------------------------------------------------------
# ANOVA CI tests
# ---------------------------------------------------------------------------


def test_anova_ci_fields_exist() -> None:
    df = _separable_groups_df()

    result = anova(df, group_col="grp", value_col="score")

    assert isinstance(result.ci_low, float)
    assert isinstance(result.ci_high, float)
    assert 0.0 <= result.ci_low <= result.ci_high <= 1.0


# ---------------------------------------------------------------------------
# correct_pvalues tests
# ---------------------------------------------------------------------------


def test_correct_pvalues_bonferroni_adds_columns() -> None:
    df = pd.DataFrame({"p_value": [0.01, 0.04, 0.5, 0.8]})

    result = correct_pvalues(df, p_col="p_value", method="bonferroni")

    assert "p_adjusted" in result.columns
    assert "reject_null" in result.columns
    assert list(df.columns) == ["p_value"]


def test_correct_pvalues_bonferroni_adjusted_gte_raw() -> None:
    df = pd.DataFrame({"p_value": [0.01, 0.04, 0.5, 0.8]})

    result = correct_pvalues(df, p_col="p_value", method="bonferroni")

    assert (result["p_adjusted"] >= result["p_value"]).all()


def test_correct_pvalues_unknown_p_col_raises() -> None:
    df = pd.DataFrame({"p_value": [0.01, 0.04]})

    with pytest.raises(ValueError, match="unknown p_col"):
        correct_pvalues(df, p_col="nope")


def test_correct_pvalues_overwrite_raises() -> None:
    df = pd.DataFrame({"p_value": [0.01, 0.04], "p_adjusted": [0.01, 0.04]})

    with pytest.raises(ValueError, match="would overwrite existing column"):
        correct_pvalues(df, p_col="p_value")


def test_correct_pvalues_does_not_mutate_input() -> None:
    df = pd.DataFrame({"p_value": [0.01, 0.04, 0.5, 0.8]})
    original = df.copy()

    correct_pvalues(df, p_col="p_value")

    from pandas.testing import assert_frame_equal

    assert_frame_equal(df, original)


# ---------------------------------------------------------------------------
# test_proportions
# ---------------------------------------------------------------------------


def test_test_proportions_different_rates() -> None:
    np = pytest.importorskip("numpy")
    rng = np.random.default_rng(42)
    n_a, n_b = 100, 100
    df = pd.DataFrame(
        {
            "group": ["a"] * n_a + ["b"] * n_b,
            "success": (list(rng.binomial(1, 0.20, n_a)) + list(rng.binomial(1, 0.40, n_b))),
        }
    )
    result = test_proportions(df, group_col="group", success_col="success")
    assert result["p_value"].iloc[0] < 0.05
    assert result["diff"].iloc[0] > 0
    assert result["ci_low"].iloc[0] <= result["diff"].iloc[0] <= result["ci_high"].iloc[0]


def test_test_proportions_relative_uplift() -> None:
    np = pytest.importorskip("numpy")
    rng = np.random.default_rng(42)
    n_a, n_b = 100, 100
    df = pd.DataFrame(
        {
            "group": ["a"] * n_a + ["b"] * n_b,
            "success": (list(rng.binomial(1, 0.20, n_a)) + list(rng.binomial(1, 0.40, n_b))),
        }
    )
    result = test_proportions(df, group_col="group", success_col="success")
    p_a = result["p_a"].iloc[0]
    diff = result["diff"].iloc[0]
    expected_uplift = diff / p_a if p_a != 0 else float("nan")
    assert result["relative_uplift"].iloc[0] == pytest.approx(expected_uplift)


def test_test_proportions_unknown_group_col_raises() -> None:
    df = pd.DataFrame({"grp": ["a", "b"], "ok": [1, 0]})
    with pytest.raises(ValueError, match="unknown group_col"):
        test_proportions(df, group_col="nope", success_col="ok")


def test_test_proportions_unknown_success_col_raises() -> None:
    df = pd.DataFrame({"grp": ["a", "b"], "ok": [1, 0]})
    with pytest.raises(ValueError, match="unknown success_col"):
        test_proportions(df, group_col="grp", success_col="nope")


def test_test_proportions_same_column_raises() -> None:
    df = pd.DataFrame({"grp": ["a", "b"], "ok": [1, 0]})
    with pytest.raises(ValueError, match="must differ"):
        test_proportions(df, group_col="ok", success_col="ok")


def test_test_proportions_non_binary_raises() -> None:
    df = pd.DataFrame({"grp": ["a", "b"], "ok": [2, 3]})
    with pytest.raises(ValueError, match="must contain only 0/1/True/False"):
        test_proportions(df, group_col="grp", success_col="ok")


def test_test_proportions_non_binary_string_raises() -> None:
    df = pd.DataFrame({"grp": ["a", "b"], "ok": ["yes", "no"]})
    with pytest.raises(ValueError, match="must contain only 0/1/True/False"):
        test_proportions(df, group_col="grp", success_col="ok")


def test_test_proportions_single_group_raises() -> None:
    df = pd.DataFrame({"grp": ["a", "a"], "ok": [1, 0]})
    with pytest.raises(ValueError, match="exactly 2 distinct groups"):
        test_proportions(df, group_col="grp", success_col="ok")


def test_test_proportions_three_groups_raises() -> None:
    df = pd.DataFrame({"grp": ["a", "b", "c"], "ok": [1, 0, 1]})
    with pytest.raises(ValueError, match="exactly 2 distinct groups"):
        test_proportions(df, group_col="grp", success_col="ok")


def test_test_proportions_all_nan_success_group_raises() -> None:
    df = pd.DataFrame({"grp": ["a", "a", "a", "b", "b", "b"], "ok": [0, 1, 1, None, None, None]})

    with pytest.raises(ValueError, match="at least one non-null"):
        test_proportions(df, group_col="grp", success_col="ok")


# ---------------------------------------------------------------------------
# power_analysis
# ---------------------------------------------------------------------------


def test_power_analysis_solve_for_power() -> None:
    result = power_analysis(effect_size=0.5, nobs=100, alpha=0.05)
    assert isinstance(result["power"].iloc[0], float)
    assert 0.0 <= result["power"].iloc[0] <= 1.0
    assert result["solved_for"].iloc[0] == "power"


def test_power_analysis_solve_for_nobs() -> None:
    result = power_analysis(effect_size=0.5, power=0.8, alpha=0.05)
    assert result["nobs"].iloc[0] > 0
    assert result["solved_for"].iloc[0] == "nobs"


def test_power_analysis_solve_for_effect_size() -> None:
    result = power_analysis(nobs=100, power=0.8, alpha=0.05)
    assert result["solved_for"].iloc[0] == "effect_size"


def test_power_analysis_all_set_raises() -> None:
    with pytest.raises(ValueError, match="exactly one of"):
        power_analysis(effect_size=0.5, nobs=100, power=0.8, alpha=0.05)


def test_power_analysis_two_unset_raises() -> None:
    with pytest.raises(ValueError, match="exactly one of"):
        power_analysis(effect_size=0.5, alpha=0.05)


def test_power_analysis_all_unset_raises() -> None:
    with pytest.raises(ValueError, match="exactly one of"):
        power_analysis(alpha=0.05)


def test_power_analysis_bad_alternative_raises() -> None:
    with pytest.raises(ValueError, match="unknown alternative"):
        power_analysis(effect_size=0.5, nobs=100, alternative="bogus")


# ---------------------------------------------------------------------------
# crosstab
# ---------------------------------------------------------------------------


def _crosstab_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "treatment": ["A", "A", "B", "B", "B", "A", "B", "A"],
            "outcome": ["good", "bad", "good", "bad", "bad", "good", "good", "bad"],
        }
    )


def test_crosstab_returns_crosstabresult() -> None:
    df = _crosstab_df()
    result = crosstab(df, row_col="treatment", col_col="outcome")
    assert isinstance(result, CrosstabResult)
    assert isinstance(result.table, pd.DataFrame)
    assert isinstance(result.chi_square, float)
    assert isinstance(result.p_value, float)
    assert isinstance(result.dof, int)
    assert isinstance(result.n, int)
    assert result.n == len(df)


def test_crosstab_margins_default() -> None:
    df = _crosstab_df()
    result = crosstab(df, row_col="treatment", col_col="outcome")
    assert "Total" in result.table.columns
    treatment_col = result.table.columns[0]
    assert (result.table[treatment_col] == "Total").any()


def test_crosstab_margins_false() -> None:
    df = _crosstab_df()
    result = crosstab(df, row_col="treatment", col_col="outcome", margins=False)
    assert "Total" not in result.table.columns
    treatment_col = result.table.columns[0]
    assert not (result.table[treatment_col] == "Total").any()


def test_crosstab_chi_square_independent_of_normalize() -> None:
    df = _crosstab_df()
    result_none = crosstab(df, row_col="treatment", col_col="outcome", normalize="none")
    result_all = crosstab(df, row_col="treatment", col_col="outcome", normalize="all")
    assert result_none.chi_square == result_all.chi_square
    assert result_none.p_value == result_all.p_value
    assert result_none.dof == result_all.dof
    assert result_none.n == result_all.n


def test_crosstab_unknown_row_col_raises() -> None:
    df = _crosstab_df()
    with pytest.raises(ValueError, match="unknown row_col"):
        crosstab(df, row_col="nope", col_col="outcome")


def test_crosstab_unknown_col_col_raises() -> None:
    df = _crosstab_df()
    with pytest.raises(ValueError, match="unknown col_col"):
        crosstab(df, row_col="treatment", col_col="nope")


def test_crosstab_same_column_raises() -> None:
    df = _crosstab_df()
    with pytest.raises(ValueError, match="must differ"):
        crosstab(df, row_col="treatment", col_col="treatment")


def test_crosstab_unknown_normalize_raises() -> None:
    df = _crosstab_df()
    with pytest.raises(ValueError, match="unknown normalize"):
        crosstab(df, row_col="treatment", col_col="outcome", normalize="bogus")


def test_crosstab_too_small_raises() -> None:
    df = pd.DataFrame({"a": ["x", "x"], "b": ["y", "y"]})
    with pytest.raises(ValueError, match="at least a 2x2"):
        crosstab(df, row_col="a", col_col="b")


# ---------------------------------------------------------------------------
# cohort_retention
# ---------------------------------------------------------------------------


def _cohort_retention_df() -> pd.DataFrame:
    # user A: active Jan, Feb, Mar (cohort=Jan)
    # user B: active Feb only (cohort=Feb)
    # user C: active Jan only (cohort=Jan)
    return pd.DataFrame(
        {
            "user": ["A", "A", "A", "B", "C"],
            "ts": [
                "2024-01-05",
                "2024-02-10",
                "2024-03-15",
                "2024-02-20",
                "2024-01-25",
            ],
        }
    )


def test_cohort_retention_known_values() -> None:
    df = _cohort_retention_df()
    result = cohort_retention(df, user_col="user", date_col="ts", period="M")
    assert isinstance(result, CohortRetentionResult)
    tidy = result.tidy

    jan = tidy[tidy["cohort"] == "2024-01"].set_index("period_number")
    assert jan.loc[0, "n_users"] == 2
    assert jan.loc[0, "cohort_size"] == 2
    assert jan.loc[0, "retention_rate"] == 1.0
    assert jan.loc[1, "n_users"] == 1
    assert jan.loc[1, "retention_rate"] == 0.5
    assert jan.loc[2, "n_users"] == 1
    assert jan.loc[2, "retention_rate"] == 0.5

    feb = tidy[tidy["cohort"] == "2024-02"].set_index("period_number")
    assert feb.loc[0, "n_users"] == 1
    assert feb.loc[0, "cohort_size"] == 1
    assert feb.loc[0, "retention_rate"] == 1.0


def test_cohort_retention_wide_shape() -> None:
    df = _cohort_retention_df()
    result = cohort_retention(df, user_col="user", date_col="ts", period="M")
    wide = result.wide
    assert set(wide["cohort"]) == {"2024-01", "2024-02"}
    assert "period_0" in wide.columns
    assert "period_1" in wide.columns


def test_cohort_retention_period_zero_always_full_retention() -> None:
    df = _cohort_retention_df()
    result = cohort_retention(df, user_col="user", date_col="ts", period="M")
    period_zero = result.tidy[result.tidy["period_number"] == 0]
    assert (period_zero["retention_rate"] == 1.0).all()


def test_cohort_retention_unknown_user_col_raises() -> None:
    df = _cohort_retention_df()
    with pytest.raises(ValueError, match="unknown user_col"):
        cohort_retention(df, user_col="nope", date_col="ts")


def test_cohort_retention_unknown_date_col_raises() -> None:
    df = _cohort_retention_df()
    with pytest.raises(ValueError, match="unknown date_col"):
        cohort_retention(df, user_col="user", date_col="nope")


def test_cohort_retention_unknown_period_raises() -> None:
    df = _cohort_retention_df()
    with pytest.raises(ValueError, match="unknown period"):
        cohort_retention(df, user_col="user", date_col="ts", period="Y")


# ---------------------------------------------------------------------------
# funnel
# ---------------------------------------------------------------------------


def _funnel_df() -> pd.DataFrame:
    rows = []
    for i in range(10):
        rows.append({"user": f"u{i}", "event": "view"})
    for i in range(6):
        rows.append({"user": f"u{i}", "event": "add_to_cart"})
    for i in range(3):
        rows.append({"user": f"u{i}", "event": "purchase"})
    return pd.DataFrame(rows)


def test_funnel_known_values() -> None:
    df = _funnel_df()
    result = funnel(
        df, user_col="user", event_col="event", steps=["view", "add_to_cart", "purchase"]
    )
    view = result[result["step"] == "view"].iloc[0]
    assert view["n_users"] == 10
    assert view["conversion_rate"] == 1.0
    assert view["drop_off"] == 0
    assert view["drop_off_rate"] == 0.0

    add = result[result["step"] == "add_to_cart"].iloc[0]
    assert add["n_users"] == 6
    assert add["conversion_rate"] == 0.6
    assert add["drop_off"] == 4
    assert add["drop_off_rate"] == 0.4

    purchase = result[result["step"] == "purchase"].iloc[0]
    assert purchase["n_users"] == 3
    assert purchase["conversion_rate"] == 0.3
    assert purchase["drop_off"] == 3
    assert purchase["drop_off_rate"] == 0.5


def test_funnel_step_zero_no_drop_off() -> None:
    df = _funnel_df()
    result = funnel(df, user_col="user", event_col="event", steps=["view", "purchase"])
    step_zero = result[result["step_number"] == 0].iloc[0]
    assert step_zero["drop_off"] == 0
    assert step_zero["drop_off_rate"] == 0.0


def test_funnel_unknown_step_raises() -> None:
    df = _funnel_df()
    with pytest.raises(ValueError, match="unknown step event"):
        funnel(df, user_col="user", event_col="event", steps=["view", "nope"])


def test_funnel_duplicate_step_raises() -> None:
    df = _funnel_df()
    with pytest.raises(ValueError, match="must be unique"):
        funnel(df, user_col="user", event_col="event", steps=["view", "view"])


def test_funnel_empty_steps_raises() -> None:
    df = _funnel_df()
    with pytest.raises(ValueError, match="non-empty"):
        funnel(df, user_col="user", event_col="event", steps=[])


def test_funnel_unknown_user_col_raises() -> None:
    df = _funnel_df()
    with pytest.raises(ValueError, match="unknown user_col"):
        funnel(df, user_col="nope", event_col="event", steps=["view"])


def test_funnel_unknown_event_col_raises() -> None:
    df = _funnel_df()
    with pytest.raises(ValueError, match="unknown event_col"):
        funnel(df, user_col="user", event_col="nope", steps=["view"])
