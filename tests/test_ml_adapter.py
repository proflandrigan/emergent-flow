"""Tests for the sklearn estimator adapter (Epic 8, Story 2).

Covers ``ef.ml.fit_estimator`` / ``ef.ml.apply_estimator`` — the single generic adapter
every archetype node routes through (ADR 0016) — and the allow-list registry
(``emergentflow.ml.registry``) it validates against. See ``tests/test_ml.py`` for the
pre-existing Epic 1/6 ``train_*``/``predict``/``evaluate`` tests, not duplicated here.
"""

from __future__ import annotations

import pandas as pd
import pytest

from emergentflow.api import PUBLIC_OPS, is_inspectable
from emergentflow.ml import FittedModel, FittedTransformer, apply_estimator, fit_estimator
from emergentflow.ml.errors import (
    InvalidEstimatorParamsError,
    MLAdapterError,
    UnknownEstimatorError,
)
from emergentflow.ml.registry import get_estimator_spec, known_estimator_keys


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
# Registry (seed catalog)
# ---------------------------------------------------------------------------


def test_seed_catalog_registers_expected_keys() -> None:
    assert set(known_estimator_keys()) == {
        "GaussianMixture",
        "KMeans",
        "LogisticRegression",
        "StandardScaler",
    }


def test_seed_catalog_archetypes() -> None:
    assert get_estimator_spec("LogisticRegression").archetype == "fit"
    assert get_estimator_spec("LogisticRegression").task == "classification"
    assert get_estimator_spec("StandardScaler").archetype == "fit_transform"
    assert get_estimator_spec("KMeans").archetype == "cluster_detect"
    assert get_estimator_spec("GaussianMixture").archetype == "cluster_detect"


def test_get_estimator_spec_unknown_key_raises() -> None:
    with pytest.raises(UnknownEstimatorError):
        get_estimator_spec("NotARealEstimator")


def test_unknown_estimator_error_is_ml_adapter_error() -> None:
    with pytest.raises(MLAdapterError):
        get_estimator_spec("NotARealEstimator")


# ---------------------------------------------------------------------------
# fit_estimator -- fit archetype (supervised)
# ---------------------------------------------------------------------------


def test_fit_estimator_fit_archetype_returns_fitted_model() -> None:
    df = _make_classification_df()
    model = fit_estimator(df, estimator="LogisticRegression", target="label")
    assert isinstance(model, FittedModel)
    assert model.estimator_type == "LogisticRegression"
    assert model.task == "classification"
    assert model.target == "label"
    assert model.feature_names == ["x1", "x2"]


def test_fit_estimator_fit_archetype_requires_target() -> None:
    df = _make_classification_df()
    with pytest.raises(ValueError):
        fit_estimator(df, estimator="LogisticRegression")


def test_fit_estimator_unknown_estimator_raises() -> None:
    df = _make_classification_df()
    with pytest.raises(UnknownEstimatorError):
        fit_estimator(df, estimator="NotARealEstimator", target="label")


def test_fit_estimator_bad_kwargs_raises() -> None:
    df = _make_classification_df()
    with pytest.raises(InvalidEstimatorParamsError):
        fit_estimator(df, estimator="LogisticRegression", target="label", params={"bogus_kwarg": 1})


def test_fit_estimator_deterministic_given_random_state() -> None:
    df = _make_classification_df()
    first = fit_estimator(
        df, estimator="LogisticRegression", target="label", params={"random_state": 0}
    )
    second = fit_estimator(
        df, estimator="LogisticRegression", target="label", params={"random_state": 0}
    )
    assert isinstance(first, FittedModel)
    assert isinstance(second, FittedModel)
    X = df[["x1", "x2"]]
    assert first.estimator.predict(X).tolist() == second.estimator.predict(X).tolist()


def test_fit_estimator_does_not_mutate_input() -> None:
    df = _make_classification_df()
    original = df.copy()
    fit_estimator(df, estimator="LogisticRegression", target="label")
    assert df.equals(original)


def test_fit_estimator_registered_as_public_op() -> None:
    assert "ef.ml.fit_estimator" in PUBLIC_OPS


def test_fit_estimator_result_is_inspectable() -> None:
    df = _make_classification_df()
    model = fit_estimator(df, estimator="LogisticRegression", target="label")
    assert is_inspectable(model)


# ---------------------------------------------------------------------------
# fit_estimator -- fit_transform archetype (unsupervised transformer)
# ---------------------------------------------------------------------------


def test_fit_estimator_fit_transform_archetype_returns_fitted_transformer() -> None:
    df = _make_unsupervised_df()
    transformer = fit_estimator(df, estimator="StandardScaler")
    assert isinstance(transformer, FittedTransformer)
    assert transformer.estimator_type == "StandardScaler"
    assert transformer.feature_names == ["x1", "x2"]
    assert hasattr(transformer.transformer, "transform")


