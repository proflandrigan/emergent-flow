"""
emergentflow.nodes.examples.recommend_temporal_split
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``recommend.temporal_split`` — a *split* node (1 in, 2 out) (Epic 15, Story 15).

Splits a tidy events/ratings DataFrame into (train, test) InteractionMatrix pairs by per-user
recency, mirroring ``ml.train_test_split``'s two-OUT-port pattern (Epic 1, Story 9): ``execute``
calls ``emergentflow.recommend.temporal_split`` directly and the code emitted by ``codegen``
calls the same wrapper via the ``ef.`` alias, so the two paths are equivalent by construction
(ADR 0002). Codegen emits a single tuple-unpack assignment rather than two separate statements.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.recommend import temporal_split

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class RecommendTemporalSplit(NodeDefinition):
    """Split events into (train, test) InteractionMatrix pairs by per-user recency."""

    type = "recommend.temporal_split"
    version = 1
    family = "recommend"
    label = "Temporal Split"
    category = "Recommenders"
    description = "Split events into train/test InteractionMatrix pairs by per-user recency."

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The tidy events/ratings DataFrame to split.",
        ),
        PortSpec(
            name="train",
            direction=Direction.OUT,
            data_type="InteractionMatrix",
            help="Each user's earlier interactions.",
        ),
        PortSpec(
            name="test",
            direction=Direction.OUT,
            data_type="InteractionMatrix",
            help="Each user's held-out, most recent interactions.",
        ),
    ]
    params = [
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
            default=None,
            label="Value column",
            help="Column with interaction value; unset means implicit (every row counts as 1).",
        ),
        ParamSpec(
            name="timestamp_col",
            type_token="str",
            required=True,
            label="Timestamp column",
            help="Column used to order each user's interactions by recency.",
        ),
        ParamSpec(
            name="test_ratio",
            type_token="float",
            default=0.2,
            label="Test ratio",
            help="Fraction of each user's most recent interactions held out for test.",
        ),
        ParamSpec(
            name="implicit",
            type_token="bool",
            default=True,
            label="Implicit feedback",
            help="Whether values represent implicit feedback rather than explicit ratings.",
        ),
    ]

    def _args(self, node: Node) -> tuple[str, str, str | None, str, float, bool]:
        values = {p.name: p.value for p in node.params}
        return (
            cast(str, values.get("user_col")),
            cast(str, values.get("item_col")),
            cast("str | None", values.get("value_col")),
            cast(str, values.get("timestamp_col")),
            cast(float, values.get("test_ratio", 0.2)),
            cast(bool, values.get("implicit", True)),
        )

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        user_col, item_col, value_col, timestamp_col, test_ratio, implicit = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('train')}, {ctx.out_var('test')} = ef.recommend.temporal_split("
                f"{ctx.in_var('frame')}, user_col={user_col!r}, item_col={item_col!r}, "
                f"value_col={value_col!r}, timestamp_col={timestamp_col!r}, "
                f"test_ratio={test_ratio!r}, implicit={implicit!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        user_col, item_col, value_col, timestamp_col, test_ratio, implicit = self._args(node)
        train, test = temporal_split(
            inputs["frame"],
            user_col=user_col,
            item_col=item_col,
            value_col=value_col,
            timestamp_col=timestamp_col,
            test_ratio=test_ratio,
            implicit=implicit,
        )
        return {"train": train, "test": test}
