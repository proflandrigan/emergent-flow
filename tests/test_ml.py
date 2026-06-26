"""Tests for ``emergentflow.ml`` (Epic 1, Story 8).

Covers ``ef.ml.train_classifier``: a thin wrapper over
``sklearn.linear_model.LogisticRegression`` that trains a classifier and
returns inspectable metrics (never the fitted estimator itself, per Story 7
rule 4).
"""

from __future__ import annotations

import pandas as pd
import pytest

import emergentflow.types.catalog  # noqa: F401  (triggers token registration)
from emergentflow.api import PUBLIC_OPS, is_inspectable
from emergentflow.ml import (
    FOREST_TASKS,
    ClassifierResult,
    EvaluationResult,
    FittedModel,
    evaluate,
    predict,
    train_classifier,
    train_random_forest,
    train_regressor,
    train_test_split,
)
from emergentflow.types.registry import registry


def _make_df() -> pd.DataFrame:
    """A small, linearly separable 2-class dataset (40 rows).

    ``label`` is fully determined by a threshold on ``x1 + x2``, so the
    classifier should achieve high, stable accuracy regardless of which rows
    land in the train/test split.
    """
    x1 = [float(i) for i in range(20)] + [float(i) for i in range(20)]
    x2 = [float(i % 5) for i in range(40)]
    label = ["low" if (a + b) < 15 else "high" for a, b in zip(x1, x2, strict=True)]
    return pd.DataFrame({"x1": x1, "x2": x2, "label": label})


def test_train_returns_result() -> None:
    df = _make_df()
    result = train_classifier(df, target="label", random_state=0)
    assert isinstance(result, ClassifierResult)
    # Must not be (or expose) the opaque sklearn estimator (Story 7 rule 4).
    assert not hasattr(result, "predict")


def test_train_accuracy_in_range() -> None:
    df = _make_df()
    result = train_classifier(df, target="label", random_state=0)
    assert 0.0 <= result.accuracy <= 1.0


def test_train_counts_sum_to_total() -> None:
    df = _make_df()
    result = train_classifier(df, target="label", random_state=0)
    assert result.n_train + result.n_test == len(df)


def test_train_classes_and_coefficients() -> None:
    df = _make_df()
    result = train_classifier(df, target="label", random_state=0)
    assert len(result.classes) == 2
    assert isinstance(result.coefficients, list)
    assert len(result.coefficients) > 0
    for row in result.coefficients:
        assert isinstance(row, list)
        assert len(row) == len(result.feature_names)
        for value in row:
            assert isinstance(value, float)


def test_train_deterministic() -> None:
    df = _make_df()
    first = train_classifier(df, target="label", random_state=0)
    second = train_classifier(df, target="label", random_state=0)
    assert first.accuracy == second.accuracy
    assert first.coefficients == second.coefficients


def test_train_does_not_mutate_input() -> None:
    df = _make_df()
    original = df.copy()
    train_classifier(df, target="label", random_state=0)
    assert df.equals(original)


def test_train_missing_target_raises() -> None:
    df = _make_df()
    with pytest.raises(ValueError):
        train_classifier(df, target="bogus", random_state=0)


def test_train_registered_as_public_op() -> None:
    assert "ef.ml.train_classifier" in PUBLIC_OPS


# ---------------------------------------------------------------------------
# train_test_split (Epic 1, Story 9)
# ---------------------------------------------------------------------------


def test_split_sizes_sum_to_row_count() -> None:
    df = _make_df()
    train_df, test_df = train_test_split(df, test_size=0.25, random_state=0)
    assert len(train_df) + len(test_df) == len(df)


def test_split_deterministic() -> None:
    df = _make_df()
    train1, test1 = train_test_split(df, random_state=0)
    train2, test2 = train_test_split(df, random_state=0)
    assert train1.equals(train2)
    assert test1.equals(test2)


def test_split_test_size_out_of_range_raises() -> None:
    df = _make_df()
    with pytest.raises(ValueError):
        train_test_split(df, test_size=0.0)
    with pytest.raises(ValueError):
        train_test_split(df, test_size=1.0)
    with pytest.raises(ValueError):
        train_test_split(df, test_size=1.5)


def test_split_returns_two_dataframes() -> None:
    df = _make_df()
    result = train_test_split(df, test_size=0.25, random_state=0)
    assert isinstance(result, tuple)
    assert len(result) == 2
    assert isinstance(result[0], pd.DataFrame)
    assert isinstance(result[1], pd.DataFrame)


