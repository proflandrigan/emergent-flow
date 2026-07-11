"""
Golden + equivalence tests for the ADR 0020 ``explain.shap_values`` node.

Guarded with ``pytest.importorskip`` (torch-style optional-dependency discipline; shap is the
optional ``emergentflow[explain]`` extra, not in the ``dev`` dependency group).
"""

from __future__ import annotations

import ast
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("shap")

from emergentflow.codegen.compiler import compile_to_code  # noqa: E402
from emergentflow.explain.errors import UnsupportedModelError  # noqa: E402
from emergentflow.ir.common import Direction  # noqa: E402
from emergentflow.ir.edge import Edge, PortRef  # noqa: E402
from emergentflow.ir.graph import Graph  # noqa: E402
from emergentflow.ml import fit_and_label, fit_estimator  # noqa: E402
from emergentflow.nodes.examples import ExplainShapValues, FitEstimator, LoadSample  # noqa: E402


def _out_port(node, name):
    return next(p for p in node.ports if p.direction == Direction.OUT and p.name == name)


def _in_port(node, name):
    return next(p for p in node.ports if p.direction == Direction.IN and p.name == name)


def _run_codegen(definition, node, scope):
    frag = definition.preview(node)
    exec(frag.render(), scope)  # noqa: S102 -- test-only, on our own emitted code
    return scope


def _assert_parseable_and_ruff_clean(code: str) -> None:
    ast.parse(code)
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "-"],
        input=code,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# Fixed, seeded fixtures.
# ---------------------------------------------------------------------------


def _tree_regression_fixture():
    """RandomForestRegressor -- exercises the TreeExplainer (no-sampling) path."""
    rng = np.random.default_rng(0)
    n = 40
    x1 = rng.normal(size=n)
    x2 = rng.normal(size=n)
    y = 2.0 * x1 - x2 + rng.normal(scale=0.1, size=n)
    df = pd.DataFrame({"x1": x1, "x2": x2, "y": y})
    model = fit_estimator(
        df,
        estimator="RandomForestRegressor",
        target="y",
        features=["x1", "x2"],
        params={"n_estimators": 10, "random_state": 0},
    )
    return model, df


def _linear_regression_fixture():
    """Ridge -- exercises the generic (PermutationExplainer) regression path."""
    rng = np.random.default_rng(0)
    n = 40
    x1 = rng.normal(size=n)
    x2 = rng.normal(size=n)
    y = 2.0 * x1 - x2 + rng.normal(scale=0.1, size=n)
    df = pd.DataFrame({"x1": x1, "x2": x2, "y": y})
    model = fit_estimator(df, estimator="Ridge", target="y", features=["x1", "x2"])
    return model, df


def _binary_classification_fixture():
    """LogisticRegression, binary -- exercises the single-output predict_proba[:, 1] path."""
    rng = np.random.default_rng(0)
    n = 40
    x1 = rng.normal(size=n)
    p = 1.0 / (1.0 + np.exp(-(2.0 * x1)))
    label = np.where(rng.random(n) < p, "yes", "no")
    df = pd.DataFrame({"x1": x1, "label": label})
    model = fit_estimator(df, estimator="LogisticRegression", target="label", features=["x1"])
    return model, df


def _multiclass_classification_fixture():
    """RandomForestClassifier, 3 classes -- exercises the multi-output predict_proba path AND
    proves a tree-classifier estimator_type still goes through the generic path, not
    TreeExplainer (ADR 0020, Decision clause 3)."""
    rng = np.random.default_rng(0)
    n = 60
    x1 = rng.normal(size=n)
    x2 = rng.normal(size=n)
    label = np.where(x1 > 0.5, "a", np.where(x1 < -0.5, "b", "c"))
    df = pd.DataFrame({"x1": x1, "x2": x2, "label": label})
    model = fit_estimator(
        df,
        estimator="RandomForestClassifier",
        target="label",
        features=["x1", "x2"],
        params={"n_estimators": 10, "random_state": 0},
    )
    return model, df


# ---------------------------------------------------------------------------
# 1. Golden-code quality.
# ---------------------------------------------------------------------------


