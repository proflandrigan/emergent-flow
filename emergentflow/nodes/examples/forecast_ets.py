"""
emergentflow.nodes.examples.forecast_ets
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``timeseries.forecast_ets`` — Holt-Winters exponential smoothing node.

Fits a Holt-Winters exponential smoothing model via ``ef.timeseries.forecast_ets`` and
forecasts future values.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.ir.params import ParamValue
from emergentflow.timeseries import forecast_ets

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class ForecastEts(NodeDefinition):
    """Fit a Holt-Winters exponential smoothing model and forecast (statsmodels)."""

    type = "timeseries.forecast_ets"
    version = 1
    family = "timeseries"
    label = "Forecast ETS"
    category = "Time Series"
    advisor_persona = "researcher"
    description = "Fit a Holt-Winters exponential smoothing model and forecast (statsmodels)."

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame with the target time series column.",
        ),
        PortSpec(
            name="result",
            direction=Direction.OUT,
            data_type="ForecastResult",
            help="The fitted model and forecast.",
        ),
    ]
    params = [
        ParamSpec(
            name="target",
            type_token="str",
            required=True,
            label="Target column",
            help="Column containing the time series to forecast.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="trend",
            type_token="str",
            default="add",
            label="Trend",
            help="Trend component type.",
            hints=ValidationHints(
                choices=cast("list[ParamValue]", ["add", "mul", None]),
                widget="select",
            ),
        ),
        ParamSpec(
            name="seasonal",
            type_token="str",
            default=None,
            label="Seasonal",
            help="Seasonal component type.",
            hints=ValidationHints(
                choices=cast("list[ParamValue]", ["add", "mul", None]),
                widget="select",
            ),
        ),
        ParamSpec(
            name="seasonal_periods",
            type_token="int",
            default=None,
            label="Seasonal periods",
            help="Number of periods in a seasonal cycle. Required when seasonal is set.",
            hints=ValidationHints(min=2),
        ),
        ParamSpec(
            name="horizon",
            type_token="int",
            default=10,
            label="Forecast horizon",
            help="Number of steps ahead to forecast.",
            hints=ValidationHints(min=1),
        ),
        ParamSpec(
            name="date_col",
            type_token="str",
            default=None,
            label="Date column",
            help="Optional datetime column to use as the index.",
            hints=ValidationHints(widget="column"),
        ),
    ]

    def _args(self, node: Node) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        return {
            "target": cast(str, values.get("target")),
            "trend": cast("str | None", values.get("trend", "add")),
            "seasonal": cast("str | None", values.get("seasonal")),
            "seasonal_periods": cast("int | None", values.get("seasonal_periods")),
            "horizon": cast(int, values.get("horizon", 10)),
            "date_col": cast("str | None", values.get("date_col")),
        }

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        args = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('result')} = ef.timeseries.forecast_ets("
                f"{ctx.in_var('frame')}, target={args['target']!r}, "
                f"trend={args['trend']!r}, seasonal={args['seasonal']!r}, "
                f"seasonal_periods={args['seasonal_periods']!r}, "
                f"horizon={args['horizon']!r}, date_col={args['date_col']!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        args = self._args(node)
        return {
            "result": forecast_ets(
                inputs["frame"],
                target=args["target"],
                trend=args["trend"],
                seasonal=args["seasonal"],
                seasonal_periods=args["seasonal_periods"],
                horizon=args["horizon"],
                date_col=args["date_col"],
            )
        }
