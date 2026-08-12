"""
Golden + equivalence tests for the ensembling nodes and their backends.

Covers ``ensemble_model``, ``blend_models``, and ``stack_models`` (Feature 2 of the
ml_feature_addons_1 plan). Because the produced ensemble ``estimator_type`` values
(e.g. ``VotingClassifier``, ``StackingClassifier``) are intentionally NOT in the curated
registry, these tests key equivalence on raw ``predict`` output rather than on
``ef.ml.summarize`` (which would report ``{"kind": "unsupported"}`` for all of them).
"""

from __future__ import annotations

import ast
import subprocess
import sys

import pandas as pd
import pytest

from emergentflow.codegen.compiler import compile_to_code
from emergentflow.ir.common import Direction
from emergentflow.ir.edge import Edge, PortRef
from emergentflow.ir.graph import Graph
from emergentflow.ml import (
    blend_models,
    ensemble_model,
    fit_estimator,
    stack_models,
    tune_model,
)
from emergentflow.nodes.examples import (
    BlendModels,
    EnsembleModel,
    FitEstimator,
    LoadSample,
    StackModels,
    TuneModel,
)


def _out_port(node, name):
    return next(p for p in node.ports if p.direction == Direction.OUT and p.name == name)


def _in_port(node, name):
    return next(p for p in node.ports if p.direction == Direction.IN and p.name == name)


def _run_codegen(definition, node, scope):
    frag = definition.preview(node)
    exec(frag.render(), scope)  # noqa: S102 -- test-only, on our own emitted code
    return scope


def _classification_df() -> pd.DataFrame:
    x1 = [float(i) for i in range(20)] + [float(i) for i in range(20)]
    x2 = [float(i % 5) for i in range(40)]
    label = [("low" if i % 2 == 0 else "high") for i in range(40)]
    return pd.DataFrame({"x1": x1, "x2": x2, "label": label})


def _regression_df() -> pd.DataFrame:
    x1 = [float(i) for i in range(30)]
    x2 = [float(i % 5) for i in range(30)]
    y = [2 * a + 3 * b + 1.0 for a, b in zip(x1, x2, strict=True)]
    return pd.DataFrame({"x1": x1, "x2": x2, "y": y})


def _fitted_classifier(df):
    return fit_estimator(df, estimator="LogisticRegression", target="label", features=["x1", "x2"])


def _second_classifier(df):
    return fit_estimator(
        df, estimator="RandomForestClassifier", target="label", features=["x1", "x2"]
    )


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------


def test_ensemble_model_bagging_classification():
    df = _classification_df()
    base = _fitted_classifier(df)
    e = ensemble_model(base, df, task="classification", target="label", method="bagging")
    assert e.task == "classification"
    assert type(e.estimator).__name__ == "BaggingClassifier"
    assert e.estimator.predict(df[["x1", "x2"]]).shape == (len(df),)


def test_ensemble_model_boosting_classification():
    df = _classification_df()
    # AdaBoost with a decision-tree base is the classic (robust) boosting configuration;
    # LogisticRegression is a weak base that can fail to converge on this small synthetic set.
    base = fit_estimator(df, estimator="DecisionTreeClassifier", target="label")
    e = ensemble_model(base, df, task="classification", target="label", method="boosting")
    assert type(e.estimator).__name__ == "AdaBoostClassifier"


def test_ensemble_model_regression():
    df = _regression_df()
    base = fit_estimator(df, estimator="Ridge", target="y")
    e = ensemble_model(base, df, task="regression", target="y", method="bagging")
    assert type(e.estimator).__name__ == "BaggingRegressor"
    assert e.task == "regression"


def test_ensemble_model_rejects_bad_method():
    df = _classification_df()
    base = _fitted_classifier(df)
    with pytest.raises(ValueError):
        ensemble_model(base, df, task="classification", target="label", method="nope")


def test_ensemble_model_rejects_bad_task():
    df = _classification_df()
    base = _fitted_classifier(df)
    with pytest.raises(ValueError):
        ensemble_model(base, df, task="clustering", target="label")


def test_blend_models_classification_soft():
    df = _classification_df()
    m1 = _fitted_classifier(df)
    m2 = _second_classifier(df)
    b = blend_models([m1, m2], df, task="classification", target="label", voting="soft")
    assert type(b.estimator).__name__ == "VotingClassifier"
    assert b.estimator.predict(df[["x1", "x2"]]).shape == (len(df),)


