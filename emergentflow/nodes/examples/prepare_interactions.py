"""
emergentflow.nodes.examples.prepare_interactions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``recommend.prepare_interactions`` — the single entry point for
validating and normalising raw events/ratings data into a deduplicated, sparse
InteractionMatrix (Epic 15, Story 3).

Both ``codegen`` and ``execute`` route through ``ef.recommend.prepare_interactions``,
which delegates to the shared ``_prepare_interactions`` validation gate, so ADR-0002
equivalence holds by construction.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.recommend import prepare_interactions

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class PrepareInteractions(NodeDefinition):
    """Normalise raw events/ratings into a deduplicated InteractionMatrix."""

    type = "recommend.prepare_interactions"
    version = 1
    family = "recommend"
    label = "Prepare Interactions"
    category = "Recommenders"
    description = (
        "Validate and deduplicate raw user-item interaction data into a sparse InteractionMatrix."
    )

    ports = [
        PortSpec(
            name="frame",
            label="Events",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame containing user, item, and optional value columns.",
        ),
        PortSpec(
            name="interactions",
            direction=Direction.OUT,
            data_type="InteractionMatrix",
            help="The validated, deduplicated sparse interaction matrix.",
        ),
    ]
    params = [
        ParamSpec(
            name="user_col",
            type_token="str",
            required=True,
            label="User column",
            help="Column identifying the user/entity.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="item_col",
            type_token="str",
            required=True,
            label="Item column",
            help="Column identifying the item/content.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="value_col",
            type_token="str",
            default=None,
            label="Value column",
            help="Column of interaction values (ratings, counts). None means implicit feedback.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="implicit",
            type_token="bool",
            default=True,
            label="Implicit feedback",
            help="True for implicit feedback (counts/binary); False for explicit ratings.",
        ),
        ParamSpec(
            name="agg",
            type_token="str",
            default="sum",
            label="Aggregation",
            help="How to aggregate duplicate (user, item) pairs.",
            hints=ValidationHints(
                choices=["sum", "mean", "max", "last"],
                widget="select",
            ),
        ),
        ParamSpec(
            name="min_user_interactions",
            type_token="int",
            default=0,
            label="Min user interactions",
            help="Minimum distinct items a user must have interacted with to keep.",
            hints=ValidationHints(widget="number"),
        ),
        ParamSpec(
            name="min_item_interactions",
            type_token="int",
            default=0,
            label="Min item interactions",
            help="Minimum distinct users who must have interacted with an item to keep it.",
            hints=ValidationHints(widget="number"),
        ),
        ParamSpec(
            name="cold_start_mode",
            type_token="str",
            default="warn-and-skip",
            label="Cold start mode",
            help="How to handle users/items below the minimum-interaction thresholds.",
            hints=ValidationHints(
                choices=["error", "warn-and-skip", "include"],
                widget="select",
            ),
        ),
    ]

    def _args(self, node: Node) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        user_col = values.get("user_col", "")
        item_col = values.get("item_col", "")
        value_col = values.get("value_col")
        if value_col in (None, ""):
            value_col = None
        implicit = values.get("implicit", True)
        agg = values.get("agg", "sum")
        min_user_interactions = values.get("min_user_interactions", 0)
        min_item_interactions = values.get("min_item_interactions", 0)
        cold_start_mode = values.get("cold_start_mode", "warn-and-skip")
        return {
            "user_col": user_col,
            "item_col": item_col,
            "value_col": value_col,
            "implicit": implicit,
            "agg": agg,
            "min_user_interactions": min_user_interactions,
            "min_item_interactions": min_item_interactions,
            "cold_start_mode": cold_start_mode,
        }

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        kwargs = self._args(node)
        kwargs_str = ", ".join(f"{k}={v!r}" for k, v in kwargs.items())
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('interactions')} = ef.recommend.prepare_interactions("
                f"{ctx.in_var('frame')}, {kwargs_str})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        kwargs = self._args(node)
        return {"interactions": prepare_interactions(inputs["frame"], **kwargs)}
