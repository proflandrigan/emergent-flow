"""
emergentflow.nodes.examples.finalize_model
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``ml.finalize_model`` — refit a fitted model on the full dataset
with its fitted hyperparameters (ADR 0016).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.ml import finalize_model

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class FinalizeModel(NodeDefinition):
    """Refit a fitted model on the full dataset with its fitted hyperparameters."""

    type = "ml.finalize_model"
    version = 1
    family = "ml"
    label = "Finalize Model"
    category = "Machine Learning"
    description = "Refit a fitted model on the full dataset with its fitted hyperparameters."

    ports = [
        PortSpec(
            name="model",
            direction=Direction.IN,
            data_type="Model",
            help="The fitted model to refit.",
        ),
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="Data (features + target) to refit the model on.",
        ),
        PortSpec(
            name="model",
            direction=Direction.OUT,
            data_type="Model",
            help="The refit final model.",
        ),
    ]
    params = [
        ParamSpec(
            name="target",
            type_token="str",
            default=None,
            label="Target column",
            help="Target column; defaults to the model's recorded target.",
            hints=ValidationHints(widget="column"),
        ),
    ]

    def _args(self, node: Node) -> str | None:
        values = {p.name: p.value for p in node.params}
        return cast("str | None", values.get("target"))

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        target = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('model')} = ef.ml.finalize_model("
                f"{ctx.in_var('model')}, {ctx.in_var('frame')}, target={target!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        target = self._args(node)
        return {"model": finalize_model(inputs["model"], inputs["frame"], target=target)}
