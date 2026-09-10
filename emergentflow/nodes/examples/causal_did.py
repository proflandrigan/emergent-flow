"""
emergentflow.nodes.examples.causal_did
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``causal.did`` — two-way fixed-effects difference-in-differences
(issue #164 Gap 1).

``execute`` calls ``emergentflow.causal.did`` directly and ``codegen`` calls the same
wrapper via the ``ef.`` alias, so the two paths are equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.causal import did
from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class CausalDid(NodeDefinition):
    """Two-way fixed-effects difference-in-differences with pre-trend test."""

    type = "causal.did"
    version = 1
    family = "causal"
    label = "Diff-in-Diff"
    category = "Causal Inference"
    description = "TWFE difference-in-differences with cluster-robust SEs and pre-trend test."

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="Panel DataFrame: one row per unit per period.",
        ),
        PortSpec(
            name="result",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="One-row frame: estimate, CIs, p-value, counts, and the pre-trend test.",
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
            name="unit_col",
            type_token="str",
            required=True,
            label="Unit column",
            help="Column naming the panel's units (subject, school, ...).",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="time_col",
            type_token="str",
            required=True,
            label="Time column",
            help="Column naming the time periods.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="treated_col",
            type_token="str",
            required=True,
            label="Treated column",
            help="Binary column: units ever treated.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="post_col",
            type_token="str",
            required=True,
            label="Post column",
            help="Binary column: post-treatment periods.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="covariates",
            type_token="list[str]",
            default=None,
            label="Covariates",
            help="Optional additional adjustment regressors.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="cluster_col",
            type_token="str",
            default=None,
            label="Cluster column",
            help="Columns to cluster SEs over; defaults to unit_col.",
            hints=ValidationHints(widget="column"),
        ),
    ]

    def _args(self, node: Node) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        return {
            "outcome": cast(str, values.get("outcome")),
            "unit_col": cast(str, values.get("unit_col")),
            "time_col": cast(str, values.get("time_col")),
            "treated_col": cast(str, values.get("treated_col")),
            "post_col": cast(str, values.get("post_col")),
            "covariates": cast("list[str] | None", values.get("covariates")),
            "cluster_col": cast("str | None", values.get("cluster_col")),
        }

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        args = self._args(node)
        codegen_cov = f", covariates={args['covariates']!r}" if args["covariates"] else ""
        codegen_cluster = f", cluster_col={args['cluster_col']!r}" if args["cluster_col"] else ""
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('result')} = ef.causal.did("
                f"{ctx.in_var('frame')}, outcome={args['outcome']!r}, "
                f"unit_col={args['unit_col']!r}, time_col={args['time_col']!r}, "
                f"treated_col={args['treated_col']!r}, post_col={args['post_col']!r}"
                f"{codegen_cov}{codegen_cluster})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        args = self._args(node)
        return {
            "result": did(
                inputs["frame"],
                outcome=args["outcome"],
                unit_col=args["unit_col"],
                time_col=args["time_col"],
                treated_col=args["treated_col"],
                post_col=args["post_col"],
                covariates=args["covariates"],
                cluster_col=args["cluster_col"],
            )
        }
