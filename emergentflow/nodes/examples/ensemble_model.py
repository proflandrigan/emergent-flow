"""
emergentflow.nodes.examples.ensemble_model
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``ml.ensemble_model`` — wrap a fitted estimator in a bagging/boosting
ensemble and refit it on data (ADR 0016).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.ml import ensemble_model

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class EnsembleModel(NodeDefinition):
    """Wrap a fitted estimator in a bagging/boosting ensemble and refit on data."""

    type = "ml.ensemble_model"
    version = 1
    family = "ml"
    label = "Ensemble Model"
    category = "Machine Learning"
    description = "Wrap a fitted estimator in a bagging/boosting ensemble and refit on data."

    ports = [
        PortSpec(
            name="model",
            direction=Direction.IN,
            data_type="Model",
            help="The fitted model to wrap in an ensemble.",
        ),
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="Data (features + target) to refit the ensemble on.",
        ),
        PortSpec(
            name="model",
            direction=Direction.OUT,
            data_type="Model",
            help="The fitted bagging/boosting ensemble model.",
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
            name="method",
            type_token="str",
            default="bagging",
            label="Method",
            help="Ensemble method: bagging or boosting.",
            hints=ValidationHints(choices=["bagging", "boosting"], widget="select"),
        ),
        ParamSpec(
            name="n_estimators",
            type_token="int",
            default=10,
            label="Number of estimators",
            help="Number of base estimators in the ensemble.",
        ),
    ]

    def _args(self, node: Node) -> tuple[str, str, list[str] | None, str, int]:
        values = {p.name: p.value for p in node.params}
        task = values.get("task")
        target = values.get("target")
        features = values.get("features")
        method = values.get("method", "bagging")
        n_estimators = values.get("n_estimators", 10)
        return (
            cast(str, task),
            cast(str, target),
            cast("list[str] | None", features),
            cast(str, method),
            cast(int, n_estimators),
        )

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        task, target, features, method, n_estimators = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('model')} = ef.ml.ensemble_model("
                f"{ctx.in_var('model')}, {ctx.in_var('frame')}, task={task!r}, "
                f"target={target!r}, features={features!r}, method={method!r}, "
                f"n_estimators={n_estimators!r}, random_state=0)"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        task, target, features, method, n_estimators = self._args(node)
        return {
            "model": ensemble_model(
                inputs["model"],
                inputs["frame"],
                task=task,
                target=target,
                features=features,
                method=method,
                n_estimators=n_estimators,
            )
        }
