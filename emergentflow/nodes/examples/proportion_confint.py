"""
emergentflow.nodes.examples.proportion_confint
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``stats.proportion_confint`` — a *transform* node (1 in, 1 out).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.stats import proportion_confint

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class ProportionConfint(NodeDefinition):
    """Per-group confidence interval for a single proportion (Wilson by default)."""

    type = "stats.proportion_confint"
    version = 1
    family = "stats"
    label = "Proportion CI"
    category = "Statistics"
    description = "Per-group point estimate and confidence interval for a single proportion."

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="DataFrame with a binary success column.",
        ),
        PortSpec(
            name="result",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="One row per group with n, successes, proportion, ci_low, ci_high.",
        ),
    ]
    params = [
        ParamSpec(
            name="success_col",
            type_token="str",
            label="Success column",
            help="Binary 0/1/True/False column.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="by",
            type_token="list[str]",
            default=None,
            label="Group by",
            help="Columns to group by for per-group intervals.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="method",
            type_token="str",
            default="wilson",
            label="Method",
            help="CI method: normal, wilson, jeffreys, beta, agresti_coull.",
            hints=ValidationHints(
                choices=["normal", "wilson", "jeffreys", "beta", "agresti_coull"],
                widget="select",
            ),
        ),
        ParamSpec(
            name="alpha",
            type_token="float",
            default=0.05,
            label="Alpha",
            help="Significance level (1 - confidence).",
            hints=ValidationHints(widget="number", min=0, max=1),
        ),
        ParamSpec(
            name="min_n",
            type_token="int",
            default=None,
            label="Min N",
            help="Minimum sample size for reporting; groups below this get null bounds.",
            hints=ValidationHints(widget="number", min=1),
        ),
    ]

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        values = {p.name: p.value for p in node.params}
        success_col = values.get("success_col") or ""
        by = values.get("by")
        method = values.get("method") or "wilson"
        alpha = values.get("alpha")
        if alpha is None:
            alpha = 0.05
        min_n = values.get("min_n")
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('result')} = ef.stats.proportion_confint("
                f"{ctx.in_var('frame')}, success_col={success_col!r}, "
                f"by={by!r}, method={method!r}, alpha={alpha!r}, min_n={min_n!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        success_col = cast(str, values.get("success_col") or "")
        by = cast("list[str] | None", values.get("by"))
        method = cast(str, values.get("method") or "wilson")
        alpha_val = values.get("alpha")
        alpha = cast(float, alpha_val if alpha_val is not None else 0.05)
        min_n = cast("int | None", values.get("min_n"))
        return {
            "result": proportion_confint(
                inputs["frame"],
                success_col=success_col,
                by=by,
                method=method,
                alpha=alpha,
                min_n=min_n,
            )
        }
