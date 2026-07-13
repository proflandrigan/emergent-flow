"""
emergentflow.nodes.examples.explain_plot_roc_pr
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``explain.plot_roc_pr`` — a Model Explainability diagnostic plot node
(ADR 0020).

Renders an ROC curve or a Precision-Recall curve (selected by the ``curve`` param) for a fitted,
BINARY-classification ``ml.FittedModel`` scored against labeled data. ``execute`` calls
``emergentflow.explain.plot_roc_pr`` directly and the code emitted by ``codegen`` calls the same
wrapper via the ``ef.`` alias, so the two paths are equivalent by construction (ADR 0002). Needs
no optional dependency.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.explain import plot_roc_pr
from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.ir.params import ParamValue

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class ExplainPlotRocPr(NodeDefinition):
    """Render an ROC or Precision-Recall curve for a fitted binary classifier."""

    type = "explain.plot_roc_pr"
    version = 1
    family = "explain"
    label = "Plot ROC / PR"
    category = "Model Explainability"
    description = "Render an ROC or Precision-Recall curve for a fitted binary classifier."

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
            help="The rendered ROC or Precision-Recall curve as a JSON-native PlotSpec.",
        ),
    ]
    params = [
        ParamSpec(
            name="curve",
            type_token="str",
            default="roc",
            label="Curve",
            help="Which curve to render.",
            hints=ValidationHints(choices=cast("list[ParamValue]", ["roc", "pr"]), widget="select"),
        ),
    ]

    def _args(self, node: Node) -> str:
        values = {p.name: p.value for p in node.params}
        return cast(str, values.get("curve"))

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        curve = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('plot')} = ef.explain.plot_roc_pr("
                f"{ctx.in_var('model')}, {ctx.in_var('frame')}, curve={curve!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        curve = self._args(node)
        return {"plot": plot_roc_pr(inputs["model"], inputs["frame"], curve=curve)}
