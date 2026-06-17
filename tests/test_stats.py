"""Tests for ``colonymind.stats`` (Epic 1, Story 8)."""

from __future__ import annotations

import pandas as pd
import pytest

from colonymind.stats import AnovaResult, anova


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


def test_anova_deterministic() -> None:
    df = _separable_groups_df()

    first = anova(df, group_col="grp", value_col="score")
    second = anova(df, group_col="grp", value_col="score")

    assert first.f_statistic == second.f_statistic
    assert first.p_value == second.p_value


def test_anova_registered_as_public_op() -> None:
    from colonymind.api import PUBLIC_OPS

    assert "cm.stats.anova" in PUBLIC_OPS
