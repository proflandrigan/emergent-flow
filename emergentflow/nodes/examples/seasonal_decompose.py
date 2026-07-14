"""
emergentflow.nodes.examples.seasonal_decompose
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``timeseries.seasonal_decompose`` — trend/seasonal/residual decomposition
node.

Decomposes a time series into components via ``ef.timeseries.seasonal_decompose``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.ir.params import ParamValue
from emergentflow.timeseries import seasonal_decompose as seasonal_decompose_fn

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class SeasonalDecompose(NodeDefinition):
    """Decompose a time series into trend, seasonal, and residual components."""

    type = "timeseries.seasonal_decompose"
    version = 1
    family = "timeseries"
    label = "Seasonal Decompose"
    category = "Time Series"
    advisor_persona = "researcher"
    description = "Decompose a time series into trend, seasonal, and residual components."

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
            data_type="DecomposeResult",
            help="The decomposed time series components.",
        ),
    ]
    params = [
        ParamSpec(
            name="target",
            type_token="str",
            required=True,
            label="Target column",
            help="Column to decompose.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="model",
            type_token="str",
            default="additive",
            label="Model",
            help="Decomposition model type.",
            hints=ValidationHints(
                choices=cast("list[ParamValue]", ["additive", "multiplicative"]),
                widget="select",
            ),
        ),
        ParamSpec(
            name="period",
            type_token="int",
            required=True,
            label="Period",
            help="Seasonal period (number of observations per cycle).",
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
            "model": cast(str, values.get("model", "additive")),
            "period": cast(int, values.get("period")),
            "date_col": cast("str | None", values.get("date_col")),
        }

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        args = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('result')} = ef.timeseries.seasonal_decompose("
                f"{ctx.in_var('frame')}, target={args['target']!r}, "
                f"model={args['model']!r}, period={args['period']!r}, "
                f"date_col={args['date_col']!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        args = self._args(node)
        return {
            "result": seasonal_decompose_fn(
                inputs["frame"],
                target=args["target"],
                model=args["model"],
                period=args["period"],
                date_col=args["date_col"],
            )
        }
