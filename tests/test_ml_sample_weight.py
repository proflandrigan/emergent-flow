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


def test_weight_col_is_never_auto_selected_as_a_feature():
    df = _make_df().drop(columns="g")
    df["w"] = df["y"] - df["y"].min() + 1.0  # positive, finite, and a pure function of the target
    assert fit_estimator(df, estimator="Ridge", target="y", weight_col="w").feature_names == ["x"]
    assert train_regressor(df, target="y", weight_col="w").feature_names == ["x"]
    rf = train_random_forest(df, target="y", task="regression", weight_col="w")
    assert rf.feature_names == ["x"]
    clf_df = df.assign(y=(df["y"] > df["y"].median()).astype(int))
    assert train_classifier(clf_df, target="y", weight_col="w").feature_names == ["x"]
    model, _ = grid_search(
        df, estimator="Ridge", param_grid={"alpha": [0.1, 1.0]}, target="y", cv=3, weight_col="w"
    )
    assert model.feature_names == ["x"]
    model, _ = tune_model(
        df,
        estimator="Ridge",
        param_distributions={"alpha": [0.1, 1.0]},
        target="y",
        n_iter=2,
        cv=3,
        weight_col="w",
    )
    assert model.feature_names == ["x"]
    cv = cross_validate(df, estimator="Ridge", target="y", cv=3, scoring="r2", weight_col="w")
    assert (cv["test_score"] < 0.999).all()  # the leaked weight would have scored a perfect 1.0
    with pytest.raises(ValueError, match="auxiliary"):
        fit_estimator(df, estimator="Ridge", target="y", features=["x", "w"], weight_col="w")


def test_group_col_is_never_auto_selected_as_a_feature():
    df = _make_df().drop(columns="w")
    df["g"] = np.argsort(np.argsort(df["y"].to_numpy()))  # a group id that ranks the target
    res = cross_validate(
        df, estimator="Ridge", target="y", cv=3, cv_strategy="grouped", group_col="g", scoring="r2"
    )
    assert (res["test_score"] < 0.999).all()


def test_weight_col_must_be_numeric_non_bool():
    df = _make_df()
    df["flag"] = df["w"] > 1.0
    with pytest.raises(ValueError, match="flag"):
        fit_estimator(df, estimator="Ridge", target="y", features=["x"], weight_col="flag")
    df["label"] = "a"
    with pytest.raises(ValueError, match="label"):
        fit_estimator(df, estimator="Ridge", target="y", features=["x"], weight_col="label")


def test_grid_search_zero_weight_fold_raises_instead_of_arbitrary_best():
    # sklearn refuses all-zero weights at fit time, but a fold whose *test* rows all carry zero
    # weight scores NaN silently: with KFold's contiguous folds, zeroing the first 20 of 60 rows
    # makes every candidate's mean_test_score NaN and the "best" model arbitrary.
    df = _make_df(n=60)
    df["w"] = np.where(np.arange(len(df)) < 20, 0.0, 1.0)
    with pytest.raises(ValueError, match="finite cross-validation score"):
        grid_search(
            df,
            estimator="Ridge",
            param_grid={"alpha": [0.1, 1.0]},
            target="y",
            features=["x"],
            cv=3,
            weight_col="w",
        )


def test_fit_estimator_non_fit_archetype_weight_col_is_typed():
    from emergentflow.ml.errors import UnsupportedEstimatorOptionError

    df = _make_df()
    with pytest.raises(UnsupportedEstimatorOptionError, match="fit-archetype"):
        fit_estimator(df, estimator="KMeans", features=["x"], weight_col="w")


def test_compare_models_weight_col_runs_and_never_uses_the_weight_as_a_feature():
    from emergentflow.ml import compare_models

    df = _make_df(n=200).drop(columns="g")
    comparison, best = compare_models(
        df, task="regression", target="y", cv=3, weight_col="w", estimators=["Ridge", "Lasso"]
    )
    assert best.feature_names == ["x"]
    assert set(comparison["status"]) == {"ok"}
    with pytest.raises(ValueError, match="weight_col"):
        compare_models(df, task="regression", target="y", cv=3, weight_col="nope")


