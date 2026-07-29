"""
emergentflow.nodes.examples.cohort_retention
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``stats.cohort_retention`` — a *transform* node (1 in, 1 out).

Real, pandas-backed cohort retention analysis (Epic 16). ``execute`` calls
``emergentflow.stats.cohort_retention`` directly and the code emitted by ``codegen`` calls
the same wrapper via the ``ef.`` alias, so the two paths are equivalent by
construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.stats import cohort_retention

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class CohortRetention(NodeDefinition):
    """Group users by their first-activity period and track retention over time."""

    type = "stats.cohort_retention"
    version = 1
    family = "stats"
    label = "Cohort Retention"
    category = "Statistics"
    description = "Cohort retention analysis over a user activity log."

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame containing the user and date columns.",
        ),
        PortSpec(
            name="result",
            direction=Direction.OUT,
            data_type="CohortRetentionResult",
            help="Inspectable tidy + wide cohort retention tables.",
        ),
    ]
    params = [
        ParamSpec(
            name="user_col",
            type_token="str",
            required=True,
            label="User column",
            help="Column identifying each user.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="date_col",
            type_token="str",
            required=True,
            label="Date column",
            help="Column with each row's activity timestamp.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="period",
            type_token="str",
            default="M",
            label="Period",
            help="Calendar period granularity for cohorts.",
            hints=ValidationHints(choices=["D", "W", "M"], widget="select"),
        ),
    ]

    def _args(self, node: Node) -> tuple[str, str, str]:
        values = {p.name: p.value for p in node.params}
        user_col = values.get("user_col")
        date_col = values.get("date_col")
        period = values.get("period", "M")
        if period is None:
            period = "M"
        return cast(str, user_col), cast(str, date_col), cast(str, period)

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        user_col, date_col, period = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('result')} = ef.stats.cohort_retention({ctx.in_var('frame')}, "
                f"user_col={user_col!r}, date_col={date_col!r}, period={period!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        user_col, date_col, period = self._args(node)
        return {
            "result": cohort_retention(
                inputs["frame"],
                user_col=user_col,
                date_col=date_col,
                period=period,
            )
        }