def test_blend_models_regression():
    df = _regression_df()
    r1 = fit_estimator(df, estimator="Ridge", target="y")
    r2 = fit_estimator(df, estimator="RandomForestRegressor", target="y")
    b = blend_models([r1, r2], df, task="regression", target="y")
    assert type(b.estimator).__name__ == "VotingRegressor"


def test_blend_models_requires_two_models():
    df = _classification_df()
    m1 = _fitted_classifier(df)
    with pytest.raises(ValueError):
        blend_models([m1], df, task="classification", target="label")


def test_blend_models_rejects_bad_voting():
    df = _classification_df()
    m1 = _fitted_classifier(df)
    m2 = _second_classifier(df)
    with pytest.raises(ValueError):
        blend_models([m1, m2], df, task="classification", target="label", voting="bogus")


def test_stack_models_classification():
    df = _classification_df()
    m1 = _fitted_classifier(df)
    m2 = _second_classifier(df)
    s = stack_models([m1, m2], df, task="classification", target="label")
    assert type(s.estimator).__name__ == "StackingClassifier"
    assert s.estimator.predict(df[["x1", "x2"]]).shape == (len(df),)


def test_stack_models_regression_custom_meta():
    df = _regression_df()
    r1 = fit_estimator(df, estimator="Ridge", target="y")
    r2 = fit_estimator(df, estimator="RandomForestRegressor", target="y")
    s = stack_models([r1, r2], df, task="regression", target="y", final_estimator="Ridge")
    assert type(s.estimator).__name__ == "StackingRegressor"

    s_default = stack_models([r1, r2], df, task="regression", target="y")
    assert type(s_default.estimator).__name__ == "StackingRegressor"
    assert s_default.estimator.predict(df[["x1", "x2"]]).shape == (len(df),)

    s_clf = stack_models(
        [_fitted_classifier(_classification_df()), _second_classifier(_classification_df())],
        _classification_df(),
        task="classification",
        target="label",
    )
    assert type(s_clf.estimator).__name__ == "StackingClassifier"


def test_stack_models_rejects_task_mismatched_meta():
    df = _regression_df()
    r1 = fit_estimator(df, estimator="Ridge", target="y")
    r2 = fit_estimator(df, estimator="RandomForestRegressor", target="y")
    with pytest.raises(ValueError, match="final_estimator"):
        stack_models(
            [r1, r2],
            df,
            task="regression",
            target="y",
            final_estimator="LogisticRegression",
        )


def test_stack_models_requires_two_models():
    df = _classification_df()
    m1 = _fitted_classifier(df)
    with pytest.raises(ValueError):
        stack_models([m1], df, task="classification", target="label")


# ---------------------------------------------------------------------------
# Node-level execute + codegen equivalence (ADR 0002)
# ---------------------------------------------------------------------------


def _assert_node_predict_execute_and_codegen_equivalent(defn, node, inputs, feature_cols):
    execute_model = defn.execute(node, inputs)["model"]
    exec_preds = execute_model.estimator.predict(inputs["frame"][feature_cols])
    scope = _run_codegen(defn, node, dict(inputs))
    codegen_model = scope["model"]
    codegen_preds = codegen_model.estimator.predict(inputs["frame"][feature_cols])
    assert (exec_preds == codegen_preds).all()


def test_ensemble_model_node_execute_and_codegen_equivalent():
    df = _classification_df()
    base = _fitted_classifier(df)
    defn = EnsembleModel()
    node = defn.instantiate(task="classification", target="label", method="bagging")
    _assert_node_predict_execute_and_codegen_equivalent(
        defn, node, {"model": base, "frame": df.copy()}, ["x1", "x2"]
    )


def test_blend_models_node_execute_and_codegen_equivalent():
    df = _classification_df()
    m1 = _fitted_classifier(df)
    m2 = _second_classifier(df)
    defn = BlendModels()
    node = defn.instantiate(task="classification", target="label")
    _assert_node_predict_execute_and_codegen_equivalent(
        defn, node, {"models": [m1, m2], "frame": df.copy()}, ["x1", "x2"]
    )


def test_stack_models_node_execute_and_codegen_equivalent():
    df = _classification_df()
    m1 = _fitted_classifier(df)
    m2 = _second_classifier(df)
    defn = StackModels()
    node = defn.instantiate(task="classification", target="label")
    _assert_node_predict_execute_and_codegen_equivalent(
        defn, node, {"models": [m1, m2], "frame": df.copy()}, ["x1", "x2"]
    )


