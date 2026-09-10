"""
emergentflow.nodes.examples.causal_sensitivity
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``causal.sensitivity`` — unmeasured-confounding sensitivity analysis
(issue #164 Gap 1).

``method="e_value"`` takes the effect frame produced by ``causal.estimate_effect`` /
``causal.did`` (on the ``effect`` port; set ``scale="difference"`` + ``sd`` for those
mean-difference frames) or a raw ``risk_ratio`` and computes the E-value.
``method="rosenbaum"`` takes a matched-pair frame on the ``matched`` port and computes
Rosenbaum bounds at ``gamma``. Both IN ports are optional; a graph wires whichever the chosen
method needs. ``execute`` calls ``emergentflow.causal.sensitivity`` directly and ``codegen``
calls the same wrapper via the ``ef.`` alias, so the two paths are equivalent by construction
(ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.causal import sensitivity
from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.ir.params import ParamValue

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext

_METHOD_CHOICES = ["e_value", "rosenbaum"]
_SCALE_CHOICES = ["risk_ratio", "difference"]


@register
class CausalSensitivity(NodeDefinition):
    """E-value / Rosenbaum-bound sensitivity analysis for an estimated effect."""

    type = "causal.sensitivity"
    version = 2
    family = "causal"
    label = "Sensitivity"
    category = "Causal Inference"
    description = "E-value or Rosenbaum bounds: how strong must unmeasured confounding be?"

    ports = [
        PortSpec(
            name="effect",
            label="Effect",
            direction=Direction.IN,
            data_type="DataFrame",
            required=False,
            help="method='e_value': one-row effect frame with 'estimate' (and ci_low/ci_high). "
            "Frames from causal.estimate_effect / causal.did are mean differences: set "
            "scale='difference' and sd.",
        ),
        PortSpec(
            name="matched",
            label="Matched pairs",
            direction=Direction.IN,
            data_type="DataFrame",
            required=False,
            help="method='rosenbaum': matched-pair frame with one treated and one control "
            "binary outcome per row.",
        ),
        PortSpec(
            name="result",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="One-row frame: point_evalue/bound_evalue (e_value) or gamma/p_low/p_high "
            "(rosenbaum).",
        ),
    ]
    params = [
        ParamSpec(
            name="method",
            type_token="str",
            default="e_value",
            label="Method",
            help="e_value (E-value on an effect frame or risk_ratio) or rosenbaum (bounds on "
            "matched pairs).",
            hints=ValidationHints(
                choices=cast("list[ParamValue]", _METHOD_CHOICES), widget="select"
            ),
        ),
        ParamSpec(
            name="scale",
            type_token="str",
            default="risk_ratio",
            label="Estimate scale",
            help="e_value: risk_ratio (RR/OR/HR, default) or difference (mean difference; "
            "requires sd).",
            hints=ValidationHints(
                choices=cast("list[ParamValue]", _SCALE_CHOICES), widget="select"
            ),
        ),
        ParamSpec(
            name="sd",
            type_token="float",
            default=None,
            label="Outcome SD",
            help="e_value with scale='difference': the outcome's standard deviation "
            "(must be finite and > 0).",
            # min=1e-9 (not 0.0): scale='difference' + sd=0 violates the op's "sd > 0" guard,
            # so 0 must fail graph validation, not crash at run time.
            hints=ValidationHints(min=1e-9, widget="number"),
        ),
        ParamSpec(
            name="risk_ratio",
            type_token="float",
            default=None,
            label="Risk ratio",
            help="e_value: optional direct effect value (on `scale`); overrides the effect frame.",
            hints=ValidationHints(widget="number"),
        ),
        ParamSpec(
            name="treated_outcome_col",
            type_token="str",
            default=None,
            label="Treated outcome column",
            help="rosenbaum: binary treated-outcome column of the matched frame.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="control_outcome_col",
            type_token="str",
            default=None,
            label="Control outcome column",
            help="rosenbaum: binary control-outcome column of the matched frame.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="gamma",
            type_token="float",
            default=2.0,
            label="Gamma",
            help="rosenbaum: hidden-bias magnitude (odds ratio >= 1; 1 = no hidden bias).",
            hints=ValidationHints(min=1.0, widget="number"),
        ),
    ]

    def _args(self, node: Node) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        gamma = values.get("gamma")
        return {
            "method": cast(str, values.get("method") or "e_value"),
            "scale": cast(str, values.get("scale") or "risk_ratio"),
            # `is not None` (not truthiness) downstream: 0.0 is a legitimate value and must
            # reach both the codegen and execute paths identically (ADR 0002).
            "sd": cast("float | None", values.get("sd")),
            "risk_ratio": cast("float | None", values.get("risk_ratio")),
            "treated_outcome_col": cast("str | None", values.get("treated_outcome_col") or None),
            "control_outcome_col": cast("str | None", values.get("control_outcome_col") or None),
            "gamma": cast(float, 2.0 if gamma is None else gamma),
        }

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        args = self._args(node)
        parts: list[str] = []
        if args["method"] == "e_value":
            parts.append(f"effect={ctx.in_var_or_none('effect')}")
            parts.append(f"method={args['method']!r}")
            if args["risk_ratio"] is not None:
                parts.append(f"risk_ratio={args['risk_ratio']!r}")
            if args["scale"] != "risk_ratio":
                parts.append(f"scale={args['scale']!r}")
            if args["sd"] is not None:
                parts.append(f"sd={args['sd']!r}")
        else:
            parts.append(f"method={args['method']!r}")
            parts.append(f"matched={ctx.in_var_or_none('matched')}")
            parts.append(f"treated_outcome_col={args['treated_outcome_col']!r}")
            parts.append(f"control_outcome_col={args['control_outcome_col']!r}")
            if args["gamma"] != 2.0:
                parts.append(f"gamma={args['gamma']!r}")
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=f"{ctx.out_var('result')} = ef.causal.sensitivity({', '.join(parts)})",
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        args = self._args(node)
        return {
            "result": sensitivity(
                inputs.get("effect"),
                method=args["method"],
                risk_ratio=args["risk_ratio"],
                scale=args["scale"],
                sd=args["sd"],
                matched=inputs.get("matched"),
                treated_outcome_col=args["treated_outcome_col"],
                control_outcome_col=args["control_outcome_col"],
                gamma=args["gamma"],
            )
        }
