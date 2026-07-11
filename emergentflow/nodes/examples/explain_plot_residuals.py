"""
emergentflow.nodes.examples.explain_plot_residuals
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``explain.plot_residuals`` — a Model Explainability diagnostic plot node
(ADR 0020).

Renders a scatter of predicted values vs. residuals (with a residual=0 reference line) for a
fitted, regression-task ``ml.FittedModel`` scored against labeled data. ``execute`` calls
``emergentflow.explain.plot_residuals`` directly and the code emitted by ``codegen`` calls the
same wrapper via the ``ef.`` alias, so the two paths are equivalent by construction (ADR 0002).
Needs no optional dependency. NOT the same node as ``viz.plot_residuals`` (which works on a
``stats.FittedStatsModel``, not an ``ml.FittedModel``) — see this module's package docstring for
why both exist.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from emergentflow.explain import plot_residuals
from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import PortSpec

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class ExplainPlotResiduals(NodeDefinition):
    """Render a predicted-vs-residual scatter for a fitted regression model."""

    type = "explain.plot_residuals"
    version = 1
    family = "explain"
    label = "Plot Residuals"
    category = "Model Explainability"
    description = "Render a predicted-vs-residual scatter for a fitted regression model."

    ports = [
        PortSpec(
            name="model",
            direction=Direction.IN,
            data_type="Model",
            help="The fitted, regression-task model to score.",
        ),
        PortSpec(
            name="frame",
            direction=Direction.IN,
            data_type="DataFrame",
            help="Labeled data to score the model against.",
        ),
        PortSpec(
            name="plot",
            direction=Direction.OUT,
            data_type="PlotSpec",
            help="The rendered predicted-vs-residual scatter as a JSON-native PlotSpec.",
        ),
    ]
    params = []

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('plot')} = ef.explain.plot_residuals("
                f"{ctx.in_var('model')}, {ctx.in_var('frame')})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        return {"plot": plot_residuals(inputs["model"], inputs["frame"])}