def test_split_registered_as_public_op() -> None:
    assert "ef.ml.train_test_split" in PUBLIC_OPS


def test_split_does_not_mutate_input() -> None:
    df = _make_df()
    original = df.copy()
    train_test_split(df, test_size=0.25, random_state=0)
    assert df.equals(original)


# ---------------------------------------------------------------------------
# train_regressor (Epic 1, Story 10)
# ---------------------------------------------------------------------------


def _make_linear_df() -> pd.DataFrame:
    """A small linear dataset (20 rows): y = 2*x + 1 + tiny noise-free offset."""
    x = [float(i) for i in range(20)]
    y = [2.0 * v + 1.0 for v in x]
    return pd.DataFrame({"x": x, "y": y})


def test_regressor_returns_fitted_model() -> None:
    df = _make_linear_df()
    result = train_regressor(df, target="y")
    assert isinstance(result, FittedModel)
    assert result.task == "regression"
    assert result.estimator_type == "LinearRegression"


def test_regressor_feature_names_and_target() -> None:
    df = _make_linear_df()
    result = train_regressor(df, target="y")
    assert result.target == "y"
    assert result.feature_names == ["x"]


def test_regressor_estimator_has_predict() -> None:
    df = _make_linear_df()
    result = train_regressor(df, target="y")
    assert hasattr(result.estimator, "predict")


def test_regressor_unknown_target_raises() -> None:
    df = _make_linear_df()
    with pytest.raises(ValueError):
        train_regressor(df, target="bogus")


def test_regressor_registered_as_public_op() -> None:
    assert "ef.ml.train_regressor" in PUBLIC_OPS


def test_regressor_does_not_mutate_input() -> None:
    df = _make_linear_df()
    original = df.copy()
    train_regressor(df, target="y")
    assert df.equals(original)


def test_regressor_deterministic() -> None:
    df = _make_linear_df()
    first = train_regressor(df, target="y")
    second = train_regressor(df, target="y")
    assert first.estimator.coef_.tolist() == second.estimator.coef_.tolist()


# ---------------------------------------------------------------------------
# FittedModel / EvaluationResult (Story 6 ML foundation)
# ---------------------------------------------------------------------------


def test_fitted_model_is_dataclass_and_inspectable() -> None:
    fm = FittedModel(
        estimator_type="LinearRegression",
        task="regression",
        feature_names=["x1", "x2"],
        target="y",
        estimator=object(),
    )
    import dataclasses

    assert dataclasses.is_dataclass(fm)
    assert is_inspectable(fm)


def test_evaluation_result_is_inspectable() -> None:
    er = EvaluationResult(task="regression", n=100, metrics={"rmse": 0.42, "r2": 0.91})
    assert is_inspectable(er)


def test_type_tokens_registered() -> None:
    assert registry.is_registered("Model")
    assert registry.is_registered("Predictions")
    assert registry.is_registered("EvaluationResult")


# ---------------------------------------------------------------------------
# train_random_forest (Epic 1, Story 11)
# ---------------------------------------------------------------------------


def _make_rf_df() -> pd.DataFrame:
    """A small, linearly separable 2-class dataset (40 rows) for random-forest tests."""
    x1 = [float(i) for i in range(20)] + [float(i) for i in range(20)]
    x2 = [float(i % 5) for i in range(40)]
    label = ["low" if (a + b) < 15 else "high" for a, b in zip(x1, x2, strict=True)]
    return pd.DataFrame({"x1": x1, "x2": x2, "label": label})


def test_random_forest_classification_returns_fitted_model() -> None:
    df = _make_rf_df()
    result = train_random_forest(df, target="label", task="classification", random_state=0)
    assert isinstance(result, FittedModel)
    assert result.estimator_type == "RandomForestClassifier"
    assert result.task == "classification"


def test_random_forest_regression_returns_fitted_model() -> None:
    df = pd.DataFrame(
        {
            "x": [float(i) for i in range(20)],
            "y": [2.0 * float(i) + 1.0 for i in range(20)],
        }
    )
    result = train_random_forest(df, target="y", task="regression", random_state=0)
    assert isinstance(result, FittedModel)
    assert result.estimator_type == "RandomForestRegressor"
    assert result.task == "regression"


