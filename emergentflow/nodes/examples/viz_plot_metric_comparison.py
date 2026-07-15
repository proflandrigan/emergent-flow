"""
emergentflow.nodes.examples.viz_plot_metric_comparison
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``viz.plot_metric_comparison`` — a bespoke recommender-aware plot node
(Epic 15, Story 14).

Renders a grouped bar chart comparing multiple recommenders across evaluation metrics, from
``ef.recommend.compare``'s tidy comparison DataFrame. ``execute`` calls
``emergentflow.viz.plot_metric_comparison`` directly and the code emitted by ``codegen`` calls
the same wrapper via the ``ef.`` alias, so the two paths are equivalent by construction
(ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.viz import plot_metric_comparison

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class VizPlotMetricComparison(NodeDefinition):
    """Render a grouped bar chart comparing multiple recommenders across metrics."""

    type = "viz.plot_metric_comparison"
    version = 1
    family = "viz"
    label = "Plot Metric Comparison"
    category = "Visualization"
    description = "Render a grouped bar chart comparing multiple recommenders across metrics."

    ports = [
        PortSpec(
            name="comparison",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The tidy comparison DataFrame from ef.recommend.compare().",
        ),
        PortSpec(
            name="plot",
            direction=Direction.OUT,
            data_type="PlotSpec",
            help="The rendered grouped bar chart as a JSON-native PlotSpec.",
        ),
    ]
    params = [
        ParamSpec(
            name="metrics",
            type_token="list[str]",
            default=None,
            label="Metrics",
            help="Subset of metric columns to plot; unset means every standard metric column "
            "present in the comparison frame.",
        ),
    ]

    def _args(self, node: Node) -> tuple[list[str] | None]:
        values = {p.name: p.value for p in node.params}
        return (cast("list[str] | None", values.get("metrics")),)

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        (metrics,) = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('plot')} = ef.viz.plot_metric_comparison("
                f"{ctx.in_var('comparison')}, metrics={metrics!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        (metrics,) = self._args(node)
        return {"plot": plot_metric_comparison(inputs["comparison"], metrics=metrics)}
