"""Tests for ``ef.ml.reduce_dimensions`` (Epic 16)."""

from __future__ import annotations

import importlib.util

import numpy as np
import pandas as pd
import pytest

from emergentflow.ml import DimensionReductionResult, reduce_dimensions
from emergentflow.ml.errors import MissingOptionalDependencyError


def _numeric_df(seed: int = 0) -> pd.DataFrame:
    # n=40 rows: sklearn's TSNE requires n_samples > perplexity (default perplexity=30).
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        {
            "a": rng.normal(size=40),
            "b": rng.normal(size=40),
            "c": rng.normal(size=40),
        }
    )


def test_pca_returns_result_with_components_and_variance():
    df = _numeric_df()
    result = reduce_dimensions(df, feature_cols=["a", "b", "c"], method="pca", n_components=2)
    assert isinstance(result, DimensionReductionResult)
    assert "component_1" in result.coordinates.columns
    assert "component_2" in result.coordinates.columns
    assert isinstance(result.explained_variance, pd.DataFrame)
    assert list(result.explained_variance.columns) == [
        "component",
        "explained_variance_ratio",
        "cumulative_variance_ratio",
    ]
    ratios = result.explained_variance["cumulative_variance_ratio"].tolist()
    assert ratios == sorted(ratios)
    assert ratios[-1] <= 1.0 + 1e-9


def test_tsne_has_no_explained_variance():
    df = _numeric_df()
    result = reduce_dimensions(df, feature_cols=["a", "b", "c"], method="tsne", n_components=2)
    assert result.explained_variance is None


def test_pca_deterministic_given_seed():
    df = _numeric_df()
    r1 = reduce_dimensions(df, feature_cols=["a", "b", "c"], method="pca", seed=42)
    r2 = reduce_dimensions(df, feature_cols=["a", "b", "c"], method="pca", seed=42)
    pd.testing.assert_frame_equal(r1.coordinates, r2.coordinates)


def test_unknown_method_raises():
    df = _numeric_df()
    with pytest.raises(ValueError):
        reduce_dimensions(df, feature_cols=["a", "b", "c"], method="nope")


def test_unknown_feature_col_raises():
    df = _numeric_df()
    with pytest.raises(ValueError):
        reduce_dimensions(df, feature_cols=["a", "nope"], method="pca")


def test_zero_components_raises():
    df = _numeric_df()
    with pytest.raises(ValueError):
        reduce_dimensions(df, feature_cols=["a", "b", "c"], method="pca", n_components=0)


def test_column_collision_raises():
    df = _numeric_df()
    df = df.assign(component_1=0.0)
    with pytest.raises(ValueError):
        reduce_dimensions(df, feature_cols=["a", "b", "c"], method="pca", n_components=1)


def test_umap_without_extra_raises_missing_dependency_error():
    assert importlib.util.find_spec("umap") is None, "this test assumes umap-learn is NOT installed"
    df = _numeric_df()
    with pytest.raises(MissingOptionalDependencyError):
        reduce_dimensions(df, feature_cols=["a", "b", "c"], method="umap")


def test_does_not_mutate_input():
    df = _numeric_df()
    before = df.copy()
    reduce_dimensions(df, feature_cols=["a", "b", "c"], method="pca")
    pd.testing.assert_frame_equal(df, before)