def test_fit_estimator_fit_transform_ignores_target() -> None:
    df = _make_unsupervised_df()
    transformer = fit_estimator(df, estimator="StandardScaler", target="x1")
    assert isinstance(transformer, FittedTransformer)


def test_fit_estimator_fit_transform_result_is_inspectable() -> None:
    df = _make_unsupervised_df()
    transformer = fit_estimator(df, estimator="StandardScaler")
    assert is_inspectable(transformer)


# ---------------------------------------------------------------------------
# fit_estimator -- cluster_detect archetype (unsupervised label/score)
# ---------------------------------------------------------------------------


def test_fit_estimator_cluster_detect_archetype_returns_fitted_model() -> None:
    df = _make_unsupervised_df()
    model = fit_estimator(df, estimator="KMeans", params={"n_clusters": 2, "random_state": 0})
    assert isinstance(model, FittedModel)
    assert model.estimator_type == "KMeans"
    assert model.task == "clustering"
    assert model.target is None


def test_fit_estimator_cluster_detect_deterministic_given_random_state() -> None:
    df = _make_unsupervised_df()
    params = {"n_clusters": 2, "random_state": 0}
    first = fit_estimator(df, estimator="KMeans", params=params)
    second = fit_estimator(df, estimator="KMeans", params=params)
    assert isinstance(first, FittedModel)
    assert isinstance(second, FittedModel)
    X = df[["x1", "x2"]]
    assert first.estimator.predict(X).tolist() == second.estimator.predict(X).tolist()


# ---------------------------------------------------------------------------
# apply_estimator -- predict
# ---------------------------------------------------------------------------


def test_apply_estimator_predict_adds_prediction_column() -> None:
    df = _make_classification_df()
    model = fit_estimator(df, estimator="LogisticRegression", target="label")
    result = apply_estimator(model, df, op="predict")
    assert "prediction" in result.columns
    assert len(result) == len(df)


def test_apply_estimator_predict_does_not_mutate_input() -> None:
    df = _make_classification_df()
    original = df.copy()
    model = fit_estimator(df, estimator="LogisticRegression", target="label")
    apply_estimator(model, df, op="predict")
    assert df.equals(original)


def test_apply_estimator_predict_on_transformer_raises() -> None:
    df = _make_unsupervised_df()
    transformer = fit_estimator(df, estimator="StandardScaler")
    with pytest.raises(ValueError):
        apply_estimator(transformer, df, op="predict")


def test_apply_estimator_missing_feature_column_raises() -> None:
    df = _make_classification_df()
    model = fit_estimator(df, estimator="LogisticRegression", target="label")
    df_bad = df.drop(columns=["x1"])
    with pytest.raises(ValueError):
        apply_estimator(model, df_bad, op="predict")


def test_apply_estimator_registered_as_public_op() -> None:
    assert "ef.ml.apply_estimator" in PUBLIC_OPS


# ---------------------------------------------------------------------------
# apply_estimator -- transform
# ---------------------------------------------------------------------------


def test_apply_estimator_transform_adds_component_columns() -> None:
    df = _make_unsupervised_df()
    transformer = fit_estimator(df, estimator="StandardScaler")
    result = apply_estimator(transformer, df, op="transform")
    assert "component_0" in result.columns
    assert "component_1" in result.columns
    assert len(result) == len(df)


def test_apply_estimator_transform_does_not_mutate_input() -> None:
    df = _make_unsupervised_df()
    original = df.copy()
    transformer = fit_estimator(df, estimator="StandardScaler")
    apply_estimator(transformer, df, op="transform")
    assert df.equals(original)


def test_apply_estimator_transform_on_model_raises() -> None:
    df = _make_classification_df()
    model = fit_estimator(df, estimator="LogisticRegression", target="label")
    with pytest.raises(ValueError):
        apply_estimator(model, df, op="transform")


# ---------------------------------------------------------------------------
# apply_estimator -- score_samples
# ---------------------------------------------------------------------------


def test_apply_estimator_score_samples_adds_score_column() -> None:
    df = _make_unsupervised_df()
    model = fit_estimator(df, estimator="GaussianMixture", params={"n_components": 1})
    result = apply_estimator(model, df, op="score_samples")
    assert "score" in result.columns
    assert len(result) == len(df)


def test_apply_estimator_score_samples_does_not_mutate_input() -> None:
    df = _make_unsupervised_df()
    original = df.copy()
    model = fit_estimator(df, estimator="GaussianMixture", params={"n_components": 1})
    apply_estimator(model, df, op="score_samples")
    assert df.equals(original)


# ---------------------------------------------------------------------------
# apply_estimator -- op validation
# ---------------------------------------------------------------------------


def test_apply_estimator_unknown_op_raises() -> None:
    df = _make_classification_df()
    model = fit_estimator(df, estimator="LogisticRegression", target="label")
    with pytest.raises(ValueError):
        apply_estimator(model, df, op="bogus")
