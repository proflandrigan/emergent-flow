"""
emergentflow.nodes.examples.ts_rolling_aggregate
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``timeseries.rolling_aggregate`` — rolling-window aggregate node.

Appends rolling-window aggregate columns via ``ef.timeseries.rolling_aggregate``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.ir.params import ParamValue
from emergentflow.timeseries import rolling_aggregate

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class TsRollingAggregate(NodeDefinition):
    """Append rolling-window aggregate columns (mean, sum, std, min, max)."""

    type = "timeseries.rolling_aggregate"
    version = 1
    family = "timeseries"
    label = "Rolling Aggregate"
    category = "Time Series"
    description = "Append rolling-window aggregate columns (mean, sum, std, min, max)."

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
            help="The augmented DataFrame with rolling aggregate columns.",
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
            name="window",
            type_token="int",
            required=True,
            label="Window",
            help="Rolling window size.",
            hints=ValidationHints(min=1),
        ),
        ParamSpec(
            name="agg",
            type_token="str",
            default="mean",
            label="Aggregation",
            help="Aggregation function.",
            hints=ValidationHints(
                choices=cast("list[ParamValue]", ["mean", "sum", "std", "min", "max"]),
                widget="select",
            ),
        ),
        ParamSpec(
            name="min_periods",
            type_token="int",
            default=None,
            label="Min periods",
            help="Minimum number of observations required. Defaults to window size.",
            hints=ValidationHints(min=1),
        ),
    ]

    def _args(self, node: Node) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        return {
            "columns": cast("list[str]", values.get("columns")),
            "window": cast(int, values.get("window")),
            "agg": cast(str, values.get("agg", "mean")),
            "min_periods": cast("int | None", values.get("min_periods")),
        }

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        args = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('result')} = ef.timeseries.rolling_aggregate("
                f"{ctx.in_var('frame')}, columns={args['columns']!r}, "
                f"window={args['window']!r}, agg={args['agg']!r}, "
                f"min_periods={args['min_periods']!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        args = self._args(node)
        return {
            "result": rolling_aggregate(
                inputs["frame"],
                columns=args["columns"],
                window=args["window"],
                agg=args["agg"],
                min_periods=args["min_periods"],
            )
        }
