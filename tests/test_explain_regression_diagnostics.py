"""
Golden + equivalence tests for the ADR 0020 ``explain.plot_predicted_vs_actual`` and
``explain.plot_residuals`` nodes.
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
    ExplainPlotPredictedVsActual,
    ExplainPlotResiduals,
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
    n = 30
    x1 = rng.normal(size=n)
    p = 1.0 / (1.0 + np.exp(-(2.0 * x1)))
    label = np.where(rng.random(n) < p, "yes", "no")
    df = pd.DataFrame({"x1": x1, "label": label})
    model = fit_estimator(df, estimator="LogisticRegression", target="label", features=["x1"])
    return model, df


def _build_regression_plot_graph(plot_defn_cls) -> Graph:
    load = LoadSample().instantiate(name="diabetes", label="Load Sample")
    fit = FitEstimator().instantiate(estimator="Ridge", target="target", label="Fit")
    plot = plot_defn_cls().instantiate(label="Plot")
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


@pytest.mark.parametrize("plot_cls", [ExplainPlotPredictedVsActual, ExplainPlotResiduals])
def test_regression_diagnostic_codegen_is_parseable_and_ruff_clean(plot_cls) -> None:
    code = compile_to_code(_build_regression_plot_graph(plot_cls))
    _assert_parseable_and_ruff_clean(code)


@pytest.mark.equivalence
def test_plot_predicted_vs_actual_equivalence() -> None:
    model, df = _regression_fixture()
    defn = ExplainPlotPredictedVsActual()
    node = defn.instantiate(label="Plot Predicted vs Actual")
    executed = defn.execute(node, inputs={"model": model, "frame": df})["plot"]
    scope = _run_codegen(defn, node, {"model": model, "frame": df})
    assert executed.spec == scope["plot"].spec


@pytest.mark.equivalence
def test_plot_residuals_equivalence() -> None:
    model, df = _regression_fixture()
    defn = ExplainPlotResiduals()
    node = defn.instantiate(label="Plot Residuals")
    executed = defn.execute(node, inputs={"model": model, "frame": df})["plot"]
    scope = _run_codegen(defn, node, {"model": model, "frame": df})
    assert executed.spec == scope["plot"].spec


@pytest.mark.parametrize("plot_cls", [ExplainPlotPredictedVsActual, ExplainPlotResiduals])
def test_regression_diagnostic_rejects_classification_model(plot_cls) -> None:
    model, df = _binary_classification_fixture()
    defn = plot_cls()
    node = defn.instantiate(label="Plot")
    with pytest.raises(UnsupportedModelError):
        defn.execute(node, inputs={"model": model, "frame": df})


def test_plot_residuals_matches_actual_minus_prediction() -> None:
    from emergentflow.explain import plot_residuals

    model, df = _regression_fixture()
    plot = plot_residuals(model, df)
    trace = plot.spec["data"][0]
    y_pred = model.estimator.predict(df[model.feature_names])
    expected_residual = (df["y"].to_numpy() - y_pred).tolist()
    assert trace["y"] == pytest.approx(expected_residual)
    assert trace["x"] == pytest.approx(y_pred.tolist())
