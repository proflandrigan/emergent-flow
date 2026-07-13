"""
emergentflow.nodes.examples.predict
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``ml.predict`` — a *transform* node (2 in, 1 out).

Real, scikit-learn-backed predictor (Epic 1, Story 12). ``execute`` calls
``emergentflow.ml.predict`` directly and the code emitted by ``codegen`` calls
the same wrapper via the ``ef.`` alias, so the two paths are equivalent by
construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.ml import predict

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import PortSpec

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class Predict(NodeDefinition):
    """Apply a fitted model to data, producing predictions."""

    type = "ml.predict"
    version = 1
    family = "ml"
    label = "Predict"
    category = "Machine Learning"
    description = "Apply a fitted model to data, producing predictions."

    ports = [
        PortSpec(
            name="model",
            direction=Direction.IN,
            data_type="Model",
            help="The fitted model to apply.",
        ),
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The data to predict on.",
        ),
        PortSpec(
            name="predictions",
            direction=Direction.OUT,
            data_type="Predictions",
            help="Input rows plus a prediction column.",
        ),
    ]
    params = []

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('predictions')} = ef.ml.predict("
                f"{ctx.in_var('model')}, {ctx.in_var('frame')})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        return {"predictions": predict(inputs["model"], inputs["frame"])}
