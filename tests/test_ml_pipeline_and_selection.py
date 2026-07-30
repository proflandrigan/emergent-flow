"""
Golden + equivalence tests for the Epic 8 Story 8 pipeline/model-selection nodes.

Mirrors ``tests/test_ml_supervised_catalog.py``'s pattern, scoped to the three Story 8 node
types (``ml.pipeline``, ``ml.grid_search``, ``ml.cross_validate``) rather than a whole
estimator-archetype matrix, since each of these is a single node file, not a generated
catalog family.
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
from emergentflow.nodes.examples import (
    ApplyEstimator,
    CrossValidate,
    GridSearch,
    LoadSample,
    Pipeline,
)


def _out_port(node, name):
    return next(p for p in node.ports if p.direction == Direction.OUT and p.name == name)


def _in_port(node, name):
    return next(p for p in node.ports if p.direction == Direction.IN and p.name == name)


def _run_codegen(definition, node, scope):
    """exec a node's preview fragment in *scope* and return the updated scope."""
    frag = definition.preview(node)
    exec(frag.render(), scope)  # noqa: S102 -- test-only, on our own emitted code
    return scope


def _classification_df() -> pd.DataFrame:
    x1 = [float(i) for i in range(20)] + [float(i) for i in range(20)]
    x2 = [float(i % 5) for i in range(40)]
    label = ["low" if i % 2 == 0 else "high" for i in range(40)]
    return pd.DataFrame({"x1": x1, "x2": x2, "label": label})


# ---------------------------------------------------------------------------
# 1. Golden-code quality
# ---------------------------------------------------------------------------


def _build_pipeline_apply_graph() -> Graph:
    load = LoadSample().instantiate(name="iris", label="Load Sample")
    pipe = Pipeline().instantiate(
        steps=[
            {"estimator": "StandardScaler", "params": {}},
            {"estimator": "LogisticRegression", "params": {}},
        ],
        target="target",
        label="Pipeline",
    )
    apply_ = ApplyEstimator().instantiate(op="predict", label="Apply")

    load_to_pipe = Edge(
        source=PortRef(node_id=load.id, port_id=_out_port(load, "frame").id),
        target=PortRef(node_id=pipe.id, port_id=_in_port(pipe, "frame").id),
    )
    pipe_to_apply_model = Edge(
        source=PortRef(node_id=pipe.id, port_id=_out_port(pipe, "model").id),
        target=PortRef(node_id=apply_.id, port_id=_in_port(apply_, "model").id),
    )
    load_to_apply_frame = Edge(
        source=PortRef(node_id=load.id, port_id=_out_port(load, "frame").id),
        target=PortRef(node_id=apply_.id, port_id=_in_port(apply_, "frame").id),
    )
    return Graph(
        nodes={load.id: load, pipe.id: pipe, apply_.id: apply_},
        edges={
            load_to_pipe.id: load_to_pipe,
            pipe_to_apply_model.id: pipe_to_apply_model,
            load_to_apply_frame.id: load_to_apply_frame,
        },
    )


def _build_grid_search_graph() -> Graph:
    load = LoadSample().instantiate(name="iris", label="Load Sample")
    gs = GridSearch().instantiate(
        estimator="LogisticRegression",
        param_grid={"C": [0.1, 1.0]},
        target="target",
        cv=3,
        label="Grid Search",
    )
    load_to_gs = Edge(
        source=PortRef(node_id=load.id, port_id=_out_port(load, "frame").id),
        target=PortRef(node_id=gs.id, port_id=_in_port(gs, "frame").id),
    )
    return Graph(nodes={load.id: load, gs.id: gs}, edges={load_to_gs.id: load_to_gs})


def _build_cross_validate_graph() -> Graph:
    load = LoadSample().instantiate(name="iris", label="Load Sample")
    cv_node = CrossValidate().instantiate(
        estimator="LogisticRegression", target="target", cv=3, label="Cross Validate"
    )
    load_to_cv = Edge(
        source=PortRef(node_id=load.id, port_id=_out_port(load, "frame").id),
        target=PortRef(node_id=cv_node.id, port_id=_in_port(cv_node, "frame").id),
    )
    return Graph(nodes={load.id: load, cv_node.id: cv_node}, edges={load_to_cv.id: load_to_cv})


