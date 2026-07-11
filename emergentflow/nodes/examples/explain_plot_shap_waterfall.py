"""
emergentflow.nodes.examples.explain_plot_shap_waterfall
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``explain.plot_shap_waterfall`` — a Model Explainability plot node (ADR 0020).

Renders a waterfall chart explaining ONE row's prediction (base value -> per-feature
contributions -> final prediction) from a tidy ``shap_values`` frame
(``explain.shap_values``'s output). ``execute`` calls
``emergentflow.explain.plot_shap_waterfall`` directly and the code emitted by ``codegen`` calls
the same wrapper via the ``ef.`` alias, so the two paths are equivalent by construction
(ADR 0002). Needs no optional dependency. Only supports a single-output ``shap_values`` frame
(regression or binary classification); a multiclass frame or an unknown ``row_index`` raises
``ValueError`` at execute/codegen-run time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.explain import plot_shap_waterfall
from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class ExplainPlotShapWaterfall(NodeDefinition):
    """Render a waterfall chart explaining one row's prediction."""

    type = "explain.plot_shap_waterfall"
    version = 1
    family = "explain"
    label = "Plot SHAP Waterfall"
    category = "Model Explainability"
    description = "Render a waterfall chart explaining one row's prediction."

    ports = [
        PortSpec(
            name="shap_values",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The tidy SHAP values frame (explain.shap_values's output); single-output only.",
        ),
        PortSpec(
            name="plot",
            direction=Direction.OUT,
            data_type="PlotSpec",
            help="The rendered waterfall chart as a JSON-native PlotSpec.",
        ),
    ]
    params = [
        ParamSpec(
            name="row_index",
            type_token="int",
            required=True,
            label="Row index",
            help="Which row (0-indexed position in the frame shap_values was run on) to explain.",
        ),
    ]

    def _args(self, node: Node) -> int:
        values = {p.name: p.value for p in node.params}
        return cast(int, values.get("row_index"))

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        row_index = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('plot')} = ef.explain.plot_shap_waterfall("
                f"{ctx.in_var('shap_values')}, row_index={row_index!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        row_index = self._args(node)
        return {"plot": plot_shap_waterfall(inputs["shap_values"], row_index=row_index)}
