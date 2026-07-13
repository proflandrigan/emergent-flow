"""
emergentflow.nodes.examples.explain_plot_calibration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``explain.plot_calibration`` — a Model Explainability diagnostic plot node
(ADR 0020).

Renders a reliability diagram (calibration curve) for a fitted, BINARY-classification
``ml.FittedModel`` scored against labeled data. ``execute`` calls
``emergentflow.explain.plot_calibration`` directly and the code emitted by ``codegen`` calls the
same wrapper via the ``ef.`` alias, so the two paths are equivalent by construction (ADR 0002).
Needs no optional dependency.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.explain import plot_calibration
from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class ExplainPlotCalibration(NodeDefinition):
    """Render a reliability diagram (calibration curve) for a fitted binary classifier."""

    type = "explain.plot_calibration"
    version = 1
    family = "explain"
    label = "Plot Calibration"
    category = "Model Explainability"
    description = "Render a reliability diagram for a fitted binary classifier."

    ports = [
        PortSpec(
            name="model",
            direction=Direction.IN,
            data_type="Model",
            help="The fitted, binary-classification model to score.",
        ),
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="Labeled data to score the model against.",
        ),
        PortSpec(
            name="plot",
            direction=Direction.OUT,
            data_type="PlotSpec",
            help="The rendered calibration curve as a JSON-native PlotSpec.",
        ),
    ]
    params = [
        ParamSpec(
            name="n_bins",
            type_token="int",
            default=10,
            label="Number of bins",
            help="Number of probability buckets to bin predictions into.",
        ),
    ]

    def _args(self, node: Node) -> int:
        values = {p.name: p.value for p in node.params}
        return cast(int, values.get("n_bins"))

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        n_bins = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('plot')} = ef.explain.plot_calibration("
                f"{ctx.in_var('model')}, {ctx.in_var('frame')}, n_bins={n_bins!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        n_bins = self._args(node)
        return {"plot": plot_calibration(inputs["model"], inputs["frame"], n_bins=n_bins)}
