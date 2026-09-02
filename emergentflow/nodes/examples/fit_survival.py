"""
emergentflow.nodes.examples.fit_survival
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``stats.fit_survival`` — a *transform* node (1 in, 1 out).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.stats.survival import fit_survival

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class FitSurvival(NodeDefinition):
    """Fit a Cox proportional-hazards model."""

    type = "stats.fit_survival"
    version = 1
    family = "stats"
    label = "Fit Survival"
    category = "Statistics"
    description = "Cox proportional-hazards model with PH assumption test."
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
            help="Coefficient frame with hazard ratios, CIs, and PH test.",
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
            help="Column indicating whether the event occurred (1) or censored (0).",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="formula",
            type_token="str",
            default=None,
            label="Formula",
            help="Patsy formula; None uses all other columns as predictors.",
            hints=ValidationHints(widget="text"),
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
        formula = values.get("formula")
        alpha = values.get("alpha")
        if alpha is None:
            alpha = 0.05
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('result')} = ef.stats.fit_survival("
                f"{ctx.in_var('frame')}, duration_col={duration_col!r}, "
                f"event_col={event_col!r}, formula={formula!r}, alpha={alpha!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        duration_col = cast(str, values.get("duration_col") or "")
        event_col = cast(str, values.get("event_col") or "")
        formula = cast("str | None", values.get("formula"))
        alpha_val = values.get("alpha")
        alpha = cast(float, alpha_val if alpha_val is not None else 0.05)
        return {
            "result": fit_survival(
                inputs["frame"],
                duration_col=duration_col,
                event_col=event_col,
                formula=formula,
                alpha=alpha,
            )
        }
