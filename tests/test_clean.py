"""Tests for colonymind.clean (Epic 1, Story 8).

Covers ``cm.clean.impute_missing``: a thin wrapper over
``sklearn.impute.SimpleImputer`` that fills missing values column-wise while
remaining pure (never mutating its input DataFrame).
"""

from __future__ import annotations

import pandas as pd
import pytest

from colonymind.api import PUBLIC_OPS
from colonymind.clean import impute_missing


def test_impute_mean_fills_nan() -> None:
    df = pd.DataFrame({"a": [1.0, None, 3.0]})
    result = impute_missing(df, strategy="mean")
    assert result["a"].iloc[1] == 2.0
    assert not result.isna().any().any()


def test_impute_does_not_mutate_input() -> None:
    df = pd.DataFrame({"a": [1.0, None, 3.0]})
    original = df.copy()
    impute_missing(df, strategy="mean")
    assert original.isna().any().any()
    pd.testing.assert_frame_equal(df, original)


def test_impute_bad_strategy_raises() -> None:
    df = pd.DataFrame({"a": [1.0, None, 3.0]})
    with pytest.raises(ValueError):
        impute_missing(df, strategy="bogus")


def test_impute_unknown_column_raises() -> None:
    df = pd.DataFrame({"a": [1.0, None, 3.0]})
    with pytest.raises(ValueError):
        impute_missing(df, columns=["nope"])


def test_impute_returns_dataframe() -> None:
    df = pd.DataFrame({"a": [1.0, None, 3.0]})
    result = impute_missing(df, strategy="mean")
    assert isinstance(result, pd.DataFrame)


def test_impute_registered_as_public_op() -> None:
    assert "cm.clean.impute_missing" in PUBLIC_OPS
