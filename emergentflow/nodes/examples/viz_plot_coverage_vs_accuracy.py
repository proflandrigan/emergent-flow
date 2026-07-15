"""
emergentflow.nodes.examples.viz_plot_coverage_vs_accuracy
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``viz.plot_coverage_vs_accuracy`` — a bespoke recommender-aware plot node
(Epic 15, Story 14).

Renders a scatter plot of each recommender's coverage against an accuracy metric (default
NDCG@k), from ``ef.recommend.compare``'s tidy comparison DataFrame — surfacing the
accuracy/diversity trade-off. ``execute`` calls ``emergentflow.viz.plot_coverage_vs_accuracy``
directly and the code emitted by ``codegen`` calls the same wrapper via the ``ef.`` alias, so
the two paths are equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.viz import plot_coverage_vs_accuracy

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class VizPlotCoverageVsAccuracy(NodeDefinition):
    """Render a scatter plot of each recommender's coverage against an accuracy metric."""

    type = "viz.plot_coverage_vs_accuracy"
    version = 1
    family = "viz"
    label = "Plot Coverage vs. Accuracy"
    category = "Visualization"
    description = (
        "Render coverage vs. accuracy scatter to surface the accuracy/diversity trade-off."
    )

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
            help="The rendered coverage-vs-accuracy scatter as a JSON-native PlotSpec.",
        ),
    ]
    params = [
        ParamSpec(
            name="accuracy_metric",
            type_token="str",
            default="mean_ndcg_at_k",
            label="Accuracy metric",
            help="Which comparison-frame column to plot on the y-axis as the accuracy metric.",
        ),
    ]

    def _args(self, node: Node) -> tuple[str]:
        values = {p.name: p.value for p in node.params}
        return (cast(str, values.get("accuracy_metric", "mean_ndcg_at_k")),)

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        (accuracy_metric,) = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('plot')} = ef.viz.plot_coverage_vs_accuracy("
                f"{ctx.in_var('comparison')}, accuracy_metric={accuracy_metric!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        (accuracy_metric,) = self._args(node)
        return {
            "plot": plot_coverage_vs_accuracy(inputs["comparison"], accuracy_metric=accuracy_metric)
        }
