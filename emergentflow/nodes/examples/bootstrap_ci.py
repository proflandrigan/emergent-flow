"""
emergentflow.nodes.examples.bootstrap_ci
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``stats.bootstrap_ci`` — a *transform* node (1 in, 1 out).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.stats import bootstrap_ci

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class BootstrapCi(NodeDefinition):
    """Bootstrap confidence interval for a statistic (mean, median, std, sum)."""

    type = "stats.bootstrap_ci"
    version = 1
    family = "stats"
    label = "Bootstrap CI"
    category = "Statistics"
    description = "Bootstrap confidence interval for a statistic (mean, median, std, sum)."

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="DataFrame with the value column to bootstrap.",
        ),
        PortSpec(
            name="result",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="One-row DataFrame with point_estimate, ci_low, ci_high.",
        ),
    ]
    params = [
        ParamSpec(
            name="statistic",
            type_token="str",
            default="mean",
            label="Statistic",
            help="Statistic to compute: mean, median, std, sum.",
            hints=ValidationHints(
                choices=["mean", "median", "std", "sum"],
                widget="select",
            ),
        ),
        ParamSpec(
            name="value_col",
            type_token="str",
            label="Value column",
            help="Column to bootstrap.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="group_col",
            type_token="str",
            default=None,
            label="Group column",
            help="Column for cluster bootstrap (resample whole groups); None resamples rows.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="n_resamples",
            type_token="int",
            default=1000,
            label="Resamples",
            help="Number of bootstrap resamples.",
            hints=ValidationHints(widget="number", min=100),
        ),
        ParamSpec(
            name="ci",
            type_token="float",
            default=0.95,
            label="Confidence level",
            help="Confidence level (e.g. 0.95 for 95% CI).",
            hints=ValidationHints(widget="number", min=0, max=1),
        ),
        ParamSpec(
            name="random_state",
            type_token="int",
            default=0,
            label="Random state",
            help="Seed for deterministic resampling.",
            hints=ValidationHints(widget="number"),
        ),
    ]

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        values = {p.name: p.value for p in node.params}
        statistic = values.get("statistic") or "mean"
        value_col = values.get("value_col") or ""
        group_col = values.get("group_col")
        n_resamples = values.get("n_resamples") or 1000
        ci = values.get("ci")
        if ci is None:
            ci = 0.95
        random_state = values.get("random_state") or 0
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('result')} = ef.stats.bootstrap_ci("
                f"{ctx.in_var('frame')}, statistic={statistic!r}, "
                f"value_col={value_col!r}, group_col={group_col!r}, "
                f"n_resamples={n_resamples!r}, ci={ci!r}, "
                f"random_state={random_state!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        statistic = cast(str, values.get("statistic") or "mean")
        value_col = cast(str, values.get("value_col") or "")
        group_col = cast("str | None", values.get("group_col"))
        n_resamples = cast(int, values.get("n_resamples") or 1000)
        ci_val = values.get("ci")
        ci = cast(float, ci_val if ci_val is not None else 0.95)
        random_state = cast(int, values.get("random_state") or 0)
        return {
            "result": bootstrap_ci(
                inputs["frame"],
                statistic=statistic,
                value_col=value_col,
                group_col=group_col,
                n_resamples=n_resamples,
                ci=ci,
                random_state=random_state,
            )
        }
