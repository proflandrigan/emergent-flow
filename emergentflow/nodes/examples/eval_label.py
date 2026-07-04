"""
emergentflow.nodes.examples.eval_label
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``eval.label`` — the label-merge node (Epic 9 Story 6).
2 required IN ports, 1 OUT port.

Both ``execute`` and ``codegen`` route through the same ``emergentflow.eval.label``
wrapper via the ``ef.eval.label`` alias, so the two paths are equivalent by
construction (ADR 0002). Unlike ``llm.call``/``eval.run``, this node needs no
injected client -- the merge is a pure pandas join over its two DataFrame
inputs, so it does not set ``requires_client``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from emergentflow.eval import label as eval_label
from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import PortSpec

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class EvalLabel(NodeDefinition):
    """Merge human labels onto an eval-run compare table."""

    type = "eval.label"
    version = 1
    family = "eval"
    label = "Eval Label"
    category = "LLM"
    description = "Merge a labels table onto an eval-run compare table, keyed by (row_id, variant)."

    ports = [
        PortSpec(
            name="results",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The eval-run compare table (ef.eval.run's output) to label.",
        ),
        PortSpec(
            name="labels",
            direction=Direction.IN,
            data_type="DataFrame",
            help=(
                "Label rows keyed by row_id/variant, with a label column and "
                "optional score/rubric/note."
            ),
        ),
        PortSpec(
            name="labeled",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="results, left-joined with labels on (row_id, variant).",
        ),
    ]
    params = []

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('labeled')} = ef.eval.label("
                f"{ctx.in_var('results')}, {ctx.in_var('labels')})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        return {"labeled": eval_label(inputs["results"], inputs["labels"])}
