"""Tests for the per-family summary builders (Epic 8, Story 3).

Covers the 6 builder functions in ``emergentflow.ml.summaries`` directly and the
``ef.ml.summarize`` public op end-to-end via the 4 seed estimators.
"""

from __future__ import annotations

import warnings

import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import StandardScaler
from sklearn.svm import OneClassSVM

from emergentflow.api import is_inspectable
from emergentflow.ml import fit_estimator, summarize
from emergentflow.ml.summaries import (
    summarize_classifier,
    summarize_clustering,
    summarize_decomposition,
    summarize_outlier,
    summarize_preprocessing,
    summarize_regressor,
)


def _make_classification_df() -> pd.DataFrame:
    """A small, linearly separable 2-class dataset (20 rows)."""
    x1 = [float(i) for i in range(20)]
    x2 = [float(i % 5) for i in range(20)]
    label = ["low" if i < 10 else "high" for i in range(20)]
    return pd.DataFrame({"x1": x1, "x2": x2, "label": label})


def _make_unsupervised_df() -> pd.DataFrame:
    """A small unlabeled dataset (20 rows, 2 numeric features)."""
    x1 = [float(i) for i in range(20)]
    x2 = [float(i % 5) for i in range(20)]
    return pd.DataFrame({"x1": x1, "x2": x2})


# ---------------------------------------------------------------------------
# Unit tests for each builder function
# ---------------------------------------------------------------------------


def test_summarize_classifier() -> None:
    df = _make_classification_df()
    X = df[["x1", "x2"]]
    y = df["label"]
    est = LogisticRegression(max_iter=1000, random_state=0).fit(X, y)
    result = summarize_classifier(est)
    assert "classes" in result
    assert "coefficients" in result
    assert result["classes"] == ["high", "low"]
    assert isinstance(result["coefficients"], list)
    for row in result["coefficients"]:
        assert isinstance(row, list)
        for v in row:
            assert isinstance(v, float)


def test_summarize_classifier_linear_svc() -> None:
    from sklearn.svm import LinearSVC

    X = _make_unsupervised_df()
    y = [0 if i < 10 else 1 for i in range(20)]
    est = LinearSVC(random_state=0, max_iter=10000).fit(X, y)
    result = summarize_classifier(est)
    assert "coefficients" in result
    assert isinstance(result["coefficients"], list)
    for v in result["coefficients"]:
        assert isinstance(v, list)
        for v2 in v:
            assert isinstance(v2, float)


def test_summarize_classifier_missing_attrs() -> None:
    result = summarize_classifier(object())
    assert result == {}


def test_summarize_regressor() -> None:
    df = _make_unsupervised_df()
    X = df[["x1", "x2"]]
    y = [float(i) for i in range(20)]
    est = LinearRegression().fit(X, y)
    result = summarize_regressor(est)
    assert "coefficients" in result
    assert isinstance(result["coefficients"], list)
    for v in result["coefficients"]:
        assert isinstance(v, float)
    assert "intercept" in result
    assert isinstance(result["intercept"], float)


def test_summarize_regressor_missing_attrs() -> None:
    result = summarize_regressor(object())
    assert result == {}


def test_summarize_decomposition() -> None:
    df = _make_unsupervised_df()
    X = df[["x1", "x2"]]
    est = PCA(n_components=2).fit(X)
    result = summarize_decomposition(est)
    assert "explained_variance_ratio" in result
    assert isinstance(result["explained_variance_ratio"], list)
    for v in result["explained_variance_ratio"]:
        assert isinstance(v, float)
    assert "n_components" in result
    assert isinstance(result["n_components"], int)
    assert result["n_components"] == 2
    assert "components" in result
    assert isinstance(result["components"], list)
    for row in result["components"]:
        assert isinstance(row, list)
        for v in row:
            assert isinstance(v, float)


def test_summarize_decomposition_missing_attrs() -> None:
    result = summarize_decomposition(object())
    assert result == {}


def test_summarize_clustering_kmeans() -> None:
    df = _make_unsupervised_df()
    X = df[["x1", "x2"]]
    est = KMeans(n_clusters=2, random_state=0, n_init=10).fit(X)
    result = summarize_clustering(est)
    assert "cluster_sizes" in result
    assert isinstance(result["cluster_sizes"], dict)
    for k, v in result["cluster_sizes"].items():
        assert isinstance(k, str)
        assert isinstance(v, int)
    assert "n_clusters" in result
    assert isinstance(result["n_clusters"], int)
    assert result["n_clusters"] == 2
    assert "inertia" in result
    assert isinstance(result["inertia"], float)


