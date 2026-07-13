"""
emergentflow.nodes.examples.viz_plot
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``viz.plot`` — the "viz.plot" archetype node (Epic 12, Story 8).

Renders a curated, allow-listed chart (any chart registered in
``emergentflow.viz.registry``) from an input DataFrame, returning a JSON-native ``PlotSpec``.
The ``chart`` choice list is computed at import time from the live chart registry, so it grows
automatically as more charts are curated into the allow-list (no edits needed here). ``execute``
calls ``emergentflow.viz.plot`` directly and the code emitted by ``codegen`` calls the same
wrapper via the ``ef.`` alias, so the two paths are equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.ir.params import ParamValue
from emergentflow.viz import plot as viz_plot
from emergentflow.viz.registry import known_chart_keys

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class VizPlot(NodeDefinition):
    """Render a curated, allow-listed chart from an input DataFrame."""

    type = "viz.plot"
    version = 1
    family = "viz"
    label = "Plot"
    category = "Visualization"
    description = "Render a curated, allow-listed chart (plotly.express) from a DataFrame."

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame to chart.",
        ),
        PortSpec(
            name="plot",
            direction=Direction.OUT,
            data_type="PlotSpec",
            help="The rendered chart as a JSON-native PlotSpec.",
        ),
    ]
    params = [
        ParamSpec(
            name="chart",
            type_token="str",
            required=True,
            label="Chart",
            help="Which allow-listed chart type to render.",
            hints=ValidationHints(
                choices=cast("list[ParamValue]", known_chart_keys()),
                widget="select",
            ),
        ),
        ParamSpec(
            name="encoding",
            type_token="dict[str, any]",
            default={},
            label="Encoding",
            help="Column-reference kwargs for the chosen chart (x/y/color/facet_row/...).",
        ),
        ParamSpec(
            name="options",
            type_token="dict[str, any]",
            default={},
            label="Options",
            help="Non-column-reference kwargs for the chosen chart (trendline/log_x/nbins/...).",
        ),
    ]

    def _args(self, node: Node) -> tuple[str, dict[str, Any], dict[str, Any]]:
        values = {p.name: p.value for p in node.params}
        chart = cast(str, values.get("chart"))
        encoding = cast("dict[str, Any]", values.get("encoding") or {})
        options = cast("dict[str, Any]", values.get("options") or {})
        return chart, encoding, options

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        chart, encoding, options = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('plot')} = ef.viz.plot("
                f"{ctx.in_var('frame')}, chart={chart!r}, encoding={encoding!r}, "
                f"options={options!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        chart, encoding, options = self._args(node)
        return {"plot": viz_plot(inputs["frame"], chart=chart, encoding=encoding, options=options)}
