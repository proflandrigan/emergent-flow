"""
emergentflow.nodes.examples.recommend_weight_interactions_by_recency
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``recommend.weight_interactions_by_recency`` — weight event rows by recency
before building an interaction matrix (Epic 15).

``execute`` calls ``emergentflow.recommend.weight_interactions_by_recency`` directly and the code
emitted by ``codegen`` calls the same wrapper via the ``ef.`` alias, so the two paths are
equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.ir.params import ParamValue
from emergentflow.recommend import weight_interactions_by_recency

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ColumnEffect, ColumnEffectKind, ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext

_DECAY_CHOICES: list[str] = ["exponential"]


@register
class RecommendWeightInteractionsByRecency(NodeDefinition):
    """Weight event rows by recency (newer events get higher weight) for downstream interaction
    matrix preparation."""

    type = "recommend.weight_interactions_by_recency"
    version = 1
    family = "recommend"
    label = "Weight Interactions by Recency"
    category = "Recommenders"
    description = (
        "Weight event rows by recency: newer events get a higher weight value in the added column. "
        "Produces a value column suitable for prepare_interactions."
    )

    column_effect = ColumnEffect(kind=ColumnEffectKind.DERIVE)

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The events/ratings DataFrame with a timestamp column.",
        ),
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="The input frame with a recency-weighted value column added.",
        ),
    ]
    params = [
        ParamSpec(
            name="timestamp_col",
            type_token="str",
            required=True,
            label="Timestamp column",
            help="Column with event timestamps (used to compute recency).",
        ),
        ParamSpec(
            name="user_col",
            type_token="str",
            required=True,
            label="User column",
            help="Column identifying the user.",
        ),
        ParamSpec(
            name="item_col",
            type_token="str",
            required=True,
            label="Item column",
            help="Column identifying the item.",
        ),
        ParamSpec(
            name="value_col",
            type_token="str",
            default="weight",
            label="Value column name",
            help="Name of the added recency-weight column.",
        ),
        ParamSpec(
            name="decay",
            type_token="str",
            default="exponential",
            label="Decay function",
            help="The recency decay function to apply.",
            hints=ValidationHints(
                choices=cast("list[ParamValue]", _DECAY_CHOICES),
                widget="select",
            ),
        ),
        ParamSpec(
            name="half_life_days",
            type_token="float",
            default=30.0,
            label="Half-life (days)",
            help="Number of days after which an event's weight drops to 0.5.",
        ),
    ]

    def _args(self, node: Node) -> tuple[str, str, str, str, str, float]:
        values = {p.name: p.value for p in node.params}
        return (
            cast(str, values.get("timestamp_col")),
            cast(str, values.get("user_col")),
            cast(str, values.get("item_col")),
            cast(str, values.get("value_col", "weight")),
            cast(str, values.get("decay", "exponential")),
            cast(float, values.get("half_life_days", 30.0)),
        )

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        timestamp_col, user_col, item_col, value_col, decay, half_life_days = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('frame')} = ef.recommend.weight_interactions_by_recency("
                f"{ctx.in_var('frame')}, "
                f"timestamp_col={timestamp_col!r}, user_col={user_col!r}, "
                f"item_col={item_col!r}, value_col={value_col!r}, "
                f"decay={decay!r}, half_life_days={half_life_days!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        timestamp_col, user_col, item_col, value_col, decay, half_life_days = self._args(node)
        return {
            "frame": weight_interactions_by_recency(
                inputs["frame"],
                timestamp_col=timestamp_col,
                user_col=user_col,
                item_col=item_col,
                value_col=value_col,
                decay=decay,
                half_life_days=half_life_days,
            )
        }
