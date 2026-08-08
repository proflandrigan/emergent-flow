"""
emergentflow.nodes.examples.discretize
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``transform.discretize`` — dedicated discretization transformer node.

Fits a curated discretization transformer (KBinsDiscretizer, Binarizer) and transforms the
input frame, returning both a fitted Transformer and the transformed DataFrame. A more
discoverable front door to the discretization subset of ``ml.fit_transform``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.ir.params import ParamValue
from emergentflow.ml import fit_transform

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ColumnEffect, ColumnEffectKind, ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext

_DISCRETIZER_KEYS: list[str] = [
    "Binarizer",
    "KBinsDiscretizer",
]


@register
class Discretize(NodeDefinition):
    """Fit a discretization transformer and transform the input frame."""

    type = "transform.discretize"
    version = 1
    family = "transform"
    label = "Discretize"
    category = "Feature Transform"
    description = (
        "Discretize continuous features using a curated sklearn discretizer "
        "(KBinsDiscretizer or Binarizer)."
    )

    column_effect = ColumnEffect(kind=ColumnEffectKind.DERIVE)

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame containing continuous features to discretize.",
        ),
        PortSpec(
            name="transformer",
            direction=Direction.OUT,
            data_type="Transformer",
            help="The fitted discretizer (reusable on new data via ml.transform).",
        ),
        PortSpec(
            name="result",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="The input frame with discretized feature columns appended.",
        ),
    ]
    params = [
        ParamSpec(
            name="estimator",
            type_token="str",
            required=True,
            label="Discretizer",
            help="Which discretization algorithm to use.",
            hints=ValidationHints(
                choices=cast("list[ParamValue]", _DISCRETIZER_KEYS),
                widget="select",
            ),
        ),
        ParamSpec(
            name="features",
            type_token="list[str]",
            default=None,
            label="Feature columns",
            help="Columns to discretize; empty/unset uses all numeric columns.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="params",
            type_token="dict[str, any]",
            default={},
            label="Discretizer params",
            help="Constructor kwargs for the chosen discretizer (allow-listed per discretizer).",
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
