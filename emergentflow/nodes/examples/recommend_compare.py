"""
emergentflow.nodes.examples.recommend_compare
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``recommend.compare`` — evaluate multiple fitted recommenders on the same
held-out test set and rank them by NDCG@k (Epic 15, Story 12).

Takes multiple already-fitted ``Recommender`` inputs (a ``Cardinality.MANY`` IN port, the same
fan-in support proven by ``recommend.hybrid_weighted``, Epic 15 Story 9) and emits a single tidy
comparison ``DataFrame``. ``execute`` calls ``emergentflow.recommend.compare`` directly and the
code emitted by ``codegen`` calls the same wrapper via the ``ef.`` alias, so the two paths are
equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Cardinality, Direction
from emergentflow.ir.node import Node
from emergentflow.recommend import compare

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class RecommendCompare(NodeDefinition):
    """Evaluate multiple fitted recommenders on the same test set and rank them by NDCG@k."""

    type = "recommend.compare"
    version = 1
    family = "recommend"
    label = "Compare"
    category = "Recommenders"
    description = "Evaluate multiple fitted recommenders and rank them by NDCG@k."

    ports = [
        PortSpec(
            name="recommenders",
            label="Recommenders",
            direction=Direction.IN,
            data_type="Recommender",
            cardinality=Cardinality.MANY,
            help="Two or more already-fitted recommenders to compare.",
        ),
        PortSpec(
            name="test_interactions",
            direction=Direction.IN,
            data_type="InteractionMatrix",
            help="Held-out interactions all recommenders are scored against.",
        ),
        PortSpec(
            name="result",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="Tidy comparison table, one row per recommender, sorted by NDCG@k descending.",
        ),
    ]
    params = [
        ParamSpec(
            name="k",
            type_token="int",
            default=10,
            label="k",
            help="Cutoff for the ranking metrics.",
        ),
    ]

    def _args(self, node: Node) -> tuple[int]:
        values = {p.name: p.value for p in node.params}
        return (cast(int, values.get("k", 10)),)

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        (k,) = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('result')} = ef.recommend.compare("
                f"{ctx.in_var('test_interactions')}, "
                f"recommenders={ctx.in_var('recommenders')}, k={k!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        (k,) = self._args(node)
        return {
            "result": compare(inputs["test_interactions"], recommenders=inputs["recommenders"], k=k)
        }
