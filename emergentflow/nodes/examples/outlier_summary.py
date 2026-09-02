"""
emergentflow.nodes.examples.outlier_summary
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``stats.outlier_summary`` — a *statistics* node (1 in, 1 out).

Reports the outlier bounds actually applied by ``ef.clean.detect_outliers``,
one row per numeric column. ``execute`` calls ``emergentflow.stats.outlier_summary``
directly and the code emitted by ``codegen`` calls the same wrapper via the
``ef.`` alias, so the two paths are equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.clean.outliers import OUTLIER_METHODS
from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.ir.params import ParamValue
from emergentflow.stats import outlier_summary

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class OutlierSummary(NodeDefinition):
    """Report per-column outlier bounds and hit counts (companion to Detect Outliers)."""

    type = "stats.outlier_summary"
    version = 2
    family = "stats"
    label = "Outlier Summary"
    category = "Statistics"
    description = (
        "Report the outlier bounds actually applied by Detect Outliers, one row per numeric column."
    )

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame whose numeric columns should be summarized.",
        ),
        PortSpec(
            name="summary",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="Per-column outlier bounds and hit counts as a tidy DataFrame.",
        ),
    ]
    params = [
        ParamSpec(
            name="columns",
            type_token="list[str]",
            default=None,
            label="Columns",
            help="Columns to summarize; empty/unset summarizes all numeric columns.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="method",
            type_token="str",
            default="zscore",
            label="Method",
            help="Which outlier rule to report bounds for.",
            hints=ValidationHints(
                choices=cast("list[ParamValue]", list(OUTLIER_METHODS)),
                widget="select",
            ),
        ),
        ParamSpec(
            name="threshold",
            type_token="float",
            default=3.0,
            label="Threshold",
            help="Rule cutoff, per method: SDs > 0 for zscore/modified_zscore, k > 0 for "
            "iqr, a tail quantile in (0, 0.5) for quantile, a fraction in (0, 1) for "
            "percent. The 3.0 default suits the first three; lower it when switching "
            "to quantile or percent.",
            hints=ValidationHints(widget="number", min=0),
        ),
        ParamSpec(
            name="by",
            type_token="list[str]",
            default=None,
            label="Group by",
            help="Report outlier bounds within each group of these columns; "
            "unset uses the whole frame.",
            hints=ValidationHints(widget="column"),
        ),
    ]

    def _args(self, node: Node) -> tuple[list[str] | None, str, float, list[str] | None]:
        values = {p.name: p.value for p in node.params}
        columns = values.get("columns")
        method = values.get("method") or "zscore"
        threshold = values.get("threshold")
        if threshold is None:
            threshold = 3.0
        by = values.get("by")
        return (
            cast("list[str] | None", columns),
            cast(str, method),
            cast(float, threshold),
            cast("list[str] | None", by),
        )

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        columns, method, threshold, by = self._args(node)
        codegen_by = f", by={by!r}" if by else ""
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('summary')} = ef.stats.outlier_summary("
                f"{ctx.in_var('frame')}, columns={columns!r}, method={method!r}, "
                f"threshold={threshold!r}{codegen_by})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        columns, method, threshold, by = self._args(node)
        return {
            "summary": outlier_summary(
                inputs["frame"], columns=columns, method=method, threshold=threshold, by=by
            )
        }
