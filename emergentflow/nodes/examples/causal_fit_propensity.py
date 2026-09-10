"""
emergentflow.nodes.examples.causal_fit_propensity
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``causal.fit_propensity`` — propensity-score fitting + balance
diagnostics (issue #164 Gap 1).

Fits a binary-treatment propensity model and returns the fitted scores/IPW weights
(``result``, a ``PropensityResult`` record) AND the balance table as a second OUT port
(``balance``), so the weighting diagnostic is a first-class, wireable output rather than
hidden inside the record. ``execute`` calls ``emergentflow.causal.fit_propensity``
directly and ``codegen`` calls the same wrapper via the ``ef.`` alias, so the two paths
are equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.causal import fit_propensity
from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.ir.params import ParamValue

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext

_PROPENSITY_ESTIMATOR_CHOICES = ["LogisticRegression"]


@register
class CausalFitPropensity(NodeDefinition):
    """Fit a propensity model; return scores/weights and a balance diagnostics table."""

    type = "causal.fit_propensity"
    version = 2
    family = "causal"
    label = "Fit Propensity"
    category = "Causal Inference"
    description = "Fit a propensity model; report IPW weights and balance diagnostics."

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame with the binary treatment and covariates.",
        ),
        PortSpec(
            name="result",
            direction=Direction.OUT,
            data_type="PropensityResult",
            help="Fitted scores, IPW/ATT weights, and summary diagnostics.",
        ),
        PortSpec(
            name="balance",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="Per-covariate standardized mean difference + variance ratio before/after "
            "weighting.",
        ),
    ]
    params = [
        ParamSpec(
            name="treatment",
            type_token="str",
            required=True,
            label="Treatment column",
            help="Binary (0/1 or True/False) column naming treated units.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="covariates",
            type_token="list[str]",
            required=True,
            label="Covariates",
            help="Adjustment-set columns; non-numeric are one-hot encoded.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="estimator",
            type_token="str",
            default="LogisticRegression",
            label="Estimator",
            help="Propensity model estimator.",
            hints=ValidationHints(
                choices=cast("list[ParamValue]", _PROPENSITY_ESTIMATOR_CHOICES), widget="select"
            ),
        ),
        ParamSpec(
            name="params",
            type_token="dict[str, any]",
            default={},
            label="Estimator params",
            help='Constructor kwargs for the propensity estimator (e.g. {"C": 0.5}).',
        ),
        ParamSpec(
            name="trim",
            type_token="list[float]",
            default=[0.01, 0.99],
            label="Trim",
            help="Propensity-score support to winsorize weights to, or [] for none.",
        ),
        ParamSpec(
            name="effect",
            type_token="str",
            default="ATE",
            label="Effect",
            help="Weight scheme: 'ATE' (IPW) or 'ATT'.",
            hints=ValidationHints(
                choices=cast("list[ParamValue]", ["ATE", "ATT"]), widget="select"
            ),
        ),
    ]

    def _args(self, node: Node) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        # `values.get("trim", [0.01, 0.99])`: an ABSENT param falls back to the declared
        # default (as instantiate would fill it); `[]` (or None) still means "no trimming".
        trim = cast("list[float] | None", values.get("trim", [0.01, 0.99]))
        return {
            "treatment": cast(str, values.get("treatment")),
            "covariates": cast("list[str]", values.get("covariates")),
            "estimator": cast(str, values.get("estimator", "LogisticRegression")),
            "params": cast("dict[str, Any] | None", values.get("params") or None),
            "trim": cast("tuple[float, float] | None", tuple(trim) if trim else None),
            "effect": cast(str, values.get("effect", "ATE")),
        }

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        args = self._args(node)
        # Always emit trim: `[]` means "no trimming" (None) on the execute path, and omitting the
        # kwarg would make the compiled script fall back to the op default (0.01, 0.99).
        codegen_trim = f", trim={args['trim']!r}"
        codegen_params = f", params={args['params']!r}" if args["params"] is not None else ""
        codegen_effect = f", effect={args['effect']!r}" if args["effect"] != "ATE" else ""
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('result')} = ef.causal.fit_propensity("
                f"{ctx.in_var('frame')}, treatment={args['treatment']!r}, "
                f"covariates={args['covariates']!r}, estimator={args['estimator']!r}"
                f"{codegen_params}{codegen_trim}{codegen_effect})\n"
                f"{ctx.out_var('balance')} = {ctx.out_var('result')}.balance"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        args = self._args(node)
        result = fit_propensity(
            inputs["frame"],
            treatment=args["treatment"],
            covariates=args["covariates"],
            estimator=args["estimator"],
            params=args["params"],
            trim=args["trim"],
            effect=args["effect"],
        )
        return {"result": result, "balance": result.balance}
