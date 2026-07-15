"""
emergentflow.nodes.examples.recommend_hybrid_switching
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``recommend.hybrid_switching`` — route each user to one of two fitted
recommenders by their known-interaction count, addressing cold-start directly (Epic 15,
Story 9).

A composition layer, not a new algorithm family: it takes exactly two already-fitted
``Recommender`` inputs (a ``Cardinality.MANY`` IN port, same mechanism as
``recommend.hybrid_weighted``) plus the ``InteractionMatrix`` used to look up each user's
known-interaction count, and emits a single ``RecommendationResult``. ``execute`` calls
``emergentflow.recommend.hybrid_switching`` directly and the code emitted by ``codegen`` calls
the same wrapper via the ``ef.`` alias, so the two paths are equivalent by construction
(ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Cardinality, Direction
from emergentflow.ir.node import Node
from emergentflow.recommend import hybrid_switching

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class HybridSwitching(NodeDefinition):
    """Route each user to one of two fitted recommenders by their known-interaction count."""

    type = "recommend.hybrid_switching"
    version = 1
    family = "recommend"
    label = "Hybrid (Switching)"
    category = "Recommenders"
    description = (
        "Route cold-start users to one recommender and warm users to another, "
        "based on known-interaction count."
    )

    ports = [
        PortSpec(
            name="recommenders",
            label="Recommenders",
            direction=Direction.IN,
            data_type="Recommender",
            cardinality=Cardinality.MANY,
            help="Exactly two fitted recommenders: [cold_start_recommender, warm_recommender].",
        ),
        PortSpec(
            name="interactions",
            label="Interactions",
            direction=Direction.IN,
            data_type="InteractionMatrix",
            help="Used only to look up each user's known-interaction count.",
        ),
        PortSpec(
            name="result",
            direction=Direction.OUT,
            data_type="RecommendationResult",
            help="The routed top-N recommendations per user.",
        ),
    ]
    params = [
        ParamSpec(
            name="cold_start_threshold",
            type_token="int",
            required=True,
            label="Cold-start threshold",
            help="Users with fewer known interactions than this go to the first "
            "recommender; users with this many or more go to the second.",
        ),
        ParamSpec(
            name="n",
            type_token="int",
            default=10,
            label="Recommendations per user",
            help="Number of recommendations to generate per user.",
        ),
        ParamSpec(
            name="user_ids",
            type_token="list[str]",
            default=None,
            label="User IDs",
            help="Users to recommend for; empty/unset means every user in the interactions.",
        ),
        ParamSpec(
            name="exclude_known",
            type_token="bool",
            default=True,
            label="Exclude known items",
            help="Drop items already present in each user's training interactions.",
        ),
    ]

    def _args(self, node: Node) -> tuple[int, int, Any, bool]:
        values = {p.name: p.value for p in node.params}
        cold_start_threshold = cast(int, values.get("cold_start_threshold"))
        n = cast(int, values.get("n", 10))
        user_ids = values.get("user_ids")
        exclude_known = cast(bool, values.get("exclude_known", True))
        return cold_start_threshold, n, user_ids, exclude_known

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        cold_start_threshold, n, user_ids, exclude_known = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('result')} = ef.recommend.hybrid_switching("
                f"{ctx.in_var('recommenders')}, {ctx.in_var('interactions')}, "
                f"cold_start_threshold={cold_start_threshold!r}, n={n!r}, "
                f"user_ids={user_ids!r}, exclude_known={exclude_known!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        cold_start_threshold, n, user_ids, exclude_known = self._args(node)
        return {
            "result": hybrid_switching(
                inputs["recommenders"],
                inputs["interactions"],
                cold_start_threshold=cold_start_threshold,
                n=n,
                user_ids=user_ids,
                exclude_known=exclude_known,
            )
        }
