"""
emergentflow.nodes.examples.explain_plot_shap_beeswarm
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``explain.plot_shap_beeswarm`` — a Model Explainability plot node (ADR 0020).

Renders a jittered strip plot (a JSON-native approximation of SHAP's beeswarm summary) from a
tidy ``shap_values`` frame (``explain.shap_values``'s output). ``execute`` calls
``emergentflow.explain.plot_shap_beeswarm`` directly and the code emitted by ``codegen`` calls the
same wrapper via the ``ef.`` alias, so the two paths are equivalent by construction (ADR 0002).
Needs no optional dependency: it consumes an already-computed DataFrame, not a live model. Only
supports a single-output ``shap_values`` frame (regression or binary classification); a
multiclass frame raises ``ValueError`` at execute/codegen-run time (see
``emergentflow.explain.plot_shap_beeswarm``'s docstring).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from emergentflow.explain import plot_shap_beeswarm
from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import PortSpec

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class ExplainPlotShapBeeswarm(NodeDefinition):
    """Render a jittered strip plot (beeswarm approximation) of SHAP values per feature."""

    type = "explain.plot_shap_beeswarm"
    version = 1
    family = "explain"
    label = "Plot SHAP Beeswarm"
    category = "Model Explainability"
    description = "Render a jittered strip plot (beeswarm approximation) of SHAP values."

    ports = [
        PortSpec(
            name="shap_values",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The tidy SHAP values frame (explain.shap_values's output); single-output only.",
        ),
        PortSpec(
            name="plot",
            direction=Direction.OUT,
            data_type="PlotSpec",
            help="The rendered beeswarm-style plot as a JSON-native PlotSpec.",
        ),
    ]
    params = []

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('plot')} = ef.explain.plot_shap_beeswarm("
                f"{ctx.in_var('shap_values')})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        return {"plot": plot_shap_beeswarm(inputs["shap_values"])}
