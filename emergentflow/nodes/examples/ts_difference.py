"""
emergentflow.nodes.examples.ts_difference
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``timeseries.difference`` — first/seasonal differencing node.

Appends differenced columns via ``ef.timeseries.difference``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.timeseries import difference

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class TsDifference(NodeDefinition):
    """Append first-difference and optional seasonal-difference columns."""

    type = "timeseries.difference"
    version = 1
    family = "timeseries"
    label = "Difference"
    category = "Time Series"
    description = "Append first-difference and optional seasonal-difference columns."

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
            help="The augmented DataFrame with differenced columns.",
        ),
    ]
    params = [
        ParamSpec(
            name="columns",
            type_token="list[str]",
            required=True,
            label="Columns",
            help="Columns to difference.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="periods",
            type_token="int",
            default=1,
            label="Periods",
            help="Number of periods to difference by.",
            hints=ValidationHints(min=1),
        ),
        ParamSpec(
            name="seasonal_periods",
            type_token="int",
            default=None,
            label="Seasonal periods",
            help="Additional seasonal differencing period.",
            hints=ValidationHints(min=1),
        ),
    ]

    def _args(self, node: Node) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        return {
            "columns": cast("list[str]", values.get("columns")),
            "periods": cast(int, values.get("periods", 1)),
            "seasonal_periods": cast("int | None", values.get("seasonal_periods")),
        }

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        args = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('result')} = ef.timeseries.difference("
                f"{ctx.in_var('frame')}, columns={args['columns']!r}, "
                f"periods={args['periods']!r}, "
                f"seasonal_periods={args['seasonal_periods']!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        args = self._args(node)
        return {
            "result": difference(
                inputs["frame"],
                columns=args["columns"],
                periods=args["periods"],
                seasonal_periods=args["seasonal_periods"],
            )
        }
