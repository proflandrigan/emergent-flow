"""
emergentflow.nodes.examples.recommend_fit_sequence
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``recommend.fit_sequence`` — fit a sequential recommender from a
SequenceDataset (Epic 15).

``execute`` calls ``emergentflow.recommend.fit_sequence`` directly and the code
emitted by ``codegen`` calls the same wrapper via the ``ef.`` alias, so the two paths are
equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.ir.params import ParamValue
from emergentflow.recommend import fit_sequence
from emergentflow.recommend.registry import keys_for_family

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext

_SEQUENTIAL_ALGORITHMS: list[str] = keys_for_family("sequential")


@register
class RecommendFitSequence(NodeDefinition):
    """Fit a curated sequential recommender algorithm from a SequenceDataset."""

    type = "recommend.fit_sequence"
    version = 1
    family = "recommend"
    label = "Fit Sequence Recommender"
    category = "Recommenders"
    description = "Fit a sequential (session-based) recommender algorithm from a SequenceDataset."

    ports = [
        PortSpec(
            name="sequences",
            label="Sequences",
            direction=Direction.IN,
            data_type="SequenceDataset",
            help="The sequence dataset produced by build_sequences.",
        ),
        PortSpec(
            name="recommender",
            direction=Direction.OUT,
            data_type="Recommender",
            help="The fitted sequential recommender model.",
        ),
    ]
    params = [
        ParamSpec(
            name="algorithm",
            type_token="str",
            required=True,
            label="Algorithm",
            help="Which sequential recommender algorithm to fit.",
            hints=ValidationHints(
                choices=cast("list[ParamValue]", _SEQUENTIAL_ALGORITHMS), widget="select"
            ),
        ),
        ParamSpec(
            name="params",
            type_token="dict[str, any]",
            default={},
            label="Algorithm params",
            help="Keyword arguments for the chosen sequential algorithm.",
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
                f"{ctx.out_var('recommender')} = ef.recommend.fit_sequence("
                f"{ctx.in_var('sequences')}, algorithm={algorithm!r}, params={params!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        algorithm, params = self._args(node)
        return {
            "recommender": fit_sequence(
                inputs["sequences"],
                algorithm=algorithm,
                params=params,
            )
        }
