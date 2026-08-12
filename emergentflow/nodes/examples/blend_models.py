"""
emergentflow.nodes.examples.blend_models
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``ml.blend_models`` — weighted voting blend of two or more fitted models (ADR 0016).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Cardinality, Direction
from emergentflow.ir.node import Node
from emergentflow.ml import blend_models

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class BlendModels(NodeDefinition):
    """Blend two or more fitted models into a weighted voting ensemble, refit on data."""

    type = "ml.blend_models"
    version = 1
    family = "ml"
    label = "Blend Models"
    category = "Machine Learning"
    description = "Blend two or more fitted models into a weighted voting ensemble, refit on data."

    ports = [
        PortSpec(
            name="models",
            label="Models",
            direction=Direction.IN,
            data_type="Model",
            cardinality=Cardinality.MANY,
            help="Two or more fitted models to blend.",
        ),
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="Data (features + target) to refit the voting ensemble on.",
        ),
        PortSpec(
            name="model",
            direction=Direction.OUT,
            data_type="Model",
            help="The fitted voting ensemble model.",
        ),
    ]
    params = [
        ParamSpec(
            name="task",
            type_token="str",
            required=True,
            label="Task",
            help="Supervised task type.",
            hints=ValidationHints(choices=["classification", "regression"], widget="select"),
        ),
        ParamSpec(
            name="target",
            type_token="str",
            required=True,
            label="Target column",
            help="Column to predict.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="features",
            type_token="list[str]",
            default=None,
            label="Feature columns",
            help="Columns to use as features; empty/unset uses every other column.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="voting",
            type_token="str",
            default="soft",
            label="Voting",
            help="Voting scheme: soft or hard.",
            hints=ValidationHints(choices=["soft", "hard"], widget="select"),
        ),
    ]

    def _args(self, node: Node) -> tuple[str, str, list[str] | None, str]:
        values = {p.name: p.value for p in node.params}
        task = values.get("task")
        target = values.get("target")
        features = values.get("features")
        voting = values.get("voting", "soft")
        return (
            cast(str, task),
            cast(str, target),
            cast("list[str] | None", features),
            cast(str, voting),
        )

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        task, target, features, voting = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('model')} = ef.ml.blend_models("
                f"{ctx.in_var('models')}, {ctx.in_var('frame')}, task={task!r}, target={target!r}, "
                f"features={features!r}, voting={voting!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        task, target, features, voting = self._args(node)
        return {
            "model": blend_models(
                inputs["models"],
                inputs["frame"],
                task=task,
                target=target,
                features=features,
                voting=voting,
            )
        }