_GOLDEN_GRAPH_BUILDERS = {
    "pipeline": _build_pipeline_apply_graph,
    "grid_search": _build_grid_search_graph,
    "cross_validate": _build_cross_validate_graph,
}


@pytest.mark.parametrize("name", sorted(_GOLDEN_GRAPH_BUILDERS))
def test_codegen_is_parseable(name: str) -> None:
    code = compile_to_code(_GOLDEN_GRAPH_BUILDERS[name]())
    ast.parse(code)  # raises SyntaxError on failure


@pytest.mark.parametrize("name", sorted(_GOLDEN_GRAPH_BUILDERS))
def test_codegen_is_ruff_clean(name: str) -> None:
    code = compile_to_code(_GOLDEN_GRAPH_BUILDERS[name]())
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "-"],
        input=code,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# 2. ADR-0002 equivalence
# ---------------------------------------------------------------------------


@pytest.mark.equivalence
def test_pipeline_equivalence_supervised_final_step() -> None:
    """execute == running the emitted code, for a pipeline ending in a fit-archetype step."""
    df = _classification_df()
    steps = [
        {"estimator": "StandardScaler", "params": {}},
        {"estimator": "LogisticRegression", "params": {}},
    ]

    defn = Pipeline()
    node = defn.instantiate(steps=steps, target="label")
    executed_model = defn.execute(node, inputs={"frame": df.copy()})["model"]
    scope = _run_codegen(defn, node, {"frame": df.copy()})
    codegen_model = scope["model"]

    assert executed_model.estimator_type == codegen_model.estimator_type == "Pipeline"
    assert executed_model.task == codegen_model.task == "classification"
    assert executed_model.target == codegen_model.target == "label"
    assert executed_model.feature_names == codegen_model.feature_names
    assert (
        executed_model.estimator.predict(df[executed_model.feature_names]).tolist()
        == codegen_model.estimator.predict(df[codegen_model.feature_names]).tolist()
    )


@pytest.mark.equivalence
def test_pipeline_equivalence_cluster_detect_final_step() -> None:
    """execute == running the emitted code, for a pipeline ending in a cluster_detect step."""
    df = _classification_df()  # features only matter here; label column is simply unused
    steps = [
        {"estimator": "StandardScaler", "params": {}},
        {"estimator": "KMeans", "params": {"n_clusters": 2, "random_state": 0, "n_init": 10}},
    ]

    defn = Pipeline()
    node = defn.instantiate(steps=steps, features=["x1", "x2"])
    executed_model = defn.execute(node, inputs={"frame": df.copy()})["model"]
    scope = _run_codegen(defn, node, {"frame": df.copy()})
    codegen_model = scope["model"]

    assert executed_model.estimator_type == codegen_model.estimator_type == "Pipeline"
    assert executed_model.task == codegen_model.task == "clustering"
    assert executed_model.target is None
    assert codegen_model.target is None
    assert executed_model.feature_names == codegen_model.feature_names
    assert (
        executed_model.estimator.predict(df[executed_model.feature_names]).tolist()
        == codegen_model.estimator.predict(df[codegen_model.feature_names]).tolist()
    )


@pytest.mark.equivalence
def test_pipeline_equivalence_outlier_detect_final_step() -> None:
    """execute == running the emitted code, for a pipeline ending in an outlier_detect step."""
    df = _classification_df()  # label column is unused
    steps = [
        {"estimator": "StandardScaler", "params": {}},
        {"estimator": "IsolationForest", "params": {"random_state": 0}},
    ]

    defn = Pipeline()
    node = defn.instantiate(steps=steps, features=["x1", "x2"])
    executed_model = defn.execute(node, inputs={"frame": df.copy()})["model"]
    scope = _run_codegen(defn, node, {"frame": df.copy()})
    codegen_model = scope["model"]

    assert executed_model.estimator_type == codegen_model.estimator_type == "Pipeline"
    assert executed_model.task == codegen_model.task == "outlier_detection"
    assert executed_model.target is None
    assert codegen_model.target is None
    assert executed_model.feature_names == codegen_model.feature_names
    assert (
        executed_model.estimator.predict(df[executed_model.feature_names]).tolist()
        == codegen_model.estimator.predict(df[codegen_model.feature_names]).tolist()
    )