def test_compare_models_reports_estimators_without_sample_weight_support():
    import inspect

    from emergentflow.ml import compare_models
    from emergentflow.ml.registry import get_estimator_spec, keys_for_archetype

    def _accepts_weight(key: str) -> bool:
        params = inspect.signature(get_estimator_spec(key).sklearn_class.fit).parameters
        return "sample_weight" in params or any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()
        )

    regressors = [
        k for k in keys_for_archetype("fit") if get_estimator_spec(k).task == "regression"
    ]
    unsupported = [k for k in regressors if not _accepts_weight(k)]
    if not unsupported:
        pytest.skip("every curated regressor accepts sample_weight")
    df = _make_df(n=200).drop(columns="g")
    comparison, _ = compare_models(
        df,
        task="regression",
        target="y",
        cv=3,
        weight_col="w",
        estimators=["Ridge", unsupported[0]],
    )
    status = comparison.set_index("estimator")["status"]
    assert status["Ridge"] == "ok"
    assert "sample_weight" in status[unsupported[0]]


def test_fit_pipeline_weight_col_reaches_the_final_step():
    from emergentflow.ml import fit_pipeline
    from emergentflow.ml.errors import UnsupportedEstimatorOptionError

    df = _make_df(n=200).drop(columns="g")
    steps = [{"estimator": "StandardScaler"}, {"estimator": "Ridge"}]
    plain = fit_pipeline(df, steps=steps, target="y")
    weighted = fit_pipeline(df, steps=steps, target="y", weight_col="w")
    assert weighted.feature_names == ["x"]
    assert plain.estimator[-1].coef_ != pytest.approx(weighted.estimator[-1].coef_)
    with pytest.raises(UnsupportedEstimatorOptionError, match="final step"):
        fit_pipeline(
            df, steps=[{"estimator": "StandardScaler"}, {"estimator": "KMeans"}], weight_col="w"
        )


def test_ml_nodes_treat_empty_weight_col_as_unset():
    from emergentflow.nodes.examples import FitEstimator

    df = _make_df(n=120).drop(columns="g")
    defn = FitEstimator()
    node = defn.instantiate(estimator="Ridge", target="y", features=["x"], weight_col="")
    executed = defn.execute(node, inputs={"frame": df.copy()})["model"]
    scope = {"frame": df.copy()}
    exec(defn.preview(node).render(), scope)  # noqa: S102 - test-only on our own emitted code
    assert executed.feature_names == scope["model"].feature_names
    assert executed.estimator.coef_ == pytest.approx(scope["model"].estimator.coef_)


def test_all_zero_weight_col_raises_clear_error_everywhere():
    # An all-zero sample-weight column makes every fit degenerate; sklearn surfaces it as a
    # cryptic "All the N fits failed" out of cross_validate / grid_search, so the SDK must
    # reject it up front with a clear message (issue #164 follow-up).
    df = _make_df(n=60)
    df["w0"] = 0.0
    match = "at least one non-zero"
    for call in (
        lambda: fit_estimator(df, estimator="Ridge", target="y", features=["x"], weight_col="w0"),
        lambda: train_regressor(df, target="y", features=["x"], weight_col="w0"),
        lambda: cross_validate(df, estimator="Ridge", target="y", features=["x"], weight_col="w0"),
        lambda: grid_search(
            df,
            estimator="Ridge",
            target="y",
            features=["x"],
            weight_col="w0",
            param_grid={"alpha": [1.0]},
        ),
    ):
        with pytest.raises(ValueError, match=match):
            call()


def test_partially_zero_weight_col_still_accepted():
    # Zero weights on SOME rows are legitimate (e.g. down-weighting noisy rows); only an
    # all-zero column is degenerate.
    df = _make_df(n=60)
    df["w_part"] = np.where(np.arange(60) < 20, 0.0, 1.0)
    out = cross_validate(df, estimator="Ridge", target="y", features=["x"], weight_col="w_part")
    assert len(out) == 5
