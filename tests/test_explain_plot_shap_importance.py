"""
Golden + equivalence tests for the ADR 0020 ``explain.plot_shap_importance`` node.
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
    ExplainPlotShapImportance,
    ExplainShapValues,
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


# ---------------------------------------------------------------------------
# Fixtures -- hand-built tidy shap_values frames (no shap dependency needed).
# ---------------------------------------------------------------------------


def _single_output_shap_frame() -> pd.DataFrame:
    """2 rows x 2 features, single-output (regression / binary classification shape)."""
    return pd.DataFrame(
        {
            "row_index": [0, 0, 1, 1],
            "feature": ["x1", "x2", "x1", "x2"],
            "feature_value": [1.0, 2.0, 1.5, 2.5],
            "shap_value": [0.5, -0.2, -0.3, 0.4],
            "base_value": [0.1, 0.1, 0.1, 0.1],
        }
    )


def _multiclass_shap_frame() -> pd.DataFrame:
    """2 rows x 2 features x 2 classes, multiclass shape (a 'class' column present)."""
    return pd.DataFrame(
        {
            "row_index": [0, 0, 1, 1, 0, 0, 1, 1],
            "feature": ["x1", "x2", "x1", "x2", "x1", "x2", "x1", "x2"],
            "feature_value": [1.0, 2.0, 1.5, 2.5, 1.0, 2.0, 1.5, 2.5],
            "shap_value": [0.5, -0.2, -0.3, 0.4, -0.5, 0.2, 0.3, -0.4],
            "base_value": [0.1] * 8,
            "class": ["a", "a", "a", "a", "b", "b", "b", "b"],
        }
    )


# ---------------------------------------------------------------------------
# 1. Golden-code quality: a realistic full graph (does NOT need shap installed --
#    compile_to_code only generates source text, it never executes it).
# ---------------------------------------------------------------------------


def test_plot_shap_importance_codegen_is_parseable_and_ruff_clean() -> None:
    load = LoadSample().instantiate(name="diabetes", label="Load Sample")
    fit = FitEstimator().instantiate(estimator="Ridge", target="target", label="Fit")
    explain = ExplainShapValues().instantiate(seed=0, background_samples=50, label="SHAP Values")
    plot = ExplainPlotShapImportance().instantiate(label="Plot SHAP Importance")
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
    explain_to_plot = Edge(
        source=PortRef(node_id=explain.id, port_id=_out_port(explain, "shap_values").id),
        target=PortRef(node_id=plot.id, port_id=_in_port(plot, "shap_values").id),
    )
    graph = Graph(
        nodes={load.id: load, fit.id: fit, explain.id: explain, plot.id: plot},
        edges={
            load_to_fit.id: load_to_fit,
            fit_to_explain_model.id: fit_to_explain_model,
            load_to_explain_frame.id: load_to_explain_frame,
            explain_to_plot.id: explain_to_plot,
        },
    )
    _assert_parseable_and_ruff_clean(compile_to_code(graph))


# ---------------------------------------------------------------------------
# 2. ADR-0002 equivalence, one per shape (single-output, multiclass).
# ---------------------------------------------------------------------------


@pytest.mark.equivalence
def test_plot_shap_importance_single_output_equivalence() -> None:
    shap_frame = _single_output_shap_frame()
    defn = ExplainPlotShapImportance()
    node = defn.instantiate(label="Plot SHAP Importance")
    executed = defn.execute(node, inputs={"shap_values": shap_frame})["plot"]
    scope = _run_codegen(defn, node, {"shap_values": shap_frame})
    assert executed.spec == scope["plot"].spec


@pytest.mark.equivalence
def test_plot_shap_importance_multiclass_equivalence() -> None:
    shap_frame = _multiclass_shap_frame()
    defn = ExplainPlotShapImportance()
    node = defn.instantiate(label="Plot SHAP Importance")
    executed = defn.execute(node, inputs={"shap_values": shap_frame})["plot"]
    scope = _run_codegen(defn, node, {"shap_values": shap_frame})
    assert executed.spec == scope["plot"].spec


# ---------------------------------------------------------------------------
# 3. Behavioral sanity checks (not just equivalence -- prove the chart data is right).
# ---------------------------------------------------------------------------


def test_plot_shap_importance_single_output_bar_values() -> None:
    """x1's mean |shap| is (0.5 + 0.3) / 2 = 0.4; x2's is (0.2 + 0.4) / 2 = 0.3 -- x1 ranks
    higher, so it must be the LAST entry in the ascending-sorted y-axis (plotly renders the
    last category at the top of a horizontal bar chart)."""
    from emergentflow.explain import plot_shap_importance

    plot = plot_shap_importance(_single_output_shap_frame())
    bar_trace = plot.spec["data"][0]
    assert bar_trace["y"][-1] == "x1"
    assert bar_trace["y"][0] == "x2"


def test_plot_shap_importance_multiclass_has_one_trace_per_class() -> None:
    from emergentflow.explain import plot_shap_importance

    plot = plot_shap_importance(_multiclass_shap_frame())
    trace_names = {trace["name"] for trace in plot.spec["data"]}
    assert trace_names == {"a", "b"}