def test_random_forest_bad_task_raises() -> None:
    df = _make_rf_df()
    with pytest.raises(ValueError):
        train_random_forest(df, target="label", task="bogus", random_state=0)


def test_random_forest_unknown_target_raises() -> None:
    df = _make_rf_df()
    with pytest.raises(ValueError):
        train_random_forest(df, target="nonexistent", task="classification", random_state=0)


def test_random_forest_registered_as_public_op() -> None:
    assert "ef.ml.train_random_forest" in PUBLIC_OPS


def test_random_forest_deterministic() -> None:
    df = _make_rf_df()
    X = df[["x1", "x2"]]
    first = train_random_forest(df, target="label", task="classification", random_state=0)
    second = train_random_forest(df, target="label", task="classification", random_state=0)
    assert first.estimator.predict(X).tolist() == second.estimator.predict(X).tolist()


def test_random_forest_does_not_mutate_input() -> None:
    df = _make_rf_df()
    original = df.copy()
    train_random_forest(df, target="label", task="classification", random_state=0)
    assert df.equals(original)


def test_random_forest_forest_tasks_constant() -> None:
    assert "classification" in FOREST_TASKS
    assert "regression" in FOREST_TASKS


# ---------------------------------------------------------------------------
# predict (Epic 1, Story 12)
# ---------------------------------------------------------------------------


def test_predict_adds_prediction_column() -> None:
    df = _make_linear_df()
    model = train_regressor(df, target="y")
    result = predict(model, df)
    assert "prediction" in result.columns
    assert len(result) == len(df)


def test_predict_does_not_mutate_input() -> None:
    df = _make_linear_df()
    original = df.copy()
    model = train_regressor(df, target="y")
    predict(model, df)
    assert df.equals(original)


def test_predict_missing_feature_column_raises() -> None:
    df = _make_linear_df()
    model = train_regressor(df, target="y")
    df_bad = df.drop(columns=["x"])
    with pytest.raises(ValueError):
        predict(model, df_bad)


def test_predict_registered_as_public_op() -> None:
    assert "ef.ml.predict" in PUBLIC_OPS


# ---------------------------------------------------------------------------
# evaluate (Epic 1, Story 13)
# ---------------------------------------------------------------------------


def test_evaluate_regression_returns_evaluation_result() -> None:
    df = _make_linear_df()
    model = train_regressor(df, target="y")
    result = evaluate(model, df)
    assert isinstance(result, EvaluationResult)
    assert result.task == "regression"


def test_evaluate_regression_metrics_keys() -> None:
    df = _make_linear_df()
    model = train_regressor(df, target="y")
    result = evaluate(model, df)
    assert set(result.metrics.keys()) == {"r2", "mae", "rmse"}


def test_evaluate_regression_r2_near_one() -> None:
    """On a perfectly linear y=2x+1 dataset the regressor should fit exactly."""
    df = _make_linear_df()
    model = train_regressor(df, target="y")
    result = evaluate(model, df)
    assert result.metrics["r2"] > 0.99


def test_evaluate_regression_metrics_are_python_floats() -> None:
    df = _make_linear_df()
    model = train_regressor(df, target="y")
    result = evaluate(model, df)
    for v in result.metrics.values():
        assert type(v) is float


def test_evaluate_classification_returns_accuracy() -> None:
    df = _make_rf_df()
    model = train_random_forest(df, target="label", task="classification", random_state=0)
    result = evaluate(model, df)
    assert isinstance(result, EvaluationResult)
    assert result.task == "classification"
    assert set(result.metrics.keys()) == {"accuracy"}
    assert 0.0 <= result.metrics["accuracy"] <= 1.0


def test_evaluate_n_equals_row_count() -> None:
    df = _make_linear_df()
    model = train_regressor(df, target="y")
    result = evaluate(model, df)
    assert result.n == len(df)


def test_evaluate_missing_target_raises() -> None:
    df = _make_linear_df()
    model = train_regressor(df, target="y")
    df_no_target = df.drop(columns=["y"])
    with pytest.raises(ValueError):
        evaluate(model, df_no_target)


def test_evaluate_registered_as_public_op() -> None:
    assert "ef.ml.evaluate" in PUBLIC_OPS


def test_evaluate_does_not_mutate_input() -> None:
    df = _make_linear_df()
    original = df.copy()
    model = train_regressor(df, target="y")
    evaluate(model, df)
    assert df.equals(original)