def test_pipeline_allows_repeated_estimator_key_across_steps() -> None:
    """Pipeline step names must be unique even when two steps share an estimator key.

    Regression test: sklearn's ``Pipeline`` requires unique step names; naming steps by their
    bare estimator key (with no positional disambiguation) raised a raw, un-typed
    ``ValueError: Provided step names are not unique`` for any pipeline repeating an estimator
    (e.g. two ``StandardScaler`` steps with different params).
    """
    df = _classification_df()
    steps = [
        {"estimator": "StandardScaler", "params": {"with_mean": True}},
        {"estimator": "StandardScaler", "params": {"with_mean": False}},
        {"estimator": "LogisticRegression", "params": {}},
    ]

    defn = Pipeline()
    node = defn.instantiate(steps=steps, target="label")
    model = defn.execute(node, inputs={"frame": df.copy()})["model"]

    assert model.estimator_type == "Pipeline"
    model.estimator.predict(df[model.feature_names])  # doesn't raise


@pytest.mark.equivalence
def test_grid_search_equivalence() -> None:
    """execute == running the emitted code, for ml.grid_search."""
    df = _classification_df()

    defn = GridSearch()
    node = defn.instantiate(
        estimator="LogisticRegression", param_grid={"C": [0.1, 1.0]}, target="label", cv=3
    )
    executed = defn.execute(node, inputs={"frame": df.copy()})
    executed_model, executed_cv = executed["model"], executed["cv_results"]
    scope = _run_codegen(defn, node, {"frame": df.copy()})
    codegen_model, codegen_cv = scope["model"], scope["cv_results"]

    assert executed_model.estimator_type == codegen_model.estimator_type == "LogisticRegression"
    assert executed_model.feature_names == codegen_model.feature_names
    assert (
        executed_model.estimator.predict(df[executed_model.feature_names]).tolist()
        == codegen_model.estimator.predict(df[codegen_model.feature_names]).tolist()
    )
    assert executed_cv["param_C"].tolist() == codegen_cv["param_C"].tolist()
    assert executed_cv["mean_test_score"].tolist() == codegen_cv["mean_test_score"].tolist()
    assert executed_cv["rank_test_score"].tolist() == codegen_cv["rank_test_score"].tolist()


def test_grid_search_preserves_curated_defaults_outside_param_grid() -> None:
    """grid_search's base estimator must use curated defaults for kwargs not in param_grid.

    Regression test: the base estimator used to be constructed with no kwargs at all
    (``spec.sklearn_class()``), silently dropping curated defaults like
    ``LogisticRegression``'s ``max_iter=1000``/``random_state=0`` for every run whose
    ``param_grid`` didn't happen to sweep that kwarg.
    """
    df = _classification_df()

    defn = GridSearch()
    node = defn.instantiate(
        estimator="LogisticRegression", param_grid={"C": [0.1, 1.0]}, target="label", cv=3
    )
    model = defn.execute(node, inputs={"frame": df.copy()})["model"]

    assert model.estimator.max_iter == 1000
    assert model.estimator.random_state == 0


@pytest.mark.equivalence
def test_cross_validate_equivalence() -> None:
    """execute == running the emitted code, for ml.cross_validate."""
    df = _classification_df()

    defn = CrossValidate()
    node = defn.instantiate(estimator="LogisticRegression", target="label", cv=4)
    executed_result = defn.execute(node, inputs={"frame": df.copy()})["result"]
    scope = _run_codegen(defn, node, {"frame": df.copy()})
    codegen_result = scope["result"]

    assert executed_result["fold"].tolist() == codegen_result["fold"].tolist()
    assert executed_result["test_score"].tolist() == codegen_result["test_score"].tolist()
