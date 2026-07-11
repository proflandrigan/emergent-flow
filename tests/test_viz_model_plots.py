"""
Golden + equivalence tests for the Epic 12 Story 9 model-aware plot nodes: coefficient/forest,
residual, Q-Q, ACF/PACF, correlation heatmap, and confusion matrix.

Mirrors ``tests/test_stats_regression_catalog.py``'s two-part shape (golden code quality +
ADR-0002 equivalence), applied per plot node rather than per statistical model, since each
Story 9 node is a standalone bespoke plot (not part of the curated ``viz.plot`` chart allow-list
covered by ``tests/test_viz_catalog.py``).
"""

from __future__ import annotations

import ast
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from emergentflow.codegen.compiler import compile_to_code
from emergentflow.ir.common import Direction
from emergentflow.ir.edge import Edge, PortRef
from emergentflow.ir.graph import Graph
from emergentflow.ml import fit_estimator
from emergentflow.nodes.examples import (
    Correlation,
    FitEstimator,
    FitLinearRegression,
    LoadSample,
    VizPlotAcf,
    VizPlotCoefficients,
    VizPlotConfusionMatrix,
    VizPlotCorrelationHeatmap,
    VizPlotQQ,
    VizPlotResiduals,
)
from emergentflow.stats import correlation, fit_model


def _out_port(node, name):
    return next(p for p in node.ports if p.direction == Direction.OUT and p.name == name)


def _in_port(node, name):
    return next(p for p in node.ports if p.direction == Direction.IN and p.name == name)


def _run_codegen(definition, node, scope):
    """exec a node's preview fragment in *scope* and return the updated scope."""
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
# Fixed, seeded fixtures shared by both golden and equivalence tests.
# ---------------------------------------------------------------------------


def _fit_ols():
    rng = np.random.default_rng(0)
    n = 60
    x1 = rng.normal(size=n)
    y = 2.0 * x1 + 1.0 + rng.normal(scale=0.1, size=n)
    df = pd.DataFrame({"x1": x1, "y": y})
    return fit_model(df, model="OLS", spec={"target": "y", "fixed_effects": ["x1"]})


def _fixed_corr_matrix() -> pd.DataFrame:
    rng = np.random.default_rng(0)
    n = 30
    a = rng.normal(size=n)
    b = 2.0 * a + rng.normal(scale=0.1, size=n)
    c = rng.normal(size=n)
    df = pd.DataFrame({"a": a, "b": b, "c": c})
    return correlation(df)


def _fit_classifier():
    rng = np.random.default_rng(0)
    n = 40
    x1 = rng.normal(size=n)
    p = 1.0 / (1.0 + np.exp(-(2.0 * x1)))
    label = np.where(rng.random(n) < p, "yes", "no")
    df = pd.DataFrame({"x1": x1, "label": label})
    model = fit_estimator(df, estimator="LogisticRegression", target="label", features=["x1"])
    return model, df


# ---------------------------------------------------------------------------
# 1. Golden-code quality: LoadSample -> FitModel -> <plot node>, one representative graph
#    per StatsModel-consuming plot node, plus one each for the two non-StatsModel plots.
# ---------------------------------------------------------------------------


def _build_stats_plot_graph(plot_defn_cls, **plot_kwargs) -> Graph:
    load = LoadSample().instantiate(name="diabetes", label="Load Sample")
    fit = FitLinearRegression().instantiate(
        estimator="OLS", target="target", fixed_effects=["age", "bmi"], label="Fit Model"
    )
    plot = plot_defn_cls().instantiate(label="Plot", **plot_kwargs)
    load_to_fit = Edge(
        source=PortRef(node_id=load.id, port_id=_out_port(load, "frame").id),
        target=PortRef(node_id=fit.id, port_id=_in_port(fit, "frame").id),
    )
    fit_to_plot = Edge(
        source=PortRef(node_id=fit.id, port_id=_out_port(fit, "model").id),
        target=PortRef(node_id=plot.id, port_id=_in_port(plot, "model").id),
    )
    return Graph(
        nodes={load.id: load, fit.id: fit, plot.id: plot},
        edges={load_to_fit.id: load_to_fit, fit_to_plot.id: fit_to_plot},
    )


@pytest.mark.parametrize("plot_cls", [VizPlotCoefficients, VizPlotResiduals, VizPlotQQ, VizPlotAcf])
def test_stats_plot_codegen_is_parseable_and_ruff_clean(plot_cls) -> None:
    code = compile_to_code(_build_stats_plot_graph(plot_cls))
    _assert_parseable_and_ruff_clean(code)


