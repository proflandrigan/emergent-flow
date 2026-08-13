"""
emergentflow.nodes.examples.optimize_threshold
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``ml.optimize_threshold`` — optimize a binary classifier's
decision threshold to maximize F1 (ADR 0016).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.ml import optimize_threshold

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class OptimizeThreshold(NodeDefinition):
    """Optimize the decision threshold of a binary classifier to maximize F1."""

    type = "ml.optimize_threshold"
    version = 1
    family = "ml"
    label = "Optimize Threshold"
    category = "Machine Learning"
    description = "Optimize the decision threshold of a binary classifier to maximize F1."

    ports = [
        PortSpec(
            name="model",
            direction=Direction.IN,
            data_type="Model",
            help="The fitted binary classifier.",
        ),
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="Data (features + target) to evaluate thresholds on.",
        ),
        PortSpec(
            name="threshold_result",
            label="Result",
            direction=Direction.OUT,
            data_type="any",
            help="The threshold-optimization result.",
        ),
    ]
    params = [
        ParamSpec(
            name="target",
            type_token="str",
            required=True,
            label="Target column",
            help="Column to predict.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="positive_class",
            type_token="str",
            default=None,
            label="Positive class",
            help="Class to treat as positive; defaults to the second class.",
            hints=ValidationHints(widget="column"),
        ),
    ]

    def _args(self, node: Node) -> tuple[str, str | None]:
        values = {p.name: p.value for p in node.params}
        return (
            cast(str, values.get("target")),
            cast("str | None", values.get("positive_class")),
        )

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        target, positive_class = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('threshold_result')} = ef.ml.optimize_threshold("
                f"{ctx.in_var('model')}, {ctx.in_var('frame')}, target={target!r}, "
                f"positive_class={positive_class!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        target, positive_class = self._args(node)
        return {
            "threshold_result": optimize_threshold(
                inputs["model"],
                inputs["frame"],
                target=target,
                positive_class=positive_class,
            )
        }
