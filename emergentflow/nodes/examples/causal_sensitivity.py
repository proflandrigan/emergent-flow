"""
emergentflow.nodes.examples.causal_sensitivity
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``causal.sensitivity`` — unmeasured-confounding sensitivity analysis
(issue #164 Gap 1).

Takes the effect frame produced by ``causal.estimate_effect`` (or a raw risk ratio) and
computes the E-value: how strong would unmeasured confounding have to be to explain the
estimate away? ``execute`` calls ``emergentflow.causal.sensitivity`` directly and
``codegen`` calls the same wrapper via the ``ef.`` alias, so the two paths are equivalent
by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.causal import sensitivity
from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class CausalSensitivity(NodeDefinition):
    """E-value sensitivity analysis for an estimated effect."""

    type = "causal.sensitivity"
    version = 1
    family = "causal"
    label = "Sensitivity"
    category = "Causal Inference"
    description = "E-value: how strong must unmeasured confounding be to explain the estimate?"

    ports = [
        PortSpec(
            name="effect",
            label="Effect",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The one-row effect frame from causal.estimate_effect (with 'estimate').",
        ),
        PortSpec(
            name="result",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="One-row frame with point_evalue and bound_evalue.",
        ),
    ]
    params = [
        ParamSpec(
            name="method",
            type_token="str",
            default="e_value",
            label="Method",
            help="Sensitivity method; the MVP implements 'e_value'.",
            hints=ValidationHints(choices=["e_value"], widget="select"),
        ),
        ParamSpec(
            name="risk_ratio",
            type_token="float",
            default=None,
            label="Risk ratio",
            help="Optional direct risk ratio; overrides the effect frame's estimate.",
            hints=ValidationHints(widget="number"),
        ),
    ]

    def _args(self, node: Node) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        risk_ratio = values.get("risk_ratio")
        return {
            "method": cast(str, values.get("method", "e_value")),
            "risk_ratio": cast("float | None", risk_ratio if risk_ratio is not None else None),
        }

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        args = self._args(node)
        codegen_rr = f", risk_ratio={args['risk_ratio']!r}" if args["risk_ratio"] else ""
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('result')} = ef.causal.sensitivity("
                f"{ctx.in_var('effect')}, method={args['method']!r}{codegen_rr})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        args = self._args(node)
        return {
            "result": sensitivity(
                inputs["effect"],
                method=args["method"],
                risk_ratio=args["risk_ratio"],
            )
        }
