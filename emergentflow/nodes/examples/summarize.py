"""
emergentflow.nodes.examples.summarize
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``ml.summarize`` — a *transform* node (1 in, 1 out).

Returns a structural, inspectable summary (accuracy/coefficients, explained variance, cluster
sizes, ... depending on the fitted estimator's family — Epic 8, Story 3 summary builders) for a
fitted ``Model``. ``execute`` calls ``emergentflow.ml.summarize`` directly and the code emitted
by ``codegen`` calls the same wrapper via the ``ef.`` alias, so the two paths are equivalent by
construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.ml import summarize

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import PortSpec

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class Summarize(NodeDefinition):
    """Return a structural, inspectable summary of a fitted model."""

    type = "ml.summarize"
    version = 1
    family = "ml"
    label = "Summarize"
    category = "Machine Learning"
    description = "Return a structural, inspectable summary of a fitted model."

    ports = [
        PortSpec(
            name="model",
            direction=Direction.IN,
            data_type="Model",
            help="The fitted model to summarize.",
        ),
        PortSpec(
            name="summary",
            direction=Direction.OUT,
            data_type="ModelSummary",
            help="Inspectable, JSON-native structural summary.",
        ),
    ]
    params = []

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=f"{ctx.out_var('summary')} = ef.ml.summarize({ctx.in_var('model')})",
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        return {"summary": summarize(inputs["model"])}
