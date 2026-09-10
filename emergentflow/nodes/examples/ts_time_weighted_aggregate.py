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
    """Append recency-weighted aggregate columns (positional or date-aware decay)."""

    type = "timeseries.time_weighted_aggregate"
    version = 3
    family = "timeseries"
    label = "Time-Weighted Aggregate"
    category = "Time Series"
    description = "Append recency-weighted aggregate columns (positional or date-aware decay)."

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
            help="Decay method for positional weighting; ignored when half_life is set.",
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
        ParamSpec(
            name="half_life",
            type_token="float",
            default=None,
            label="Half-life",
            help="Half-life in `unit` units for date-aware decay: an observation loses half its "
            "weight every half_life units of elapsed time. Unset uses the positional weighting.",
            hints=ValidationHints(min=1e-9, widget="number"),
        ),
        ParamSpec(
            name="unit",
            type_token="str",
            default="D",
            label="Time unit",
            help="Pandas offset unit for the half-life (W, D, h, min, s, ...).",
            hints=ValidationHints(
                choices=cast("list[ParamValue]", ["W", "D", "h", "min", "s", "ms", "us", "ns"]),
                widget="select",
            ),
        ),
        ParamSpec(
            name="anchor",
            type_token="str",
            default=None,
            label="Anchor date",
            help="Optional as-of cutoff: a column name (each row's own cutoff date) or a fixed "
            "timestamp. Rows dated after the cutoff are excluded from the mean.",
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="group_col",
            type_token="str",
            default=None,
            label="Group column",
            help="Partition the weighting by this column (per-subject decay).",
            hints=ValidationHints(widget="column"),
        ),
    ]

    def _args(self, node: Node) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        return {
            "columns": cast("list[str]", values.get("columns")),
            "date_col": cast(str, values.get("date_col")),
            "decay": cast(str, values.get("decay", "linear")),
            "window": cast("int | None", values.get("window")),
            "half_life": cast("float | None", values.get("half_life")),
            "unit": cast(str, values.get("unit", "D")),
            "anchor": cast("str | None", values.get("anchor") or None),
            "group_col": cast("str | None", values.get("group_col") or None),
        }

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        args = self._args(node)
        has_half_life = args["half_life"] is not None
        codegen_half_life = f", half_life={args['half_life']!r}" if has_half_life else ""
        codegen_unit = f", unit={args['unit']!r}" if (has_half_life and args["unit"] != "D") else ""
        codegen_anchor = f", anchor={args['anchor']!r}" if args["anchor"] is not None else ""
        codegen_group = (
            f", group_col={args['group_col']!r}" if args["group_col"] is not None else ""
        )
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('result')} = ef.timeseries.time_weighted_aggregate("
                f"{ctx.in_var('frame')}, columns={args['columns']!r}, "
                f"date_col={args['date_col']!r}, decay={args['decay']!r}, "
                f"window={args['window']!r}{codegen_half_life}{codegen_unit}"
                f"{codegen_anchor}{codegen_group})"
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
                half_life=args["half_life"],
                unit=args["unit"],
                anchor=args["anchor"],
                group_col=args["group_col"],
            )
        }
