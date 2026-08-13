"""
emergentflow.nodes.examples.calibrate_model
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``ml.calibrate_model`` — probability-calibrate a fitted classifier
and refit it on data (ADR 0016).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.ml import calibrate_model

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class CalibrateModel(NodeDefinition):
    """Probability-calibrate a fitted classifier and refit on data."""

    type = "ml.calibrate_model"
    version = 1
    family = "ml"
    label = "Calibrate Model"
    category = "Machine Learning"
    description = "Probability-calibrate a fitted classifier and refit on data."

    ports = [
        PortSpec(
            name="model",
            direction=Direction.IN,
            data_type="Model",
            help="The fitted model to calibrate.",
        ),
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="Data (features + target) to refit the calibrated model on.",
        ),
        PortSpec(
            name="model",
            direction=Direction.OUT,
            data_type="Model",
            help="The fitted probability-calibrated model.",
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
        ParamSpec(
            name="method",
            type_token="str",
            default="sigmoid",
            label="Method",
            help="Calibration method: sigmoid (Platt) or isotonic.",
            hints=ValidationHints(choices=["sigmoid", "isotonic"], widget="select"),
        ),
        ParamSpec(
            name="cv",
            type_token="int",
            default=5,
            label="Cross-validation folds",
            help="Number of cross-validation folds used for calibration.",
        ),
    ]

    def _args(self, node: Node) -> tuple[str, list[str] | None, str, int]:
        values = {p.name: p.value for p in node.params}
        target = values.get("target")
        features = values.get("features")
        method = values.get("method", "sigmoid")
        cv = values.get("cv", 5)
        return (
            cast(str, target),
            cast("list[str] | None", features),
            cast(str, method),
            cast(int, cv),
        )

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        target, features, method, cv = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('model')} = ef.ml.calibrate_model("
                f"{ctx.in_var('model')}, {ctx.in_var('frame')}, target={target!r}, "
                f"features={features!r}, method={method!r}, cv={cv!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        target, features, method, cv = self._args(node)
        return {
            "model": calibrate_model(
                inputs["model"],
                inputs["frame"],
                target=target,
                features=features,
                method=method,
                cv=cv,
            )
        }
