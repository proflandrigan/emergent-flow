"""
emergentflow.nodes.examples.recommend_hybrid_weighted
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``recommend.hybrid_weighted`` — blend two or more fitted recommenders'
recommendations into one ranked list (Epic 15, Story 9).

A composition layer, not a new algorithm family: it takes multiple already-fitted
``Recommender`` inputs (the first node type in this codebase with a ``Cardinality.MANY`` IN
port -- see ``emergentflow.codegen.context``/``executor`` for the underlying fan-in support) and
emits a single ``RecommendationResult``. ``execute`` calls
``emergentflow.recommend.hybrid_weighted`` directly and the code emitted by ``codegen`` calls
the same wrapper via the ``ef.`` alias, so the two paths are equivalent by construction
(ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Cardinality, Direction
from emergentflow.ir.node import Node
from emergentflow.recommend import hybrid_weighted

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class HybridWeighted(NodeDefinition):
    """Blend two or more fitted recommenders' recommendations into one ranked list."""

    type = "recommend.hybrid_weighted"
    version = 1
    family = "recommend"
    label = "Hybrid (Weighted)"
    category = "Recommenders"
    description = "Blend two or more fitted recommenders' recommendations by weighted score."

    ports = [
        PortSpec(
            name="recommenders",
            label="Recommenders",
            direction=Direction.IN,
            data_type="Recommender",
            cardinality=Cardinality.MANY,
            help="Two or more already-fitted recommenders to blend.",
        ),
        PortSpec(
            name="result",
            direction=Direction.OUT,
            data_type="RecommendationResult",
            help="The blended top-N recommendations per user.",
        ),
    ]
    params = [
        ParamSpec(
            name="weights",
            type_token="list[float]",
            default=None,
            label="Weights",
            help="One weight per recommender, same order as the connected inputs. "
            "Unset means equal weighting.",
        ),
        ParamSpec(
            name="n",
            type_token="int",
            default=10,
            label="Recommendations per user",
            help="Number of blended recommendations to generate per user.",
        ),
        ParamSpec(
            name="blend_strategy",
            type_token="str",
            default="weighted_sum",
            label="Blend strategy",
            help="How to combine the input recommenders' scores.",
            hints=ValidationHints(
                choices=["weighted_sum", "rank_fusion", "cascade"],
                widget="select",
            ),
        ),
        ParamSpec(
            name="user_ids",
            type_token="list[str]",
            default=None,
            label="User IDs",
            help="Users to recommend for; empty/unset means every user seen across inputs.",
        ),
        ParamSpec(
            name="exclude_known",
            type_token="bool",
            default=True,
            label="Exclude known items",
            help="Drop items already present in each recommender's training interactions.",
        ),
    ]

    def _args(self, node: Node) -> tuple[Any, int, str, Any, bool]:
        values = {p.name: p.value for p in node.params}
        weights = values.get("weights")
        n = cast(int, values.get("n", 10))
        blend_strategy = cast(str, values.get("blend_strategy", "weighted_sum"))
        user_ids = values.get("user_ids")
        exclude_known = cast(bool, values.get("exclude_known", True))
        return weights, n, blend_strategy, user_ids, exclude_known

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        weights, n, blend_strategy, user_ids, exclude_known = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('result')} = ef.recommend.hybrid_weighted("
                f"{ctx.in_var('recommenders')}, weights={weights!r}, n={n!r}, "
                f"blend_strategy={blend_strategy!r}, user_ids={user_ids!r}, "
                f"exclude_known={exclude_known!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        weights, n, blend_strategy, user_ids, exclude_known = self._args(node)
        return {
            "result": hybrid_weighted(
                inputs["recommenders"],
                weights=weights,
                n=n,
                blend_strategy=blend_strategy,
                user_ids=user_ids,
                exclude_known=exclude_known,
            )
        }
