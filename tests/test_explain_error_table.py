"""
Golden + equivalence tests for the ADR 0020 ``explain.error_table`` node.
"""

from __future__ import annotations

import ast
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from emergentflow.codegen.compiler import compile_to_code
from emergentflow.explain import error_table
from emergentflow.explain.errors import UnsupportedModelError
from emergentflow.ir.common import Direction
from emergentflow.ir.edge import Edge, PortRef
from emergentflow.ir.graph import Graph
from emergentflow.ml import fit_and_label, fit_estimator
from emergentflow.nodes.examples import ExplainErrorTable, FitEstimator, LoadSample


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


def _regression_fixture():
    rng = np.random.default_rng(0)
    n = 30
    x1 = rng.normal(size=n)
    y = 2.0 * x1 + 1.0 + rng.normal(scale=0.3, size=n)
    df = pd.DataFrame({"x1": x1, "y": y})
    model = fit_estimator(df, estimator="Ridge", target="y", features=["x1"])
    return model, df


def _binary_classification_fixture():
    rng = np.random.default_rng(0)
    n = 40
    x1 = rng.normal(size=n)
    p = 1.0 / (1.0 + np.exp(-(2.0 * x1)))
    label = np.where(rng.random(n) < p, "yes", "no")
    df = pd.DataFrame({"x1": x1, "label": label})
    model = fit_estimator(df, estimator="LogisticRegression", target="label", features=["x1"])
    return model, df


def _multiclass_classification_fixture():
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


def test_error_table_codegen_is_parseable_and_ruff_clean() -> None:
    load = LoadSample().instantiate(name="diabetes", label="Load Sample")
    fit = FitEstimator().instantiate(estimator="Ridge", target="target", label="Fit")
    err = ExplainErrorTable().instantiate(top_n=10, label="Error Table")
    load_to_fit = Edge(
        source=PortRef(node_id=load.id, port_id=_out_port(load, "frame").id),
        target=PortRef(node_id=fit.id, port_id=_in_port(fit, "frame").id),
    )
    fit_to_err_model = Edge(
        source=PortRef(node_id=fit.id, port_id=_out_port(fit, "model").id),
        target=PortRef(node_id=err.id, port_id=_in_port(err, "model").id),
    )
    load_to_err_frame = Edge(
        source=PortRef(node_id=load.id, port_id=_out_port(load, "frame").id),
        target=PortRef(node_id=err.id, port_id=_in_port(err, "frame").id),
    )
    graph = Graph(
        nodes={load.id: load, fit.id: fit, err.id: err},
        edges={
            load_to_fit.id: load_to_fit,
            fit_to_err_model.id: fit_to_err_model,
            load_to_err_frame.id: load_to_err_frame,
        },
    )
    _assert_parseable_and_ruff_clean(compile_to_code(graph))


@pytest.mark.equivalence
def test_error_table_regression_equivalence() -> None:
    model, df = _regression_fixture()
    defn = ExplainErrorTable()
    node = defn.instantiate(top_n=5, label="Error Table")
    executed = defn.execute(node, inputs={"model": model, "frame": df})["error_table"]
    scope = _run_codegen(defn, node, {"model": model, "frame": df})
    pd.testing.assert_frame_equal(executed, scope["error_table"])
    assert len(executed) == 5
    assert list(executed["abs_error"]) == sorted(executed["abs_error"], reverse=True)


@pytest.mark.equivalence
def test_error_table_binary_classification_equivalence() -> None:
    model, df = _binary_classification_fixture()
    defn = ExplainErrorTable()
    node = defn.instantiate(top_n=5, label="Error Table")
    executed = defn.execute(node, inputs={"model": model, "frame": df})["error_table"]
    scope = _run_codegen(defn, node, {"model": model, "frame": df})
    pd.testing.assert_frame_equal(executed, scope["error_table"])
    # misclassified rows (correct=False) must sort before correct=True rows.
    assert list(executed["correct"]) == sorted(executed["correct"])


@pytest.mark.equivalence
def test_error_table_multiclass_classification_equivalence() -> None:
    model, df = _multiclass_classification_fixture()
    defn = ExplainErrorTable()
    node = defn.instantiate(top_n=5, label="Error Table")
    executed = defn.execute(node, inputs={"model": model, "frame": df})["error_table"]
    scope = _run_codegen(defn, node, {"model": model, "frame": df})
    pd.testing.assert_frame_equal(executed, scope["error_table"])


def test_error_table_top_n_larger_than_frame_returns_all_rows() -> None:
    model, df = _regression_fixture()
    result = error_table(model, df, top_n=10_000)
    assert len(result) == len(df)


def test_error_table_rejects_cluster_detect_model() -> None:
    rng = np.random.default_rng(0)
    n = 30
    df = pd.DataFrame({"x1": rng.normal(size=n), "x2": rng.normal(size=n)})
    model, _labeled = fit_and_label(df, estimator="KMeans", features=["x1", "x2"])
    with pytest.raises(UnsupportedModelError):
        error_table(model, df, top_n=5)
