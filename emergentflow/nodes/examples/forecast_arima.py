"""
emergentflow.nodes.examples.forecast_arima
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``timeseries.forecast_arima`` — SARIMAX forecasting node.

Fits a SARIMAX model via ``ef.timeseries.forecast_arima`` and forecasts future values.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.timeseries import forecast_arima

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class ForecastArima(NodeDefinition):
    """Fit a SARIMAX model and forecast future values (statsmodels)."""

    type = "timeseries.forecast_arima"
    version = 1
    family = "timeseries"
    label = "Forecast ARIMA"
    category = "Time Series"
    advisor_persona = "researcher"
    description = "Fit a SARIMAX model and forecast future values (statsmodels)."

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
            name="order",
            type_token="list[int]",
            default=[1, 0, 0],
            label="Order (p,d,q)",
            help="ARIMA order: (p, d, q).",
        ),
        ParamSpec(
            name="seasonal_order",
            type_token="list[int]",
            default=[0, 0, 0, 0],
            label="Seasonal order (P,D,Q,s)",
            help="Seasonal ARIMA order: (P, D, Q, s).",
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
        order = tuple(cast("list[int]", values.get("order") or [1, 0, 0]))
        seasonal_order = tuple(cast("list[int]", values.get("seasonal_order") or [0, 0, 0, 0]))
        return {
            "target": cast(str, values.get("target")),
            "order": order,
            "seasonal_order": seasonal_order,
            "horizon": cast(int, values.get("horizon", 10)),
            "date_col": cast("str | None", values.get("date_col")),
        }

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        args = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('result')} = ef.timeseries.forecast_arima("
                f"{ctx.in_var('frame')}, target={args['target']!r}, "
                f"order={args['order']!r}, seasonal_order={args['seasonal_order']!r}, "
                f"horizon={args['horizon']!r}, date_col={args['date_col']!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        args = self._args(node)
        return {
            "result": forecast_arima(
                inputs["frame"],
                target=args["target"],
                order=args["order"],
                seasonal_order=args["seasonal_order"],
                horizon=args["horizon"],
                date_col=args["date_col"],
            )
        }
