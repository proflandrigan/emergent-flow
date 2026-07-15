"""
emergentflow.nodes.examples.recommend_similar_items
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``recommend.similar_items`` — find similar items from a fitted recommender
(Epic 15).

Given a fitted ``Recommender`` that supports item-item similarity, return the N most similar
items to each given item. ``execute`` calls ``emergentflow.recommend.similar_items`` directly
and the code emitted by ``codegen`` calls the same wrapper via the ``ef.`` alias, so the two
paths are equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.recommend import similar_items

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class SimilarItems(NodeDefinition):
    """Find similar items from a fitted recommender."""

    type = "recommend.similar_items"
    version = 1
    family = "recommend"
    label = "Similar Items"
    category = "Recommenders"
    description = "Find the N most similar items to each given item."

    ports = [
        PortSpec(
            name="recommender",
            direction=Direction.IN,
            data_type="Recommender",
            help="The fitted recommender model.",
        ),
        PortSpec(
            name="result",
            direction=Direction.OUT,
            data_type="RecommendationResult",
            help="Similar items per query item.",
        ),
    ]
    params = [
        ParamSpec(
            name="item_ids",
            type_token="list[str]",
            required=True,
            label="Item IDs",
            help="Items to find similar items for.",
        ),
        ParamSpec(
            name="n",
            type_token="int",
            default=10,
            label="Similar items per item",
            help="Number of similar items to return per query item.",
        ),
    ]

    def _args(self, node: Node) -> tuple[list[str], int]:
        values = {p.name: p.value for p in node.params}
        item_ids = cast("list[str]", values.get("item_ids"))
        n = cast(int, values.get("n", 10))
        return item_ids, n

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        item_ids, n = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('result')} = ef.recommend.similar_items("
                f"{ctx.in_var('recommender')}, item_ids={item_ids!r}, n={n!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        item_ids, n = self._args(node)
        return {
            "result": similar_items(
                inputs["recommender"],
                item_ids=item_ids,
                n=n,
            )
        }
