"""
emergentflow.nodes.examples.viz_plot_residuals
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``viz.plot_residuals`` — a model-aware plot node (Epic 12, Story 9).

Renders a fitted-values-vs-residuals scatter plot from a fitted ``StatsModel``. ``execute``
calls ``emergentflow.viz.plot_residuals`` directly and the code emitted by ``codegen`` calls the
same wrapper via the ``ef.`` alias, so the two paths are equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.viz import plot_residuals

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import PortSpec

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class VizPlotResiduals(NodeDefinition):
    """Render a fitted-values-vs-residuals plot from a fitted statistical model."""

    type = "viz.plot_residuals"
    version = 1
    family = "viz"
    label = "Plot Residuals"
    category = "Visualization"
    description = "Render a fitted-values-vs-residuals scatter plot from a fitted StatsModel."

    ports = [
        PortSpec(
            name="model",
            direction=Direction.IN,
            data_type="StatsModel",
            help="The fitted statistical model to plot residuals for.",
        ),
        PortSpec(
            name="plot",
            direction=Direction.OUT,
            data_type="PlotSpec",
            help="The rendered residual plot as a JSON-native PlotSpec.",
        ),
    ]
    params = []

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=f"{ctx.out_var('plot')} = ef.viz.plot_residuals({ctx.in_var('model')})",
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        return {"plot": plot_residuals(inputs["model"])}
