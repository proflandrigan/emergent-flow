"""
emergentflow.nodes.examples.ts_lag_features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``timeseries.lag_features`` — lagged feature columns node.

Appends lagged columns via ``ef.timeseries.lag_features``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.timeseries import lag_features

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ColumnEffect, ColumnEffectKind, ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class TsLagFeatures(NodeDefinition):
    """Create lagged feature columns for time series data."""

    type = "timeseries.lag_features"
    version = 1
    family = "timeseries"
    label = "Lag Features"
    category = "Time Series"
    description = "Create lagged feature columns for time series data."

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
            help="The augmented DataFrame with lag columns.",
        ),
    ]
    params = [
        ParamSpec(
            name="columns",
            type_token="list[str]",
            required=True,
            label="Columns",
            help="Columns to create lags for.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="lags",
            type_token="list[int]",
            required=True,
            label="Lags",
            help="List of lag periods (e.g. [1, 2, 3]).",
        ),
    ]

    def _args(self, node: Node) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        return {
            "columns": cast("list[str]", values.get("columns")),
            "lags": cast("list[int]", values.get("lags")),
        }

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        args = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('result')} = ef.timeseries.lag_features("
                f"{ctx.in_var('frame')}, columns={args['columns']!r}, "
                f"lags={args['lags']!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        args = self._args(node)
        return {
            "result": lag_features(
                inputs["frame"],
                columns=args["columns"],
                lags=args["lags"],
            )
        }
