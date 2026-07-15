"""
emergentflow.nodes.examples.recommend_evaluate
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``recommend.evaluate`` — score a fitted recommender's top-k recommendations
against held-out interactions (Epic 15, Story 12).

``execute`` calls ``emergentflow.recommend.evaluate`` directly and the code emitted by
``codegen`` calls the same wrapper via the ``ef.`` alias, so the two paths are equivalent by
construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.recommend import evaluate

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class RecommendEvaluate(NodeDefinition):
    """Score a fitted recommender's top-k recommendations against held-out interactions."""

    type = "recommend.evaluate"
    version = 1
    family = "recommend"
    label = "Evaluate"
    category = "Recommenders"
    description = "Score a fitted recommender against held-out interactions."

    ports = [
        PortSpec(
            name="recommender",
            direction=Direction.IN,
            data_type="Recommender",
            help="The fitted recommender to evaluate.",
        ),
        PortSpec(
            name="test_interactions",
            direction=Direction.IN,
            data_type="InteractionMatrix",
            help="Held-out interactions to score recommendations against.",
        ),
        PortSpec(
            name="result",
            direction=Direction.OUT,
            data_type="EvalResult",
            help="Per-user metrics + system-level aggregate metrics.",
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
        ParamSpec(
            name="metrics",
            type_token="list[str]",
            default=None,
            label="Metrics",
            help="Subset of {precision_at_k, recall_at_k, ndcg_at_k, map_at_k, hit_rate, "
            "coverage, diversity, novelty} to compute; unset means all eight.",
        ),
    ]

    def _args(self, node: Node) -> tuple[int, list[str] | None]:
        values = {p.name: p.value for p in node.params}
        k = cast(int, values.get("k", 10))
        metrics = cast("list[str] | None", values.get("metrics"))
        return k, metrics

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        k, metrics = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('result')} = ef.recommend.evaluate("
                f"{ctx.in_var('recommender')}, {ctx.in_var('test_interactions')}, "
                f"k={k!r}, metrics={metrics!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        k, metrics = self._args(node)
        return {
            "result": evaluate(
                inputs["recommender"], inputs["test_interactions"], k=k, metrics=metrics
            )
        }
