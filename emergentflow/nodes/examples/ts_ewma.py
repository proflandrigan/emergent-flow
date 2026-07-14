"""
emergentflow.nodes.examples.ts_ewma
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``timeseries.ewma`` — exponentially-weighted moving-average node.

Appends EWMA columns via ``ef.timeseries.ewma``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.timeseries import ewma

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class TsEwma(NodeDefinition):
    """Append exponentially-weighted moving-average columns."""

    type = "timeseries.ewma"
    version = 1
    family = "timeseries"
    label = "EWMA"
    category = "Time Series"
    description = "Append exponentially-weighted moving-average columns."

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
            help="The augmented DataFrame with EWMA columns.",
        ),
    ]
    params = [
        ParamSpec(
            name="columns",
            type_token="list[str]",
            required=True,
            label="Columns",
            help="Columns to compute EWMA for.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="span",
            type_token="float",
            default=None,
            label="Span",
            help="Decay in terms of span.",
            hints=ValidationHints(min=0),
        ),
        ParamSpec(
            name="halflife",
            type_token="float",
            default=None,
            label="Halflife",
            help="Decay in terms of halflife.",
            hints=ValidationHints(min=0),
        ),
        ParamSpec(
            name="alpha",
            type_token="float",
            default=None,
            label="Alpha",
            help="Smoothing factor (0 < alpha <= 1).",
            hints=ValidationHints(min=0, max=1),
        ),
        ParamSpec(
            name="suffix",
            type_token="str",
            default="_ewma",
            label="Suffix",
            help="Suffix appended to new column names.",
        ),
    ]

    def _args(self, node: Node) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        return {
            "columns": cast("list[str]", values.get("columns")),
            "span": cast("float | None", values.get("span")),
            "halflife": cast("float | None", values.get("halflife")),
            "alpha": cast("float | None", values.get("alpha")),
            "suffix": cast(str, values.get("suffix", "_ewma")),
        }

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        args = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('result')} = ef.timeseries.ewma("
                f"{ctx.in_var('frame')}, columns={args['columns']!r}, "
                f"span={args['span']!r}, halflife={args['halflife']!r}, "
                f"alpha={args['alpha']!r}, suffix={args['suffix']!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        args = self._args(node)
        return {
            "result": ewma(
                inputs["frame"],
                columns=args["columns"],
                span=args["span"],
                halflife=args["halflife"],
                alpha=args["alpha"],
                suffix=args["suffix"],
            )
        }
