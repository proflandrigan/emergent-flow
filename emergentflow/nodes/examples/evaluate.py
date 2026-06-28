"""
emergentflow.nodes.examples.evaluate
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``ml.evaluate`` — a *transform* node (2 in, 1 out).

Real, scikit-learn-backed evaluator (Epic 1, Story 13). ``execute`` calls
``emergentflow.ml.evaluate`` directly and the code emitted by ``codegen`` calls
the same wrapper via the ``ef.`` alias, so the two paths are equivalent by
construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.ml import evaluate

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import PortSpec

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class Evaluate(NodeDefinition):
    """Score a fitted model against labeled data."""

    type = "ml.evaluate"
    version = 1
    family = "ml"
    label = "Evaluate"
    category = "Machine Learning"
    description = "Score a fitted model against labeled data."

    ports = [
        PortSpec(
            name="model",
            direction=Direction.IN,
            data_type="Model",
            help="The fitted model to evaluate.",
        ),
        PortSpec(
            name="frame",
            direction=Direction.IN,
            data_type="DataFrame",
            help="Labeled data to score the model against.",
        ),
        PortSpec(
            name="result",
            direction=Direction.OUT,
            data_type="EvaluationResult",
            help="Inspectable evaluation metrics.",
        ),
    ]
    params = []

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('result')} = ef.ml.evaluate("
                f"{ctx.in_var('model')}, {ctx.in_var('frame')})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        return {"result": evaluate(inputs["model"], inputs["frame"])}
