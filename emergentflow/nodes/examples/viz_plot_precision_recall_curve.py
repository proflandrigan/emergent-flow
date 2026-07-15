"""
emergentflow.nodes.examples.viz_plot_precision_recall_curve
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``viz.plot_precision_recall_curve`` — a bespoke recommender-aware plot node
(Epic 15, Story 14).

Sweeps k=1..k_max and renders the precision@k/recall@k trade-off for a fitted recommender
scored against held-out interactions. ``execute`` calls
``emergentflow.viz.plot_precision_recall_curve`` directly and the code emitted by ``codegen``
calls the same wrapper via the ``ef.`` alias, so the two paths are equivalent by construction
(ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.viz import plot_precision_recall_curve

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class VizPlotPrecisionRecallCurve(NodeDefinition):
    """Sweep k and render the precision@k/recall@k trade-off for a fitted recommender."""

    type = "viz.plot_precision_recall_curve"
    version = 1
    family = "viz"
    label = "Plot Precision-Recall Curve"
    category = "Visualization"
    description = "Render the precision@k/recall@k trade-off curve for a fitted recommender."

    ports = [
        PortSpec(
            name="recommender",
            direction=Direction.IN,
            data_type="Recommender",
            help="The fitted recommender to sweep.",
        ),
        PortSpec(
            name="test_interactions",
            direction=Direction.IN,
            data_type="InteractionMatrix",
            help="Held-out interactions to score against.",
        ),
        PortSpec(
            name="plot",
            direction=Direction.OUT,
            data_type="PlotSpec",
            help="The rendered precision-recall trade-off curve as a JSON-native PlotSpec.",
        ),
    ]
    params = [
        ParamSpec(
            name="k_max",
            type_token="int",
            default=50,
            label="Max k",
            help="Sweep k from 1 to this value.",
        ),
    ]

    def _args(self, node: Node) -> tuple[int]:
        values = {p.name: p.value for p in node.params}
        return (cast(int, values.get("k_max", 50)),)

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        (k_max,) = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('plot')} = ef.viz.plot_precision_recall_curve("
                f"{ctx.in_var('recommender')}, {ctx.in_var('test_interactions')}, "
                f"k_max={k_max!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        (k_max,) = self._args(node)
        return {
            "plot": plot_precision_recall_curve(
                inputs["recommender"], inputs["test_interactions"], k_max=k_max
            )
        }
