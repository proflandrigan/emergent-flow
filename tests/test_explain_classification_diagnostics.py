"""
Golden + equivalence tests for the ADR 0020 ``explain.plot_calibration`` and
``explain.plot_roc_pr`` nodes.
"""

from __future__ import annotations

import ast
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from emergentflow.codegen.compiler import compile_to_code
from emergentflow.explain.errors import UnsupportedModelError
from emergentflow.ir.common import Direction
from emergentflow.ir.edge import Edge, PortRef
from emergentflow.ir.graph import Graph
from emergentflow.ml import fit_estimator
from emergentflow.nodes.examples import (
    ExplainPlotCalibration,
    ExplainPlotRocPr,
    FitEstimator,
    LoadSample,
)


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


def _binary_classification_fixture():
    rng = np.random.default_rng(0)
    n = 60
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


def _regression_fixture():
    rng = np.random.default_rng(0)
    n = 30
    x1 = rng.normal(size=n)
    y = 2.0 * x1 + 1.0 + rng.normal(scale=0.3, size=n)
    df = pd.DataFrame({"x1": x1, "y": y})
    model = fit_estimator(df, estimator="Ridge", target="y", features=["x1"])
    return model, df


def _build_classification_plot_graph(plot_defn_cls, **plot_kwargs) -> Graph:
    load = LoadSample().instantiate(name="iris", label="Load Sample")
    fit = FitEstimator().instantiate(estimator="LogisticRegression", target="target", label="Fit")
    plot = plot_defn_cls().instantiate(label="Plot", **plot_kwargs)
    load_to_fit = Edge(
        source=PortRef(node_id=load.id, port_id=_out_port(load, "frame").id),
        target=PortRef(node_id=fit.id, port_id=_in_port(fit, "frame").id),
    )
    fit_to_plot_model = Edge(
        source=PortRef(node_id=fit.id, port_id=_out_port(fit, "model").id),
        target=PortRef(node_id=plot.id, port_id=_in_port(plot, "model").id),
    )
    load_to_plot_frame = Edge(
        source=PortRef(node_id=load.id, port_id=_out_port(load, "frame").id),
        target=PortRef(node_id=plot.id, port_id=_in_port(plot, "frame").id),
    )
    return Graph(
        nodes={load.id: load, fit.id: fit, plot.id: plot},
        edges={
            load_to_fit.id: load_to_fit,
            fit_to_plot_model.id: fit_to_plot_model,
            load_to_plot_frame.id: load_to_plot_frame,
        },
    )


def test_plot_calibration_codegen_is_parseable_and_ruff_clean() -> None:
    code = compile_to_code(_build_classification_plot_graph(ExplainPlotCalibration, n_bins=5))
    _assert_parseable_and_ruff_clean(code)


@pytest.mark.parametrize("curve", ["roc", "pr"])
def test_plot_roc_pr_codegen_is_parseable_and_ruff_clean(curve: str) -> None:
    code = compile_to_code(_build_classification_plot_graph(ExplainPlotRocPr, curve=curve))
    _assert_parseable_and_ruff_clean(code)


@pytest.mark.equivalence
def test_plot_calibration_equivalence() -> None:
    model, df = _binary_classification_fixture()
    defn = ExplainPlotCalibration()
    node = defn.instantiate(n_bins=5, label="Plot Calibration")
    executed = defn.execute(node, inputs={"model": model, "frame": df})["plot"]
    scope = _run_codegen(defn, node, {"model": model, "frame": df})
    assert executed.spec == scope["plot"].spec


@pytest.mark.equivalence
@pytest.mark.parametrize("curve", ["roc", "pr"])
def test_plot_roc_pr_equivalence(curve: str) -> None:
    model, df = _binary_classification_fixture()
    defn = ExplainPlotRocPr()
    node = defn.instantiate(curve=curve, label="Plot ROC / PR")
    executed = defn.execute(node, inputs={"model": model, "frame": df})["plot"]
    scope = _run_codegen(defn, node, {"model": model, "frame": df})
    assert executed.spec == scope["plot"].spec


@pytest.mark.parametrize("plot_cls,kwargs", [(ExplainPlotCalibration, {}), (ExplainPlotRocPr, {})])
def test_classification_diagnostic_rejects_regression_model(plot_cls, kwargs) -> None:
    model, df = _regression_fixture()
    defn = plot_cls()
    node = defn.instantiate(label="Plot", **kwargs)
    with pytest.raises(UnsupportedModelError):
        defn.execute(node, inputs={"model": model, "frame": df})


@pytest.mark.parametrize("plot_cls,kwargs", [(ExplainPlotCalibration, {}), (ExplainPlotRocPr, {})])
def test_classification_diagnostic_rejects_multiclass_model(plot_cls, kwargs) -> None:
    model, df = _multiclass_classification_fixture()
    defn = plot_cls()
    node = defn.instantiate(label="Plot", **kwargs)
    with pytest.raises(UnsupportedModelError):
        defn.execute(node, inputs={"model": model, "frame": df})


def test_plot_roc_pr_rejects_unknown_curve() -> None:
    from emergentflow.explain import plot_roc_pr

    model, df = _binary_classification_fixture()
    with pytest.raises(ValueError, match="unknown curve"):
        plot_roc_pr(model, df, curve="not-a-real-curve")
