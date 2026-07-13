"""
emergentflow.nodes.examples.train_regressor
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``ml.train_regressor`` — a *transform* node (1 in, 1 out).

Real, scikit-learn-backed linear-regression fitter (Epic 1, Story 10).
``execute`` calls ``emergentflow.ml.train_regressor`` directly and the code
emitted by ``codegen`` calls the same wrapper via the ``ef.`` alias, so the
two paths are equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.ml import train_regressor

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class TrainRegressor(NodeDefinition):
    """Fit a linear-regression model and return a FittedModel."""

    type = "ml.train_regressor"
    version = 1
    family = "ml"
    label = "Train Regressor"
    category = "Machine Learning"
    description = "Fit a linear-regression model."

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame containing features and the target column.",
        ),
        PortSpec(
            name="model",
            direction=Direction.OUT,
            data_type="Model",
            help="The fitted regression model.",
        ),
    ]
    params = [
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
    ]

    def _args(self, node: Node) -> tuple[str, list[str] | None]:
        values = {p.name: p.value for p in node.params}
        target = values.get("target")
        features = values.get("features")
        return (
            cast(str, target),
            cast("list[str] | None", features),
        )

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        target, features = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('model')} = ef.ml.train_regressor({ctx.in_var('frame')}, "
                f"target={target!r}, features={features!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        target, features = self._args(node)
        return {
            "model": train_regressor(
                inputs["frame"],
                target=target,
                features=features,
            )
        }
