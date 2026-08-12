"""
emergentflow.nodes.examples.stack_models
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``ml.stack_models`` — stacking ensemble of two or more fitted models
under a curated meta-learner (ADR 0016).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Cardinality, Direction
from emergentflow.ir.node import Node
from emergentflow.ml import stack_models

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class StackModels(NodeDefinition):
    """Stack two or more fitted models under a curated meta-learner, refit on data."""

    type = "ml.stack_models"
    version = 1
    family = "ml"
    label = "Stack Models"
    category = "Machine Learning"
    description = "Stack two or more fitted models under a curated meta-learner, refit on data."

    ports = [
        PortSpec(
            name="models",
            label="Models",
            direction=Direction.IN,
            data_type="Model",
            cardinality=Cardinality.MANY,
            help="Two or more fitted base models.",
        ),
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="Data (features + target) to refit the stack on.",
        ),
        PortSpec(
            name="model",
            direction=Direction.OUT,
            data_type="Model",
            help="The fitted stacking ensemble model.",
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
            name="final_estimator",
            type_token="str",
            default="LogisticRegression",
            label="Meta-learner",
            help="Curated meta-learner key.",
        ),
        ParamSpec(
            name="cv",
            type_token="int",
            default=5,
            label="CV folds",
            help="Number of cross-validation folds for the meta-learner.",
        ),
    ]

    def _args(self, node: Node) -> tuple[str, str, list[str] | None, str, int]:
        values = {p.name: p.value for p in node.params}
        task = values.get("task")
        target = values.get("target")
        features = values.get("features")
        final_estimator = values.get("final_estimator", "LogisticRegression")
        cv = values.get("cv", 5)
        return (
            cast(str, task),
            cast(str, target),
            cast("list[str] | None", features),
            cast(str, final_estimator),
            cast(int, cv),
        )

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        task, target, features, final_estimator, cv = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('model')} = ef.ml.stack_models("
                f"{ctx.in_var('models')}, {ctx.in_var('frame')}, task={task!r}, target={target!r}, "
                f"features={features!r}, final_estimator={final_estimator!r}, cv={cv!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        task, target, features, final_estimator, cv = self._args(node)
        return {
            "model": stack_models(
                inputs["models"],
                inputs["frame"],
                task=task,
                target=target,
                features=features,
                final_estimator=final_estimator,
                cv=cv,
            )
        }
