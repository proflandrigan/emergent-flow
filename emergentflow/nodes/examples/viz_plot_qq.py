"""
emergentflow.nodes.examples.viz_plot_qq
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``viz.plot_qq`` — a model-aware plot node (Epic 12, Story 9).

Renders a Q-Q (quantile-quantile) plot of a fitted ``StatsModel``'s residuals against a normal
distribution. ``execute`` calls ``emergentflow.viz.plot_qq`` directly and the code emitted by
``codegen`` calls the same wrapper via the ``ef.`` alias, so the two paths are equivalent by
construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.viz import plot_qq

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import PortSpec

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class VizPlotQQ(NodeDefinition):
    """Render a Q-Q plot of a fitted statistical model's residuals."""

    type = "viz.plot_qq"
    version = 1
    family = "viz"
    label = "Plot Q-Q"
    category = "Visualization"
    description = "Render a Q-Q plot of a fitted StatsModel's residuals against a normal."

    ports = [
        PortSpec(
            name="model",
            direction=Direction.IN,
            data_type="StatsModel",
            help="The fitted statistical model to plot a Q-Q plot for.",
        ),
        PortSpec(
            name="plot",
            direction=Direction.OUT,
            data_type="PlotSpec",
            help="The rendered Q-Q plot as a JSON-native PlotSpec.",
        ),
    ]
    params = []

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=f"{ctx.out_var('plot')} = ef.viz.plot_qq({ctx.in_var('model')})",
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        return {"plot": plot_qq(inputs["model"])}