def test_shap_values_codegen_is_parseable_and_ruff_clean() -> None:
    load = LoadSample().instantiate(name="diabetes", label="Load Sample")
    fit = FitEstimator().instantiate(
        estimator="RandomForestRegressor", target="target", label="Fit"
    )
    explain = ExplainShapValues().instantiate(seed=0, background_samples=50, label="SHAP Values")
    load_to_fit = Edge(
        source=PortRef(node_id=load.id, port_id=_out_port(load, "frame").id),
        target=PortRef(node_id=fit.id, port_id=_in_port(fit, "frame").id),
    )
    fit_to_explain_model = Edge(
        source=PortRef(node_id=fit.id, port_id=_out_port(fit, "model").id),
        target=PortRef(node_id=explain.id, port_id=_in_port(explain, "model").id),
    )
    load_to_explain_frame = Edge(
        source=PortRef(node_id=load.id, port_id=_out_port(load, "frame").id),
        target=PortRef(node_id=explain.id, port_id=_in_port(explain, "frame").id),
    )
    graph = Graph(
        nodes={load.id: load, fit.id: fit, explain.id: explain},
        edges={
            load_to_fit.id: load_to_fit,
            fit_to_explain_model.id: fit_to_explain_model,
            load_to_explain_frame.id: load_to_explain_frame,
        },
    )
    _assert_parseable_and_ruff_clean(compile_to_code(graph))


# ---------------------------------------------------------------------------
# 2. ADR-0002 equivalence, one per dispatch path.
# ---------------------------------------------------------------------------


@pytest.mark.equivalence
def test_shap_values_tree_regression_equivalence() -> None:
    model, df = _tree_regression_fixture()
    defn = ExplainShapValues()
    node = defn.instantiate(seed=0, background_samples=20, label="SHAP Values")
    executed = defn.execute(node, inputs={"model": model, "frame": df})["shap_values"]
    scope = _run_codegen(defn, node, {"model": model, "frame": df})
    pd.testing.assert_frame_equal(executed, scope["shap_values"])


@pytest.mark.equivalence
def test_shap_values_linear_regression_equivalence() -> None:
    model, df = _linear_regression_fixture()
    defn = ExplainShapValues()
    node = defn.instantiate(seed=0, background_samples=20, label="SHAP Values")
    executed = defn.execute(node, inputs={"model": model, "frame": df})["shap_values"]
    scope = _run_codegen(defn, node, {"model": model, "frame": df})
    pd.testing.assert_frame_equal(executed, scope["shap_values"])


@pytest.mark.equivalence
def test_shap_values_binary_classification_equivalence() -> None:
    model, df = _binary_classification_fixture()
    defn = ExplainShapValues()
    node = defn.instantiate(seed=0, background_samples=20, label="SHAP Values")
    executed = defn.execute(node, inputs={"model": model, "frame": df})["shap_values"]
    scope = _run_codegen(defn, node, {"model": model, "frame": df})
    pd.testing.assert_frame_equal(executed, scope["shap_values"])
    assert "class" not in executed.columns


@pytest.mark.equivalence
def test_shap_values_multiclass_classification_equivalence() -> None:
    model, df = _multiclass_classification_fixture()
    defn = ExplainShapValues()
    node = defn.instantiate(seed=0, background_samples=20, label="SHAP Values")
    executed = defn.execute(node, inputs={"model": model, "frame": df})["shap_values"]
    scope = _run_codegen(defn, node, {"model": model, "frame": df})
    pd.testing.assert_frame_equal(executed, scope["shap_values"])
    assert set(executed["class"]) == {"a", "b", "c"}


# ---------------------------------------------------------------------------
# 3. Unsupported-model error path.
# ---------------------------------------------------------------------------


def test_shap_values_rejects_cluster_detect_model() -> None:
    rng = np.random.default_rng(0)
    n = 30
    df = pd.DataFrame({"x1": rng.normal(size=n), "x2": rng.normal(size=n)})
    model, _labeled = fit_and_label(df, estimator="KMeans", features=["x1", "x2"])
    defn = ExplainShapValues()
    node = defn.instantiate(seed=0, label="SHAP Values")
    with pytest.raises(UnsupportedModelError):
        defn.execute(node, inputs={"model": model, "frame": df})
