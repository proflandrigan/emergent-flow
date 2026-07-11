"""
emergentflow.nodes.examples.explain_plot_shap_importance
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``explain.plot_shap_importance`` — a Model Explainability plot node (ADR 0020).

Renders a ranked bar chart of mean |SHAP value| per feature from a tidy ``shap_values`` frame
(``explain.shap_values``'s output). ``execute`` calls ``emergentflow.explain.plot_shap_importance``
directly and the code emitted by ``codegen`` calls the same wrapper via the ``ef.`` alias, so the
two paths are equivalent by construction (ADR 0002). Needs no optional dependency: it consumes an
already-computed DataFrame, not a live model.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from emergentflow.explain import plot_shap_importance
from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import PortSpec

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class ExplainPlotShapImportance(NodeDefinition):
    """Render a ranked bar chart of mean |SHAP value| per feature."""

    type = "explain.plot_shap_importance"
    version = 1
    family = "explain"
    label = "Plot SHAP Importance"
    category = "Model Explainability"
    description = "Render a ranked bar chart of mean |SHAP value| per feature."

    ports = [
        PortSpec(
            name="shap_values",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The tidy SHAP values frame (explain.shap_values's output).",
        ),
        PortSpec(
            name="plot",
            direction=Direction.OUT,
            data_type="PlotSpec",
            help="The rendered feature-importance bar chart as a JSON-native PlotSpec.",
        ),
    ]
    params = []

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('plot')} = ef.explain.plot_shap_importance("
                f"{ctx.in_var('shap_values')})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        return {"plot": plot_shap_importance(inputs["shap_values"])}
