"""
emergentflow.nodes.examples.recommend_fit_two_tower
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``recommend.fit_two_tower`` — the dedicated two-tower fit node (Epic 15,
Story 11). A separate node from the generic ``recommend.fit`` because the shared ``Fitter``
type only carries one optional DataFrame (``item_features``), but two-tower needs BOTH item-
and user-side feature DataFrames. ``execute`` calls ``emergentflow.recommend.fit_two_tower``
directly and the code emitted by ``codegen`` calls the same wrapper via the ``ef.`` alias, so
the two paths are equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.recommend import fit_two_tower

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class RecommendFitTwoTower(NodeDefinition):
    """Fit a two-tower retrieval model, optionally consuming item-side and/or user-side
    feature DataFrames."""

    type = "recommend.fit_two_tower"
    version = 1
    family = "recommend"
    label = "Fit Two-Tower Recommender"
    category = "Recommenders"
    description = (
        "Fit a two-tower retrieval model, optionally consuming item-side and/or "
        "user-side feature DataFrames."
    )

    ports = [
        PortSpec(
            name="interactions",
            label="Interactions",
            direction=Direction.IN,
            data_type="InteractionMatrix",
            help="The prepared user-item interaction matrix.",
        ),
        PortSpec(
            name="item_features",
            label="Item Features",
            direction=Direction.IN,
            data_type="DataFrame",
            required=False,
            help="Optional item-side features for the item tower.",
        ),
        PortSpec(
            name="user_features",
            label="User Features",
            direction=Direction.IN,
            data_type="DataFrame",
            required=False,
            help="Optional user-side features for the user tower.",
        ),
        PortSpec(
            name="recommender",
            direction=Direction.OUT,
            data_type="Recommender",
            help="The fitted two-tower recommender model.",
        ),
    ]
    params = [
        ParamSpec(
            name="params",
            type_token="dict[str, any]",
            default={},
            label="Algorithm params",
            help="Keyword arguments for the two-tower model.",
        ),
    ]

    def _args(self, node: Node) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        return cast("dict[str, Any]", values.get("params") or {})

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        params = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('recommender')} = ef.recommend.fit_two_tower("
                f"{ctx.in_var('interactions')}, "
                f"item_features={ctx.in_var('item_features')}, "
                f"user_features={ctx.in_var('user_features')}, "
                f"params={params!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        params = self._args(node)
        return {
            "recommender": fit_two_tower(
                inputs["interactions"],
                item_features=inputs.get("item_features"),
                user_features=inputs.get("user_features"),
                params=params,
            )
        }