def test_summarize_clustering_gmm() -> None:
    df = _make_unsupervised_df()
    X = df[["x1", "x2"]]
    est = GaussianMixture(n_components=2, random_state=0).fit(X)
    result = summarize_clustering(est)
    assert "n_clusters" in result
    assert isinstance(result["n_clusters"], int)
    assert result["n_clusters"] == 2
    assert "weights" in result
    assert isinstance(result["weights"], list)
    for v in result["weights"]:
        assert isinstance(v, float)
    assert "converged" in result
    assert isinstance(result["converged"], bool)
    assert "cluster_sizes" not in result  # GMM has no labels_


def test_summarize_clustering_missing_attrs() -> None:
    result = summarize_clustering(object())
    assert result == {}


def test_summarize_outlier() -> None:
    df = _make_unsupervised_df()
    X = df[["x1", "x2"]]
    est = IsolationForest(contamination=0.1, random_state=0).fit(X)
    result = summarize_outlier(est)
    assert "contamination" in result
    assert result["contamination"] == 0.1
    assert "offset" in result
    assert isinstance(result["offset"], float)


def test_summarize_outlier_missing_attrs() -> None:
    result = summarize_outlier(object())
    assert result == {}


def test_summarize_outlier_array_valued_offset_no_deprecation_warning() -> None:
    """OneClassSVM.offset_ is a shape-(1,) ndarray, unlike IsolationForest's plain float.

    Regression test for a confirmed bug hunt finding (2026-07-21): float() on that
    ndim>0 array raised ``DeprecationWarning: Conversion of an array with ndim > 0 to
    a scalar is deprecated`` (NumPy 1.25), which upgrades to a hard TypeError in a
    future NumPy -- would silently break `ef.ml.summarize` for every OneClassSVM node.
    """
    df = _make_unsupervised_df()
    X = df[["x1", "x2"]]
    est = OneClassSVM().fit(X)
    assert est.offset_.ndim == 1  # sanity: this is the array-shaped case, not a plain float

    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        result = summarize_outlier(est)

    assert isinstance(result["offset"], float)


def test_summarize_preprocessing() -> None:
    df = _make_unsupervised_df()
    X = df[["x1", "x2"]]
    est = StandardScaler().fit(X)
    result = summarize_preprocessing(est)
    assert "mean" in result
    assert isinstance(result["mean"], list)
    for v in result["mean"]:
        assert isinstance(v, float)
    assert "scale" in result
    assert isinstance(result["scale"], list)
    for v in result["scale"]:
        assert isinstance(v, float)
    assert "variance" in result
    assert isinstance(result["variance"], list)
    for v in result["variance"]:
        assert isinstance(v, float)


def test_summarize_preprocessing_missing_attrs() -> None:
    result = summarize_preprocessing(object())
    assert result == {}


# ---------------------------------------------------------------------------
# End-to-end tests: ef.ml.summarize via the 4 seed estimators
# ---------------------------------------------------------------------------


def test_summarize_logistic_regression() -> None:
    df = _make_classification_df()
    model = fit_estimator(df, estimator="LogisticRegression", target="label")
    result = summarize(model)
    assert isinstance(result, dict)
    assert len(result) > 0
    assert "classes" in result
    assert "coefficients" in result


def test_summarize_standard_scaler() -> None:
    df = _make_unsupervised_df()
    transformer = fit_estimator(df, estimator="StandardScaler")
    result = summarize(transformer)
    assert isinstance(result, dict)
    assert len(result) > 0
    assert "mean" in result
    assert "scale" in result


def test_summarize_kmeans() -> None:
    df = _make_unsupervised_df()
    model = fit_estimator(df, estimator="KMeans", params={"n_clusters": 2, "random_state": 0})
    result = summarize(model)
    assert isinstance(result, dict)
    assert len(result) > 0
    assert "cluster_sizes" in result or "n_clusters" in result


def test_summarize_gaussian_mixture() -> None:
    df = _make_unsupervised_df()
    model = fit_estimator(
        df, estimator="GaussianMixture", params={"n_components": 2, "random_state": 0}
    )
    result = summarize(model)
    assert isinstance(result, dict)
    assert len(result) > 0
    assert "n_clusters" in result
    assert "weights" in result
    assert "converged" in result


def test_summarize_is_inspectable() -> None:
    df = _make_classification_df()
    model = fit_estimator(df, estimator="LogisticRegression", target="label")
    result = summarize(model)
    assert is_inspectable(result)


def test_summarize_unknown_estimator_returns_unsupported() -> None:
    from emergentflow.ml import FittedModel

    dummy = FittedModel(
        estimator_type="NotRegistered",
        task="classification",
        feature_names=[],
        target=None,
        estimator=object(),
    )
    result = summarize(dummy)
    assert result == {"kind": "unsupported"}
