"""
emergentflow.nodes.examples.distribution_summary
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``stats.distribution_summary`` — a *transform* node (1 in, 1 out).

Real, pandas-backed per-numeric-column quantile/spread summary (Epic 12,
Story 11). ``execute`` calls ``emergentflow.stats.distribution_summary``
directly and the code emitted by ``codegen`` calls the same wrapper via the
``ef.`` alias, so the two paths are equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.stats import distribution_summary

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class DistributionSummary(NodeDefinition):
    """Per-numeric-column quantiles and spread (min/p05/p25/p50/p75/p95/max/IQR)."""

    type = "stats.distribution_summary"
    version = 1
    family = "stats"
    label = "Distribution Summary"
    category = "Statistics"
    description = "Per-numeric-column quantiles and spread (min/p05/p25/p50/p75/p95/max/IQR)."

    ports = [
        PortSpec(
            name="frame",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame whose numeric columns should be summarized.",
        ),
        PortSpec(
            name="summary",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="Per-numeric-column distribution summary as a tidy DataFrame.",
        ),
    ]
    params = [
        ParamSpec(
            name="columns",
            type_token="list[str]",
            default=None,
            label="Columns",
            help="Columns to summarize; empty/unset summarizes all numeric columns.",
            hints=ValidationHints(widget="text"),
        ),
    ]

    def _args(self, node: Node) -> tuple[list[str] | None]:
        values = {p.name: p.value for p in node.params}
        columns = values.get("columns")
        return (cast("list[str] | None", columns),)

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        (columns,) = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('summary')} = ef.stats.distribution_summary("
                f"{ctx.in_var('frame')}, columns={columns!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        (columns,) = self._args(node)
        return {"summary": distribution_summary(inputs["frame"], columns=columns)}
