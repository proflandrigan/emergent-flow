"""
emergentflow.nodes.examples.survival_curve
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``stats.survival_curve`` — a *transform* node (1 in, 1 out).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.stats.survival import survival_curve

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class SurvivalCurve(NodeDefinition):
    """Kaplan-Meier survival curve."""

    type = "stats.survival_curve"
    version = 1
    family = "stats"
    label = "Survival Curve"
    category = "Statistics"
    description = "Kaplan-Meier survival curve with confidence bounds."
    requires_extra = "emergentflow[survival]"

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="DataFrame with duration and event columns.",
        ),
        PortSpec(
            name="result",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="Survival curve: timeline, survival_probability, ci_low, ci_high.",
        ),
    ]
    params = [
        ParamSpec(
            name="duration_col",
            type_token="str",
            label="Duration column",
            help="Column with time-to-event (or time-to-censor).",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="event_col",
            type_token="str",
            label="Event column",
            help="Column indicating event (1) or censored (0).",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="group_col",
            type_token="str",
            default=None,
            label="Group column",
            help="Column to stratify curves by; None returns a single curve.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="alpha",
            type_token="float",
            default=0.05,
            label="Alpha",
            help="Significance level.",
            hints=ValidationHints(widget="number", min=0, max=1),
        ),
    ]

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        values = {p.name: p.value for p in node.params}
        duration_col = values.get("duration_col") or ""
        event_col = values.get("event_col") or ""
        group_col = values.get("group_col")
        alpha = values.get("alpha")
        if alpha is None:
            alpha = 0.05
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('result')} = ef.stats.survival_curve("
                f"{ctx.in_var('frame')}, duration_col={duration_col!r}, "
                f"event_col={event_col!r}, group_col={group_col!r}, alpha={alpha!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        duration_col = cast(str, values.get("duration_col") or "")
        event_col = cast(str, values.get("event_col") or "")
        group_col = cast("str | None", values.get("group_col"))
        alpha_val = values.get("alpha")
        alpha = cast(float, alpha_val if alpha_val is not None else 0.05)
        return {
            "result": survival_curve(
                inputs["frame"],
                duration_col=duration_col,
                event_col=event_col,
                group_col=group_col,
                alpha=alpha,
            )
        }
