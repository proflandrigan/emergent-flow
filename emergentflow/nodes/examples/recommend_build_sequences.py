"""
emergentflow.nodes.examples.recommend_build_sequences
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``recommend.build_sequences`` — build a SequenceDataset from an event
DataFrame (Epic 15, sequential recommenders).

``execute`` calls ``emergentflow.recommend.build_sequences`` directly and the code
emitted by ``codegen`` calls the same wrapper via the ``ef.`` alias, so the two paths are
equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.recommend import build_sequences

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class RecommendBuildSequences(NodeDefinition):
    """Build a SequenceDataset from an event DataFrame for sequential recommenders."""

    type = "recommend.build_sequences"
    version = 1
    family = "recommend"
    label = "Build Sequences"
    category = "Recommenders"
    description = (
        "Build a SequenceDataset from an event DataFrame: ordered item-index sequences "
        "per session, used by sequential recommenders."
    )

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The events/ratings DataFrame to build sequences from.",
        ),
        PortSpec(
            name="sequences",
            direction=Direction.OUT,
            data_type="SequenceDataset",
            help="The built sequence dataset ready for fit_sequence.",
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
            name="session_col",
            type_token="str",
            default=None,
            label="Session column",
            help="Column identifying the session; None means each user is one session.",
        ),
        ParamSpec(
            name="timestamp_col",
            type_token="str",
            default=None,
            label="Timestamp column",
            help="Column used to order events within each session.",
        ),
        ParamSpec(
            name="max_seq_len",
            type_token="int",
            default=50,
            label="Max sequence length",
            help="Maximum number of items per sequence (older items truncated).",
        ),
        ParamSpec(
            name="min_seq_len",
            type_token="int",
            default=2,
            label="Min sequence length",
            help="Sequences shorter than this are dropped.",
        ),
    ]

    def _args(self, node: Node) -> tuple[str, str, str | None, str | None, int, int]:
        values = {p.name: p.value for p in node.params}
        return (
            cast(str, values.get("user_col")),
            cast(str, values.get("item_col")),
            cast("str | None", values.get("session_col")),
            cast("str | None", values.get("timestamp_col")),
            cast(int, values.get("max_seq_len", 50)),
            cast(int, values.get("min_seq_len", 2)),
        )

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        user_col, item_col, session_col, timestamp_col, max_seq_len, min_seq_len = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('sequences')} = ef.recommend.build_sequences("
                f"{ctx.in_var('frame')}, "
                f"user_col={user_col!r}, item_col={item_col!r}, "
                f"session_col={session_col!r}, timestamp_col={timestamp_col!r}, "
                f"max_seq_len={max_seq_len!r}, min_seq_len={min_seq_len!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        user_col, item_col, session_col, timestamp_col, max_seq_len, min_seq_len = self._args(node)
        return {
            "sequences": build_sequences(
                inputs["frame"],
                user_col=user_col,
                item_col=item_col,
                session_col=session_col,
                timestamp_col=timestamp_col,
                max_seq_len=max_seq_len,
                min_seq_len=min_seq_len,
            )
        }
