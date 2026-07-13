"""
Golden + equivalence tests for the ADR 0020 ``explain.plot_shap_beeswarm`` node.
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
    ExplainPlotShapBeeswarm,
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
    """3 rows x 2 features, single-output shape."""
    return pd.DataFrame(
        {
            "row_index": [0, 1, 2, 0, 1, 2],
            "feature": ["x1", "x1", "x1", "x2", "x2", "x2"],
            "feature_value": [1.0, 2.0, 3.0, 10.0, 20.0, 30.0],
            "shap_value": [0.5, -0.1, 0.3, -0.2, 0.4, -0.4],
            "base_value": [0.1] * 6,
        }
    )


def _multiclass_shap_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "row_index": [0, 0, 0, 0],
            "feature": ["x1", "x2", "x1", "x2"],
            "feature_value": [1.0, 2.0, 1.0, 2.0],
            "shap_value": [0.5, -0.2, -0.5, 0.2],
            "base_value": [0.1] * 4,
            "class": ["a", "a", "b", "b"],
        }
    )


def test_plot_shap_beeswarm_codegen_is_parseable_and_ruff_clean() -> None:
    load = LoadSample().instantiate(name="diabetes", label="Load Sample")
    fit = FitEstimator().instantiate(estimator="Ridge", target="target", label="Fit")
    explain = ExplainShapValues().instantiate(seed=0, background_samples=50, label="SHAP Values")
    plot = ExplainPlotShapBeeswarm().instantiate(label="Plot SHAP Beeswarm")
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
def test_plot_shap_beeswarm_equivalence() -> None:
    shap_frame = _single_output_shap_frame()
    defn = ExplainPlotShapBeeswarm()
    node = defn.instantiate(label="Plot SHAP Beeswarm")
    executed = defn.execute(node, inputs={"shap_values": shap_frame})["plot"]
    scope = _run_codegen(defn, node, {"shap_values": shap_frame})
    assert executed.spec == scope["plot"].spec


def test_plot_shap_beeswarm_rejects_multiclass_frame() -> None:
    defn = ExplainPlotShapBeeswarm()
    node = defn.instantiate(label="Plot SHAP Beeswarm")
    with pytest.raises(ValueError, match="multiclass"):
        defn.execute(node, inputs={"shap_values": _multiclass_shap_frame()})


def test_plot_shap_beeswarm_one_marker_per_row() -> None:
    from emergentflow.explain import plot_shap_beeswarm

    shap_frame = _single_output_shap_frame()
    plot = plot_shap_beeswarm(shap_frame)
    trace = plot.spec["data"][0]
    assert len(trace["x"]) == len(shap_frame)
    assert len(trace["y"]) == len(shap_frame)
    assert len(trace["marker"]["color"]) == len(shap_frame)


def test_plot_shap_beeswarm_y_ticks_are_features_ordered_by_importance() -> None:
    from emergentflow.explain import plot_shap_beeswarm

    # x1's mean |shap| = (0.5 + 0.1 + 0.3) / 3 = 0.3; x2's = (0.2 + 0.4 + 0.4) / 3 = 0.333...
    # -> x2 ranks higher, so it must be LAST in the ascending-ordered y-axis ticktext.
    plot = plot_shap_beeswarm(_single_output_shap_frame())
    ticktext = plot.spec["layout"]["yaxis"]["ticktext"]
    assert ticktext[-1] == "x2"
    assert ticktext[0] == "x1"
