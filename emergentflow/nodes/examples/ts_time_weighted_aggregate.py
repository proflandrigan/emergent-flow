"""
emergentflow.nodes.examples.ts_time_weighted_aggregate
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``timeseries.time_weighted_aggregate`` — recency-weighted aggregate node.

Appends time-weighted aggregate columns via ``ef.timeseries.time_weighted_aggregate``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.ir.params import ParamValue
from emergentflow.timeseries import time_weighted_aggregate

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ColumnEffect, ColumnEffectKind, ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class TsTimeWeightedAggregate(NodeDefinition):
    """Append recency-weighted aggregate columns (linear or exponential decay)."""

    type = "timeseries.time_weighted_aggregate"
    version = 1
    family = "timeseries"
    label = "Time-Weighted Aggregate"
    category = "Time Series"
    description = "Append recency-weighted aggregate columns (linear or exponential decay)."

    column_effect = ColumnEffect(kind=ColumnEffectKind.PASSTHROUGH)

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame.",
        ),
        PortSpec(
            name="result",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="The augmented DataFrame with time-weighted aggregate columns.",
        ),
    ]
    params = [
        ParamSpec(
            name="columns",
            type_token="list[str]",
            required=True,
            label="Columns",
            help="Columns to aggregate.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="date_col",
            type_token="str",
            required=True,
            label="Date column",
            help="Column establishing chronological order.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="decay",
            type_token="str",
            default="linear",
            label="Decay",
            help="Decay method for recency weighting.",
            hints=ValidationHints(
                choices=cast("list[ParamValue]", ["linear", "exponential"]),
                widget="select",
            ),
        ),
        ParamSpec(
            name="window",
            type_token="int",
            default=None,
            label="Window",
            help="Rolling window size. If unset, uses all preceding rows.",
            hints=ValidationHints(min=1),
        ),
    ]

    def _args(self, node: Node) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        return {
            "columns": cast("list[str]", values.get("columns")),
            "date_col": cast(str, values.get("date_col")),
            "decay": cast(str, values.get("decay", "linear")),
            "window": cast("int | None", values.get("window")),
        }

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        args = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('result')} = ef.timeseries.time_weighted_aggregate("
                f"{ctx.in_var('frame')}, columns={args['columns']!r}, "
                f"date_col={args['date_col']!r}, decay={args['decay']!r}, "
                f"window={args['window']!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        args = self._args(node)
        return {
            "result": time_weighted_aggregate(
                inputs["frame"],
                columns=args["columns"],
                date_col=args["date_col"],
                decay=args["decay"],
                window=args["window"],
            )
        }
