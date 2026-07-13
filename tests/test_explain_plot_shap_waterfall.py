"""
Golden + equivalence tests for the ADR 0020 ``explain.plot_shap_waterfall`` node.
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
    ExplainPlotShapWaterfall,
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


def _single_output_shap_frame() -> pd.DataFrame:
    """2 rows x 3 features, single-output shape."""
    return pd.DataFrame(
        {
            "row_index": [0, 0, 0, 1, 1, 1],
            "feature": ["x1", "x2", "x3", "x1", "x2", "x3"],
            "feature_value": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
            "shap_value": [0.5, -0.1, 0.3, -0.2, 0.05, -0.4],
            "base_value": [0.1, 0.1, 0.1, 0.1, 0.1, 0.1],
        }
    )


def _multiclass_shap_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "row_index": [0, 0],
            "feature": ["x1", "x1"],
            "feature_value": [1.0, 1.0],
            "shap_value": [0.5, -0.5],
            "base_value": [0.1, 0.1],
            "class": ["a", "b"],
        }
    )


def test_plot_shap_waterfall_codegen_is_parseable_and_ruff_clean() -> None:
    load = LoadSample().instantiate(name="diabetes", label="Load Sample")
    fit = FitEstimator().instantiate(estimator="Ridge", target="target", label="Fit")
    explain = ExplainShapValues().instantiate(seed=0, background_samples=50, label="SHAP Values")
    plot = ExplainPlotShapWaterfall().instantiate(row_index=0, label="Plot SHAP Waterfall")
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


@pytest.mark.equivalence
@pytest.mark.parametrize("row_index", [0, 1])
def test_plot_shap_waterfall_equivalence(row_index: int) -> None:
    shap_frame = _single_output_shap_frame()
    defn = ExplainPlotShapWaterfall()
    node = defn.instantiate(row_index=row_index, label="Plot SHAP Waterfall")
    executed = defn.execute(node, inputs={"shap_values": shap_frame})["plot"]
    scope = _run_codegen(defn, node, {"shap_values": shap_frame})
    assert executed.spec == scope["plot"].spec


def test_plot_shap_waterfall_rejects_multiclass_frame() -> None:
    defn = ExplainPlotShapWaterfall()
    node = defn.instantiate(row_index=0, label="Plot SHAP Waterfall")
    with pytest.raises(ValueError, match="multiclass"):
        defn.execute(node, inputs={"shap_values": _multiclass_shap_frame()})


def test_plot_shap_waterfall_rejects_unknown_row_index() -> None:
    defn = ExplainPlotShapWaterfall()
    node = defn.instantiate(row_index=99, label="Plot SHAP Waterfall")
    with pytest.raises(ValueError, match="row_index"):
        defn.execute(node, inputs={"shap_values": _single_output_shap_frame()})


def test_plot_shap_waterfall_ends_at_base_plus_sum_of_shap() -> None:
    from emergentflow.explain import plot_shap_waterfall

    # row 0: base_value=0.1, shap = 0.5 - 0.1 + 0.3 = 0.7 -> prediction = 0.8
    plot = plot_shap_waterfall(_single_output_shap_frame(), row_index=0)
    trace = plot.spec["data"][0]
    assert trace["y"][0] == pytest.approx(0.1)  # base value
    assert trace["y"][-1] == pytest.approx(0.8)  # prediction
    assert trace["measure"][0] == "absolute"
    assert trace["measure"][-1] == "total"
    assert trace["measure"][1:-1] == ["relative"] * 3


def test_plot_shap_waterfall_orders_features_by_descending_magnitude() -> None:
    from emergentflow.explain import plot_shap_waterfall

    # row 0 shap values: x1=0.5, x2=-0.1, x3=0.3 -> |0.5| > |0.3| > |0.1|
    plot = plot_shap_waterfall(_single_output_shap_frame(), row_index=0)
    trace = plot.spec["data"][0]
    assert trace["x"][1:-1] == ["x1", "x3", "x2"]
