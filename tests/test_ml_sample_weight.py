"""Regression tests for the `weight_col` / `sample_weight` passthrough (issue #164 Gap 4).

Every ML fit-op (`fit_estimator`, `train_regressor`, `train_classifier`,
`train_random_forest`, `cross_validate`, `grid_search`, `tune_model`) accepts an
optional ``weight_col`` naming a column of per-row sample weights, forwarded to the
underlying sklearn ``fit``. Guardrails: unknown columns, non-finite or negative
weights, non-fit archetypes, and weight-unaware estimators all raise typed errors.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from emergentflow.ml import (
    cross_validate,
    fit_estimator,
    grid_search,
    train_classifier,
    train_random_forest,
    train_regressor,
    tune_model,
)


def _make_df(n: int = 300, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        {
            "x": rng.normal(size=n),
            "y": 2.0 * rng.normal(size=n) + 1.0,
            "w": rng.uniform(0.5, 3.0, size=n),
            "g": np.arange(n) % 30,
        }
    )


def test_fit_estimator_weight_col_changes_fit():
    df = _make_df()
    un = fit_estimator(df, estimator="Ridge", target="y", features=["x"])
    wtd = fit_estimator(df, estimator="Ridge", target="y", features=["x"], weight_col="w")
    assert not np.allclose(un.estimator.coef_, wtd.estimator.coef_)


def test_fit_estimator_unknown_weight_col_raises():
    df = _make_df()
    with pytest.raises(ValueError, match="weight_col"):
        fit_estimator(df, estimator="Ridge", target="y", features=["x"], weight_col="nope")


def test_fit_estimator_negative_weight_raises():
    df = _make_df()
    df["wneg"] = -1.0
    with pytest.raises(ValueError, match="non-negative"):
        fit_estimator(df, estimator="Ridge", target="y", features=["x"], weight_col="wneg")


def test_fit_estimator_non_fit_archetype_rejects_weight_col():
    df = _make_df()
    with pytest.raises(ValueError, match="fit-archetype"):
        fit_estimator(df, estimator="KMeans", features=["x"], weight_col="w")


def test_train_regressor_weight_col():
    df = _make_df()
    a = train_regressor(df, target="y", features=["x"]).estimator
    b = train_regressor(df, target="y", features=["x"], weight_col="w").estimator
    assert not np.allclose(a.coef_, b.coef_)


def test_train_classifier_weight_col():
    rng = np.random.default_rng(1)
    df = pd.DataFrame(
        {
            "x": rng.normal(size=200),
            "c": rng.integers(0, 2, size=200),
            "w": rng.uniform(0.5, 3.0, size=200),
        }
    )
    res = train_classifier(df, target="c", features=["x"], weight_col="w")
    assert 0.0 <= res.accuracy <= 1.0


def test_train_random_forest_weight_col():
    rng = np.random.default_rng(2)
    df = pd.DataFrame(
        {
            "x": rng.normal(size=200),
            "c": rng.integers(0, 2, size=200),
            "w": rng.uniform(0.5, 3.0, size=200),
        }
    )
    res = train_random_forest(df, target="c", features=["x"], weight_col="w")
    assert res.estimator_type in ("RandomForestClassifier", "RandomForestRegressor")


def test_cross_validate_weight_col_grouped():
    df = _make_df()
    res = cross_validate(
        df,
        estimator="Ridge",
        target="y",
        features=["x"],
        cv=3,
        cv_strategy="grouped",
        group_col="g",
        scoring="r2",
        weight_col="w",
    )
    assert (res["splitter"] == "GroupKFold").all()
    assert len(res) == 3


def test_grid_search_weight_col():
    df = _make_df()
    model, cv_results = grid_search(
        df,
        estimator="Ridge",
        param_grid={"alpha": [0.1, 1.0]},
        target="y",
        features=["x"],
        cv=3,
        weight_col="w",
    )
    assert model.estimator_type == "Ridge"
    assert len(cv_results) == 2


def test_tune_model_weight_col():
    df = _make_df()
    model, _ = tune_model(
        df,
        estimator="Ridge",
        param_distributions={"alpha": [0.1, 1.0]},
        target="y",
        features=["x"],
        cv=3,
        n_iter=2,
        random_state=0,
        weight_col="w",
    )
    assert model.estimator_type == "Ridge"


def test_weight_col_registered_via_public_ops_only_accepts_existing_columns():
    df = _make_df(n=50)
    with pytest.raises(ValueError, match="weight_col"):
        train_regressor(df, target="y", features=["x"], weight_col="not_a_column")


def test_helper_rejects_estimator_without_sample_weight():
    from emergentflow.ml import _resolve_sample_weight
    from emergentflow.ml.errors import UnsupportedEstimatorOptionError

    df = _make_df(n=50)

    class _NoWeightFit:
        def fit(self, X, y=None):
            return self

    with pytest.raises(UnsupportedEstimatorOptionError, match="sample_weight"):
        _resolve_sample_weight(df, "w", est=_NoWeightFit())

    class _KwargsFit:
        def fit(self, X, y=None, **kwargs):
            return self

    # **kwargs counts as accepting sample_weight
    assert isinstance(_resolve_sample_weight(df, "w", est=_KwargsFit()), pd.Series)
