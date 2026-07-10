"""
emergentflow.nodes.examples.encode_categorical
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``transform.encode_categorical`` — dedicated categorical encoding node.

Fits a curated categorical encoder (OneHotEncoder, OrdinalEncoder, TargetEncoder) and
transforms the input frame, returning both a fitted Transformer and the transformed
DataFrame. A more discoverable front door to the encoding subset of ``ml.fit_transform``.
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

_ENCODER_KEYS: list[str] = [
    "OneHotEncoder",
    "OrdinalEncoder",
    "TargetEncoder",
]


@register
class EncodeCategorical(NodeDefinition):
    """Fit a categorical encoder and transform the input frame."""

    type = "transform.encode_categorical"
    version = 1
    family = "transform"
    label = "Encode Categorical"
    category = "Feature Transform"
    description = (
        "Encode categorical features using a curated sklearn encoder "
        "(OneHotEncoder, OrdinalEncoder, or TargetEncoder)."
    )

    ports = [
        PortSpec(
            name="frame",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame containing categorical features to encode.",
        ),
        PortSpec(
            name="transformer",
            direction=Direction.OUT,
            data_type="Transformer",
            help="The fitted encoder (reusable on new data via ml.transform).",
        ),
        PortSpec(
            name="result",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="The input frame with encoded feature columns appended.",
        ),
    ]
    params = [
        ParamSpec(
            name="estimator",
            type_token="str",
            required=True,
            label="Encoder",
            help="Which categorical encoding algorithm to use.",
            hints=ValidationHints(
                choices=cast("list[ParamValue]", _ENCODER_KEYS),
                widget="select",
            ),
        ),
        ParamSpec(
            name="target",
            type_token="str",
            default=None,
            label="Target column",
            help="Required for TargetEncoder (supervised); leave unset for "
            "OneHotEncoder/OrdinalEncoder.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="features",
            type_token="list[str]",
            default=None,
            label="Feature columns",
            help="Categorical columns to encode; empty/unset uses all columns "
            "(excluding target, if given).",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="params",
            type_token="dict[str, any]",
            default={},
            label="Encoder params",
            help="Constructor kwargs for the chosen encoder (allow-listed per encoder).",
        ),
    ]

    def _args(self, node: Node) -> tuple[str, str | None, list[str] | None, dict[str, Any]]:
        values = {p.name: p.value for p in node.params}
        estimator = values.get("estimator")
        target = values.get("target")
        features = values.get("features")
        params = values.get("params") or {}
        return (
            cast(str, estimator),
            cast("str | None", target),
            cast("list[str] | None", features),
            cast("dict[str, Any]", params),
        )

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        estimator, target, features, params = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('transformer')}, {ctx.out_var('result')} = ef.ml.fit_transform("
                f"{ctx.in_var('frame')}, estimator={estimator!r}, target={target!r}, "
                f"features={features!r}, params={params!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        estimator, target, features, params = self._args(node)
        transformer, result = fit_transform(
            inputs["frame"],
            estimator=estimator,
            target=target,
            features=features,
            params=params,
        )
        return {"transformer": transformer, "result": result}
