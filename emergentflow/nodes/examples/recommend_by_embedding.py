"""
emergentflow.nodes.examples.recommend_by_embedding
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``recommend.recommend_by_embedding`` — the embedding-similarity front door.

Fits an embedding-backed content-based recommender via ``ef.recommend.fit`` with
``algorithm="embedding_similarity"`` hardcoded. Works with any pre-computed embedding column
(a list of floats per item). The composite ``embed_then_recommend`` node (chaining
``ef.llm.embed`` -> this node) described in Epic 15 Story 6 is deferred because
``ef.llm.embed`` does not exist yet in this codebase (Epic 9); this node only covers the
pre-computed-embedding-column path.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.recommend import fit

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class RecommendByEmbedding(NodeDefinition):
    """Fit an embedding-similarity content-based recommender."""

    type = "recommend.recommend_by_embedding"
    version = 1
    family = "recommend"
    label = "Recommend by Embedding Similarity"
    category = "Recommenders"
    description = (
        "Content-based filtering via dense embedding similarity — fits a "
        "NearestNeighbors index on a pre-computed embedding column."
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
            help="DataFrame with a pre-computed embedding column (list of floats) per item.",
        ),
        PortSpec(
            name="recommender",
            direction=Direction.OUT,
            data_type="Recommender",
            help="The fitted embedding-similarity recommender.",
        ),
    ]
    params = [
        ParamSpec(
            name="item_id_col",
            type_token="str",
            default="item_id",
            label="Item ID column",
            help="Column identifying the item in item_features.",
        ),
        ParamSpec(
            name="embedding_col",
            type_token="str",
            required=True,
            label="Embedding column",
            help="Column containing a pre-computed embedding (list of floats) per item.",
        ),
        ParamSpec(
            name="metric",
            type_token="str",
            default="cosine",
            label="Similarity metric",
            help="Distance metric for NearestNeighbors.",
            hints=ValidationHints(
                choices=["cosine", "euclidean"],
                widget="select",
            ),
        ),
    ]

    def _args(self, node: Node) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        params: dict[str, Any] = {}
        for key in ("item_id_col", "embedding_col", "metric"):
            val = values.get(key)
            if val not in (None, ""):
                params[key] = val
        return params

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        params = self._args(node)
        params_str = ", ".join(f"{k!r}: {v!r}" for k, v in params.items())
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('recommender')} = ef.recommend.fit("
                f"{ctx.in_var('interactions')}, algorithm='embedding_similarity', "
                f"item_features={ctx.in_var('item_features')}, "
                f"params={{{params_str}}})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        params = self._args(node)
        return {
            "recommender": fit(
                inputs["interactions"],
                algorithm="embedding_similarity",
                item_features=inputs["item_features"],
                params=params,
            )
        }
