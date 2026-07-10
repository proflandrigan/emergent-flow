"""
emergentflow.nodes.examples.scale_features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``transform.scale_features`` — dedicated scaling transformer node.

Fits a curated scaling transformer (StandardScaler, MinMaxScaler, RobustScaler,
MaxAbsScaler, Normalizer, PowerTransformer) and transforms the input frame,
returning both a fitted Transformer and the transformed DataFrame. A more
discoverable front door to the scaling subset of ``ml.fit_transform``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.ir.params import ParamValue
from emergentflow.ml import fit_transform

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext

_SCALER_KEYS: list[str] = [
    "MaxAbsScaler",
    "MinMaxScaler",
    "Normalizer",
    "PowerTransformer",
    "RobustScaler",
    "StandardScaler",
]


@register
class ScaleFeatures(NodeDefinition):
    """Fit a scaling transformer and transform the input frame."""

    type = "transform.scale_features"
    version = 1
    family = "transform"
    label = "Scale Features"
    category = "Feature Transform"
    description = (
        "Scale numeric features using a curated sklearn scaler "
        "(StandardScaler, MinMaxScaler, RobustScaler, MaxAbsScaler, "
        "Normalizer, or PowerTransformer)."
    )

    ports = [
        PortSpec(
            name="frame",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame containing features to scale.",
        ),
        PortSpec(
            name="transformer",
            direction=Direction.OUT,
            data_type="Transformer",
            help="The fitted scaler (reusable on new data via ml.transform).",
        ),
        PortSpec(
            name="result",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="The input frame with scaled feature columns appended.",
        ),
    ]
    params = [
        ParamSpec(
            name="estimator",
            type_token="str",
            required=True,
            label="Scaler",
            help="Which scaling algorithm to use.",
            hints=ValidationHints(
                choices=cast("list[ParamValue]", _SCALER_KEYS),
                widget="select",
            ),
        ),
        ParamSpec(
            name="features",
            type_token="list[str]",
            default=None,
            label="Feature columns",
            help="Columns to scale; empty/unset uses all numeric columns.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="params",
            type_token="dict[str, any]",
            default={},
            label="Scaler params",
            help="Constructor kwargs for the chosen scaler (allow-listed per scaler).",
        ),
    ]

    def _args(self, node: Node) -> tuple[str, list[str] | None, dict[str, Any]]:
        values = {p.name: p.value for p in node.params}
        estimator = values.get("estimator")
        features = values.get("features")
        params = values.get("params") or {}
        return (
            cast(str, estimator),
            cast("list[str] | None", features),
            cast("dict[str, Any]", params),
        )

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        estimator, features, params = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('transformer')}, {ctx.out_var('result')} = ef.ml.fit_transform("
                f"{ctx.in_var('frame')}, estimator={estimator!r}, target=None, "
                f"features={features!r}, params={params!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        estimator, features, params = self._args(node)
        transformer, result = fit_transform(
            inputs["frame"],
            estimator=estimator,
            target=None,
            features=features,
            params=params,
        )
        return {"transformer": transformer, "result": result}
