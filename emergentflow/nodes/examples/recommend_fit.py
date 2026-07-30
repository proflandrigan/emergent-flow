"""
emergentflow.nodes.examples.recommend_fit
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``recommend.fit`` — the "fit" archetype node for recommender systems (Epic 15).

Fits a curated, allow-listed recommender algorithm (any algorithm registered in
``emergentflow.recommend.registry``) and returns a fitted ``Recommender``. The
``algorithm`` choice list is computed at import time from the live registry, so it grows
automatically as more algorithms are curated. ``execute`` calls ``emergentflow.recommend.fit``
directly and the code emitted by ``codegen`` calls the same wrapper via the ``ef.`` alias, so the
two paths are equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.ir.params import ParamValue
from emergentflow.recommend import fit
from emergentflow.recommend.registry import known_recommender_keys

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class RecommendFit(NodeDefinition):
    """Fit a curated, allow-listed recommender algorithm."""

    type = "recommend.fit"
    version = 1
    family = "recommend"
    label = "Fit Recommender"
    category = "Recommenders"
    description = "Fit a curated, allow-listed recommender algorithm."

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
            help="Optional item features for content-based algorithms.",
        ),
        PortSpec(
            name="recommender",
            direction=Direction.OUT,
            data_type="Recommender",
            help="The fitted recommender model.",
        ),
    ]
    params = [
        ParamSpec(
            name="algorithm",
            type_token="str",
            required=True,
            label="Algorithm",
            help="Which curated recommender algorithm to fit.",
            hints=ValidationHints(
                choices=cast("list[ParamValue]", known_recommender_keys()), widget="select"
            ),
        ),
        ParamSpec(
            name="params",
            type_token="dict[str, any]",
            default={},
            label="Algorithm params",
            help="Keyword arguments for the chosen algorithm.",
        ),
    ]

    def _args(self, node: Node) -> tuple[str, dict[str, Any]]:
        values = {p.name: p.value for p in node.params}
        algorithm = cast(str, values.get("algorithm"))
        params = cast("dict[str, Any]", values.get("params") or {})
        return algorithm, params

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        algorithm, params = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('recommender')} = ef.recommend.fit("
                f"{ctx.in_var('interactions')}, algorithm={algorithm!r}, "
                f"item_features={ctx.in_var_or_none('item_features')}, params={params!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        algorithm, params = self._args(node)
        return {
            "recommender": fit(
                inputs["interactions"],
                algorithm=algorithm,
                item_features=inputs.get("item_features"),
                params=params,
            )
        }
