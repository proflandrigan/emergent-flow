"""
emergentflow.nodes.examples.viz_plot_coefficients
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``viz.plot_coefficients`` — a model-aware plot node (Epic 12, Story 9).

Renders a coefficient / forest plot from a fitted ``StatsModel``'s tidy coefficient frame.
``execute`` calls ``emergentflow.viz.plot_coefficients`` directly and the code emitted by
``codegen`` calls the same wrapper via the ``ef.`` alias, so the two paths are equivalent by
construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.viz import plot_coefficients

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import PortSpec

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class VizPlotCoefficients(NodeDefinition):
    """Render a coefficient / forest plot from a fitted statistical model."""

    type = "viz.plot_coefficients"
    version = 1
    family = "viz"
    label = "Plot Coefficients"
    category = "Visualization"
    description = "Render a coefficient / forest plot from a fitted StatsModel."

    ports = [
        PortSpec(
            name="model",
            direction=Direction.IN,
            data_type="StatsModel",
            help="The fitted statistical model whose coefficients to plot.",
        ),
        PortSpec(
            name="plot",
            direction=Direction.OUT,
            data_type="PlotSpec",
            help="The rendered coefficient/forest plot as a JSON-native PlotSpec.",
        ),
    ]
    params = []

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(f"{ctx.out_var('plot')} = ef.viz.plot_coefficients({ctx.in_var('model')})"),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        return {"plot": plot_coefficients(inputs["model"])}