def test_correlation_heatmap_codegen_is_parseable_and_ruff_clean() -> None:
    load = LoadSample().instantiate(name="diabetes", label="Load Sample")
    corr = Correlation().instantiate(label="Correlation")
    plot = VizPlotCorrelationHeatmap().instantiate(label="Plot Correlation Heatmap")
    load_to_corr = Edge(
        source=PortRef(node_id=load.id, port_id=_out_port(load, "frame").id),
        target=PortRef(node_id=corr.id, port_id=_in_port(corr, "frame").id),
    )
    corr_to_plot = Edge(
        source=PortRef(node_id=corr.id, port_id=_out_port(corr, "matrix").id),
        target=PortRef(node_id=plot.id, port_id=_in_port(plot, "matrix").id),
    )
    graph = Graph(
        nodes={load.id: load, corr.id: corr, plot.id: plot},
        edges={load_to_corr.id: load_to_corr, corr_to_plot.id: corr_to_plot},
    )
    _assert_parseable_and_ruff_clean(compile_to_code(graph))


def test_confusion_matrix_codegen_is_parseable_and_ruff_clean() -> None:
    load = LoadSample().instantiate(name="iris", label="Load Sample")
    fit = FitEstimator().instantiate(estimator="LogisticRegression", target="target", label="Fit")
    plot = VizPlotConfusionMatrix().instantiate(label="Plot Confusion Matrix")
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
    graph = Graph(
        nodes={load.id: load, fit.id: fit, plot.id: plot},
        edges={
            load_to_fit.id: load_to_fit,
            fit_to_plot_model.id: fit_to_plot_model,
            load_to_plot_frame.id: load_to_plot_frame,
        },
    )
    _assert_parseable_and_ruff_clean(compile_to_code(graph))


# ---------------------------------------------------------------------------
# 2. ADR-0002 equivalence: execute() vs running the emitted code, per plot node, on a fixed
#    seeded fixture (a real fitted model/matrix/classifier, not a stub).
# ---------------------------------------------------------------------------


@pytest.mark.equivalence
def test_plot_coefficients_equivalence() -> None:
    model = _fit_ols()
    defn = VizPlotCoefficients()
    node = defn.instantiate(label="Plot Coefficients")
    executed = defn.execute(node, inputs={"model": model})["plot"]
    scope = _run_codegen(defn, node, {"model": model})
    assert executed.spec == scope["plot"].spec


@pytest.mark.equivalence
def test_plot_residuals_equivalence() -> None:
    model = _fit_ols()
    defn = VizPlotResiduals()
    node = defn.instantiate(label="Plot Residuals")
    executed = defn.execute(node, inputs={"model": model})["plot"]
    scope = _run_codegen(defn, node, {"model": model})
    assert executed.spec == scope["plot"].spec


@pytest.mark.equivalence
def test_plot_qq_equivalence() -> None:
    model = _fit_ols()
    defn = VizPlotQQ()
    node = defn.instantiate(label="Plot Q-Q")
    executed = defn.execute(node, inputs={"model": model})["plot"]
    scope = _run_codegen(defn, node, {"model": model})
    assert executed.spec == scope["plot"].spec


@pytest.mark.equivalence
@pytest.mark.parametrize("kind", ["acf", "pacf"])
def test_plot_acf_equivalence(kind: str) -> None:
    model = _fit_ols()
    defn = VizPlotAcf()
    node = defn.instantiate(kind=kind, nlags=10, label="Plot ACF")
    executed = defn.execute(node, inputs={"model": model})["plot"]
    scope = _run_codegen(defn, node, {"model": model})
    assert executed.spec == scope["plot"].spec


@pytest.mark.equivalence
def test_plot_correlation_heatmap_equivalence() -> None:
    matrix = _fixed_corr_matrix()
    defn = VizPlotCorrelationHeatmap()
    node = defn.instantiate(label="Plot Correlation Heatmap")
    executed = defn.execute(node, inputs={"matrix": matrix})["plot"]
    scope = _run_codegen(defn, node, {"matrix": matrix})
    assert executed.spec == scope["plot"].spec


@pytest.mark.equivalence
def test_plot_confusion_matrix_equivalence() -> None:
    model, df = _fit_classifier()
    defn = VizPlotConfusionMatrix()
    node = defn.instantiate(label="Plot Confusion Matrix")
    executed = defn.execute(node, inputs={"model": model, "frame": df})["plot"]
    scope = _run_codegen(defn, node, {"model": model, "frame": df})
    assert executed.spec == scope["plot"].spec
