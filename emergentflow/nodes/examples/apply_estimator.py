"""
emergentflow.nodes.examples.apply_estimator
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``ml.apply_estimator`` — the "apply" archetype node (Epic 8, ADR 0016).

Applies a fitted ``Model`` (from ``ml.fit_estimator``) to a DataFrame via ``predict`` or
``score_samples``, returning a new DataFrame. (A companion ``ml.transform`` node for fitted
``Transformer`` inputs is a separate, later task — this node's IN port only accepts ``Model``.)
``execute`` calls ``emergentflow.ml.apply_estimator`` directly and the code emitted by
``codegen`` calls the same wrapper via the ``ef.`` alias, so the two paths are equivalent by
construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.ml import apply_estimator

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class ApplyEstimator(NodeDefinition):
    """Apply a fitted Model to data via predict or score_samples."""

    type = "ml.apply_estimator"
    version = 1
    family = "ml"
    label = "Apply Estimator"
    category = "Machine Learning"
    description = "Apply a fitted Model to data via predict or score_samples."

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
            help="The data to apply the model to.",
        ),
        PortSpec(
            name="result",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="Input rows plus the op's output column.",
        ),
    ]
    params = [
        ParamSpec(
            name="op",
            type_token="str",
            default="predict",
            label="Operation",
            help="Which operation to apply: predict adds a 'prediction' column, "
            "score_samples adds a 'score' column.",
            hints=ValidationHints(choices=["predict", "score_samples"], widget="select"),
        ),
    ]

    def _op(self, node: Node) -> str:
        values = {p.name: p.value for p in node.params}
        op = values.get("op", "predict") or "predict"
        return cast(str, op)

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        op = self._op(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('result')} = ef.ml.apply_estimator("
                f"{ctx.in_var('model')}, {ctx.in_var('frame')}, op={op!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        op = self._op(node)
        return {"result": apply_estimator(inputs["model"], inputs["frame"], op=op)}
