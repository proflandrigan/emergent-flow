"""
emergentflow.nodes.examples.viz_plot_popularity_distribution
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``viz.plot_popularity_distribution`` — a bespoke recommender-aware plot node
(Epic 15, Story 14).

Renders a long-tail histogram of recommendation frequency vs. item popularity rank (log scale)
for a fitted recommender, showing whether it is biased toward popular items. ``execute`` calls
``emergentflow.viz.plot_popularity_distribution`` directly and the code emitted by ``codegen``
calls the same wrapper via the ``ef.`` alias, so the two paths are equivalent by construction
(ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.viz import plot_popularity_distribution

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class VizPlotPopularityDistribution(NodeDefinition):
    """Render a long-tail histogram of recommendation frequency vs. item popularity rank."""

    type = "viz.plot_popularity_distribution"
    version = 1
    family = "viz"
    label = "Plot Popularity Distribution"
    category = "Visualization"
    description = "Render recommendation frequency vs. item popularity rank (log scale)."

    ports = [
        PortSpec(
            name="recommender",
            direction=Direction.IN,
            data_type="Recommender",
            help="The fitted recommender to analyze.",
        ),
        PortSpec(
            name="interactions",
            direction=Direction.IN,
            data_type="InteractionMatrix",
            help="Interactions used to rank item popularity.",
        ),
        PortSpec(
            name="plot",
            direction=Direction.OUT,
            data_type="PlotSpec",
            help="The rendered popularity-distribution histogram as a JSON-native PlotSpec.",
        ),
    ]
    params = [
        ParamSpec(
            name="n",
            type_token="int",
            default=10,
            label="Recommendations per user",
            help="Number of recommendations generated per user to tally item frequency.",
        ),
    ]

    def _args(self, node: Node) -> tuple[int]:
        values = {p.name: p.value for p in node.params}
        return (cast(int, values.get("n", 10)),)

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        (n,) = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('plot')} = ef.viz.plot_popularity_distribution("
                f"{ctx.in_var('recommender')}, {ctx.in_var('interactions')}, n={n!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        (n,) = self._args(node)
        return {
            "plot": plot_popularity_distribution(inputs["recommender"], inputs["interactions"], n=n)
        }
