"""
emergentflow.nodes.examples.viz_plot_confusion_matrix
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``viz.plot_confusion_matrix`` — a bespoke plot node (Epic 12, Story 9).

Renders a confusion-matrix heatmap for a fitted Epic 8 ``Model`` scored against a labeled
``DataFrame``. ``execute`` calls ``emergentflow.viz.plot_confusion_matrix`` directly and the
code emitted by ``codegen`` calls the same wrapper via the ``ef.`` alias, so the two paths are
equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.viz import plot_confusion_matrix

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import PortSpec

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class VizPlotConfusionMatrix(NodeDefinition):
    """Render a confusion-matrix heatmap for a fitted classifier scored against labeled data."""

    type = "viz.plot_confusion_matrix"
    version = 1
    family = "viz"
    label = "Plot Confusion Matrix"
    category = "Visualization"
    description = "Render a confusion-matrix heatmap for a fitted classifier."

    ports = [
        PortSpec(
            name="model",
            direction=Direction.IN,
            data_type="Model",
            help="The fitted classifier to score.",
        ),
        PortSpec(
            name="frame",
            direction=Direction.IN,
            data_type="DataFrame",
            help="Labeled data to score the classifier against.",
        ),
        PortSpec(
            name="plot",
            direction=Direction.OUT,
            data_type="PlotSpec",
            help="The rendered confusion-matrix heatmap as a JSON-native PlotSpec.",
        ),
    ]
    params = []

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('plot')} = ef.viz.plot_confusion_matrix("
                f"{ctx.in_var('model')}, {ctx.in_var('frame')})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        return {"plot": plot_confusion_matrix(inputs["model"], inputs["frame"])}
