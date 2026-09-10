"""
emergentflow.nodes.examples.causal_estimate_effect
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``causal.estimate_effect`` — ATE estimation (issue #164 Gap 1).

Computes an average treatment effect by one of four methods (IPW / AIPW / matching /
regression adjustment) with cluster-robust or bootstrap inference. ``execute`` calls
``emergentflow.causal.estimate_effect`` directly and ``codegen`` calls the same wrapper
via the ``ef.`` alias, so the two paths are equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.causal import estimate_effect, keys_for_archetype
from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.ir.params import ParamValue

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class CausalEstimateEffect(NodeDefinition):
    """Estimate an average treatment effect with honest uncertainty."""

    type = "causal.estimate_effect"
    version = 1
    family = "causal"
    label = "Estimate Effect"
    category = "Causal Inference"
    description = "ATE estimation via IPW/AIPW/matching/regression adjustment."

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame with outcome, binary treatment, and covariates.",
        ),
        PortSpec(
            name="result",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="One-row frame: estimate, std_err, ci_low, ci_high, p_value, method.",
        ),
    ]
    params = [
        ParamSpec(
            name="outcome",
            type_token="str",
            required=True,
            label="Outcome column",
            help="Continuous outcome column.",
            hints=ValidationHints(widget="column"),
        ),
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
            default=None,
            label="Covariates",
            help="Adjustment-set columns; non-numeric are one-hot encoded.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="method",
            type_token="str",
            default="aipw",
            label="Method",
            help="Effect estimator: ipw, aipw, matching, or regression_adjust.",
            hints=ValidationHints(
                choices=cast("list[ParamValue]", keys_for_archetype("estimate_effect")),
                widget="select",
            ),
        ),
        ParamSpec(
            name="cluster_col",
            type_token="str",
            default=None,
            label="Cluster column",
            help="Optional column to cluster-robust inference over (e.g. subject id).",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="n_boot",
            type_token="int",
            default=0,
            label="Bootstrap resamples",
            help=">0 runs a bootstrap (cluster bootstrap when cluster_col is set).",
            hints=ValidationHints(min=0, widget="number"),
        ),
    ]

    def _args(self, node: Node) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        return {
            "outcome": cast(str, values.get("outcome")),
            "treatment": cast(str, values.get("treatment")),
            "covariates": cast("list[str] | None", values.get("covariates")),
            "method": cast(str, values.get("method", "aipw")),
            "cluster_col": cast("str | None", values.get("cluster_col")),
            "n_boot": cast(int, values.get("n_boot") or 0),
        }

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        args = self._args(node)
        codegen_cluster = f", cluster_col={args['cluster_col']!r}" if args["cluster_col"] else ""
        codegen_boot = f", n_boot={args['n_boot']!r}" if args["n_boot"] else ""
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('result')} = ef.causal.estimate_effect("
                f"{ctx.in_var('frame')}, outcome={args['outcome']!r}, "
                f"treatment={args['treatment']!r}, covariates={args['covariates']!r}, "
                f"method={args['method']!r}{codegen_cluster}{codegen_boot})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        args = self._args(node)
        return {
            "result": estimate_effect(
                inputs["frame"],
                outcome=args["outcome"],
                treatment=args["treatment"],
                covariates=args["covariates"],
                method=args["method"],
                cluster_col=args["cluster_col"],
                n_boot=args["n_boot"],
            )
        }
