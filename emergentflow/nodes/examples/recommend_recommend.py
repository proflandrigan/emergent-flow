"""
emergentflow.nodes.examples.recommend_recommend
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``recommend.recommend`` — generate top-N recommendations from a fitted
recommender (Epic 15).

Given a fitted ``Recommender``, generate top-N item recommendations for each user.
``execute`` calls ``emergentflow.recommend.recommend`` directly and the code emitted by
``codegen`` calls the same wrapper via the ``ef.`` alias, so the two paths are equivalent by
construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.recommend import recommend

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class Recommend(NodeDefinition):
    """Generate top-N recommendations from a fitted recommender."""

    type = "recommend.recommend"
    version = 1
    family = "recommend"
    label = "Recommend"
    category = "Recommenders"
    description = "Generate top-N recommendations from a fitted recommender."

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
            help="Top-N recommendations per user.",
        ),
    ]
    params = [
        ParamSpec(
            name="user_ids",
            type_token="list[str]",
            default=None,
            label="User IDs",
            help="Users to recommend for; empty/unset means every user the recommender was fit on.",
        ),
        ParamSpec(
            name="n",
            type_token="int",
            default=10,
            label="Recommendations per user",
            help="Number of recommendations to generate per user.",
        ),
        ParamSpec(
            name="exclude_known",
            type_token="bool",
            default=True,
            label="Exclude known items",
            help="Drop items already present in the user's training interactions.",
        ),
    ]

    def _args(self, node: Node) -> tuple[Any, int, bool]:
        values = {p.name: p.value for p in node.params}
        user_ids = values.get("user_ids")
        n = cast(int, values.get("n", 10))
        exclude_known = cast(bool, values.get("exclude_known", True))
        return user_ids, n, exclude_known

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        user_ids, n, exclude_known = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('result')} = ef.recommend.recommend("
                f"{ctx.in_var('recommender')}, user_ids={user_ids!r}, "
                f"n={n!r}, exclude_known={exclude_known!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        user_ids, n, exclude_known = self._args(node)
        return {
            "result": recommend(
                inputs["recommender"],
                user_ids=user_ids,
                n=n,
                exclude_known=exclude_known,
            )
        }
