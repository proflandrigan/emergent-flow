"""
emergentflow.nodes.examples.recommend_encode_categorical_features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``recommend.encode_categorical_features`` — encode categorical columns in a
user- or item-feature frame while preserving its id column (Epic 15, Story 11).

``execute`` calls ``emergentflow.recommend.encode_categorical_features`` directly and the code
emitted by ``codegen`` calls the same wrapper via the ``ef.`` alias, so the two paths are
equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.ir.params import ParamValue
from emergentflow.recommend import encode_categorical_features

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ColumnEffect, ColumnEffectKind, ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext

_ENCODE_STRATEGIES: list[str] = ["onehot", "ordinal"]


@register
class RecommendEncodeCategoricalFeatures(NodeDefinition):
    """Encode categorical columns in a feature frame while preserving its id column."""

    type = "recommend.encode_categorical_features"
    version = 1
    family = "recommend"
    label = "Encode Categorical Features"
    category = "Recommenders"
    description = (
        "Encode categorical columns in a user/item feature frame while preserving its id column. "
        "Produces numeric columns suitable for wiring into the two-tower seam."
    )

    column_effect = ColumnEffect(kind=ColumnEffectKind.ENCODE)

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The user- or item-feature DataFrame with categorical columns to encode.",
        ),
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="The input frame with categorical columns encoded as numeric columns.",
        ),
    ]
    params = [
        ParamSpec(
            name="columns",
            type_token="list[str]",
            required=True,
            label="Columns",
            help="Categorical columns to encode.",
        ),
        ParamSpec(
            name="id_col",
            type_token="str",
            required=True,
            label="ID column",
            help="Column identifying the user or item (preserved untouched).",
        ),
        ParamSpec(
            name="strategy",
            type_token="str",
            default="onehot",
            label="Strategy",
            help=(
                "Encoding strategy: onehot produces indicator columns; "
                "ordinal produces numeric labels."
            ),
            hints=ValidationHints(
                choices=cast("list[ParamValue]", _ENCODE_STRATEGIES),
                widget="select",
            ),
        ),
        ParamSpec(
            name="drop_first",
            type_token="bool",
            default=False,
            label="Drop first",
            help="Drop one level per input column (one-hot only) to avoid collinearity.",
        ),
    ]

    def _args(self, node: Node) -> tuple[list[str], str, str, bool]:
        values = {p.name: p.value for p in node.params}
        return (
            cast(list[str], values.get("columns")),
            cast(str, values.get("id_col")),
            cast(str, values.get("strategy", "onehot")),
            cast(bool, values.get("drop_first", False)),
        )

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        columns, id_col, strategy, drop_first = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('frame')} = ef.recommend.encode_categorical_features("
                f"{ctx.in_var('frame')}, columns={columns!r}, id_col={id_col!r}, "
                f"strategy={strategy!r}, drop_first={drop_first!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        columns, id_col, strategy, drop_first = self._args(node)
        return {
            "frame": encode_categorical_features(
                inputs["frame"],
                columns=columns,
                id_col=id_col,
                strategy=strategy,
                drop_first=drop_first,
            )
        }