# ---------------------------------------------------------------------------
# Full-graph golden: the emitted blend module must parse and be ruff-clean
# ---------------------------------------------------------------------------


def _build_blend_graph() -> Graph:
    load = LoadSample().instantiate(name="iris", label="Load Sample")
    fit1 = FitEstimator().instantiate(
        estimator="LogisticRegression", target="target", features=["x1", "x2"], label="Fit 1"
    )
    fit2 = FitEstimator().instantiate(
        estimator="RandomForestClassifier",
        target="target",
        features=["x1", "x2"],
        label="Fit 2",
    )
    blend = BlendModels().instantiate(task="classification", target="target", label="Blend")

    load_to_fit1_frame = Edge(
        source=PortRef(node_id=load.id, port_id=_out_port(load, "frame").id),
        target=PortRef(node_id=fit1.id, port_id=_in_port(fit1, "frame").id),
    )
    load_to_fit2_frame = Edge(
        source=PortRef(node_id=load.id, port_id=_out_port(load, "frame").id),
        target=PortRef(node_id=fit2.id, port_id=_in_port(fit2, "frame").id),
    )
    fit1_to_blend = Edge(
        source=PortRef(node_id=fit1.id, port_id=_out_port(fit1, "model").id),
        target=PortRef(node_id=blend.id, port_id=_in_port(blend, "models").id),
    )
    fit2_to_blend = Edge(
        source=PortRef(node_id=fit2.id, port_id=_out_port(fit2, "model").id),
        target=PortRef(node_id=blend.id, port_id=_in_port(blend, "models").id),
    )
    load_to_blend_frame = Edge(
        source=PortRef(node_id=load.id, port_id=_out_port(load, "frame").id),
        target=PortRef(node_id=blend.id, port_id=_in_port(blend, "frame").id),
    )

    return Graph(
        schema_version=1,
        paradigm="functional",
        nodes={load.id: load, fit1.id: fit1, fit2.id: fit2, blend.id: blend},
        edges={
            load_to_fit1_frame.id: load_to_fit1_frame,
            load_to_fit2_frame.id: load_to_fit2_frame,
            load_to_blend_frame.id: load_to_blend_frame,
            fit1_to_blend.id: fit1_to_blend,
            fit2_to_blend.id: fit2_to_blend,
        },
    )


def test_blend_graph_codegen_parses_and_is_ruff_clean():
    code = compile_to_code(_build_blend_graph())
    ast.parse(code)  # raises SyntaxError on failure
    assert "ef.ml.blend_models" in code
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "-"],
        input=code,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# Tune model (Feature 3)
# ---------------------------------------------------------------------------


def test_tune_model_backend_returns_best_model_and_cv_results():
    df = _classification_df()
    model, cv_results = tune_model(
        df,
        estimator="LogisticRegression",
        param_distributions={"C": [0.1, 1.0, 10.0]},
        target="label",
        features=["x1", "x2"],
        n_iter=3,
        cv=3,
        random_state=0,
    )
    assert model.task == "classification"
    assert type(model.estimator).__name__ == "LogisticRegression"
    assert len(cv_results) <= 3
    assert {"mean_test_score", "rank_test_score", "std_test_score"} <= set(cv_results.columns)


def test_tune_model_rejects_bad_distribution_key():
    df = _classification_df()
    with pytest.raises(ValueError):
        tune_model(
            df,
            estimator="LogisticRegression",
            param_distributions={"not_a_param": [1]},
            target="label",
            n_iter=2,
            cv=2,
        )


def test_tune_model_rejects_empty_distributions():
    df = _classification_df()
    with pytest.raises(ValueError):
        tune_model(df, estimator="LogisticRegression", param_distributions={}, target="label", cv=2)


def test_tune_model_node_execute_and_codegen_equivalent():
    df = _classification_df()
    defn = TuneModel()
    node = defn.instantiate(
        estimator="LogisticRegression",
        param_distributions={"C": [0.1, 1.0]},
        target="label",
        features=["x1", "x2"],
        n_iter=2,
        cv=3,
    )
    execute_model = defn.execute(node, {"frame": df.copy()})["model"]
    exec_preds = execute_model.estimator.predict(df[["x1", "x2"]])
    scope = _run_codegen(defn, node, {"frame": df.copy()})
    codegen_model = scope["model"]
    codegen_preds = codegen_model.estimator.predict(df[["x1", "x2"]])
    assert (exec_preds == codegen_preds).all()
