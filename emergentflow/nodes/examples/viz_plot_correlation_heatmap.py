"""
emergentflow.nodes.examples.viz_plot_correlation_heatmap
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``viz.plot_correlation_heatmap`` — a bespoke plot node (Epic 12, Story 9).

Renders a heatmap from a tidy correlation matrix (the output of ``stats.correlation``).
``execute`` calls ``emergentflow.viz.plot_correlation_heatmap`` directly and the code emitted by
``codegen`` calls the same wrapper via the ``ef.`` alias, so the two paths are equivalent by
construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.viz import plot_correlation_heatmap

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import PortSpec

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class VizPlotCorrelationHeatmap(NodeDefinition):
    """Render a heatmap from a tidy correlation matrix."""

    type = "viz.plot_correlation_heatmap"
    version = 1
    family = "viz"
    label = "Plot Correlation Heatmap"
    category = "Visualization"
    description = "Render a heatmap from a tidy correlation matrix (stats.correlation's output)."

    ports = [
        PortSpec(
            name="matrix",
            direction=Direction.IN,
            data_type="DataFrame",
            help="A tidy correlation matrix (e.g. from stats.correlation): a leading 'column' "
            "field of row labels, plus one column per correlated variable.",
        ),
        PortSpec(
            name="plot",
            direction=Direction.OUT,
            data_type="PlotSpec",
            help="The rendered correlation heatmap as a JSON-native PlotSpec.",
        ),
    ]
    params = []

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('plot')} = ef.viz.plot_correlation_heatmap({ctx.in_var('matrix')})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        return {"plot": plot_correlation_heatmap(inputs["matrix"])}
