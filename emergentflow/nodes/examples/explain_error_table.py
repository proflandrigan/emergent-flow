"""
emergentflow.nodes.examples.explain_error_table
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``explain.error_table`` — the Model Explainability family's error-analysis node
(ADR 0020).

Scores a fitted, supervised ``ml.FittedModel`` against a labeled DataFrame and returns the
top-N worst-error rows (largest |residual| for regression; lowest-confidence/misclassified rows
for classification), as a tidy DataFrame. ``execute`` calls ``emergentflow.explain.error_table``
directly and the code emitted by ``codegen`` calls the same wrapper via the ``ef.`` alias, so the
two paths are equivalent by construction (ADR 0002). Needs no optional dependency: pure sklearn/
pandas, no SHAP computation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.explain import error_table
from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class ExplainErrorTable(NodeDefinition):
    """Return the top-N worst-error rows for a fitted model scored against labeled data."""

    type = "explain.error_table"
    version = 1
    family = "explain"
    label = "Error Table"
    category = "Model Explainability"
    description = "Return the top-N worst-error rows for a fitted model."

    ports = [
        PortSpec(
            name="model",
            direction=Direction.IN,
            data_type="Model",
            help="The fitted, supervised model to score.",
        ),
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="Labeled data to score the model against.",
        ),
        PortSpec(
            name="error_table",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="The top-N worst-error rows, sorted worst-first.",
        ),
    ]
    params = [
        ParamSpec(
            name="top_n",
            type_token="int",
            default=20,
            label="Top N",
            help="Number of worst-error rows to return.",
        ),
    ]

    def _args(self, node: Node) -> int:
        values = {p.name: p.value for p in node.params}
        return cast(int, values.get("top_n"))

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        top_n = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('error_table')} = ef.explain.error_table("
                f"{ctx.in_var('model')}, {ctx.in_var('frame')}, top_n={top_n!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        top_n = self._args(node)
        return {"error_table": error_table(inputs["model"], inputs["frame"], top_n=top_n)}
