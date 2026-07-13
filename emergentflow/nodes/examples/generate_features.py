"""
emergentflow.nodes.examples.generate_features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``transform.generate_features`` — dedicated feature generation node.

Fits a curated feature generation transformer (PolynomialFeatures) and transforms the
input frame, returning both a fitted Transformer and the transformed DataFrame. A more
discoverable front door to the feature generation subset of ``ml.fit_transform``.
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

_GENERATOR_KEYS: list[str] = [
    "PolynomialFeatures",
]


@register
class GenerateFeatures(NodeDefinition):
    """Fit a feature generation transformer and transform the input frame."""

    type = "transform.generate_features"
    version = 1
    family = "transform"
    label = "Generate Features"
    category = "Feature Transform"
    description = (
        "Generate new features from existing ones using a curated sklearn "
        "feature generator (PolynomialFeatures)."
    )

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame containing features to generate from.",
        ),
        PortSpec(
            name="transformer",
            direction=Direction.OUT,
            data_type="Transformer",
            help="The fitted generator (reusable on new data via ml.transform).",
        ),
        PortSpec(
            name="result",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="The input frame with generated feature columns appended.",
        ),
    ]
    params = [
        ParamSpec(
            name="estimator",
            type_token="str",
            required=True,
            label="Generator",
            help="Which feature generation algorithm to use.",
            hints=ValidationHints(
                choices=cast("list[ParamValue]", _GENERATOR_KEYS),
                widget="select",
            ),
        ),
        ParamSpec(
            name="features",
            type_token="list[str]",
            default=None,
            label="Feature columns",
            help="Columns to generate features from; empty/unset uses all numeric columns.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="params",
            type_token="dict[str, any]",
            default={},
            label="Generator params",
            help="Constructor kwargs for the chosen generator (allow-listed per generator).",
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
