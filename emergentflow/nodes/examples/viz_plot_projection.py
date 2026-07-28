"""
emergentflow.nodes.examples.viz_plot_projection
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``viz.plot_projection`` — a *transform* node (1 in, 1 out).

Renders a 2-D dimensionality-reduction projection (e.g. the output of ``ef.ml.reduce_dimensions``)
as a scatter plot, optionally colored by a label column. ``execute`` calls
``emergentflow.viz.plot_projection`` directly and the code emitted by ``codegen`` calls the same
wrapper via the ``ef.`` alias, so the two paths are equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.viz import plot_projection

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class VizPlotProjection(NodeDefinition):
    """Render a 2-D projection scatter plot, optionally colored by a label column."""

    type = "viz.plot_projection"
    version = 1
    family = "viz"
    label = "Plot Projection"
    category = "Visualization"
    description = "Render a 2-D dimensionality-reduction projection as a scatter plot."

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame containing the projection coordinate columns.",
        ),
        PortSpec(
            name="plot",
            direction=Direction.OUT,
            data_type="PlotSpec",
            help="The rendered projection scatter plot as a JSON-native PlotSpec.",
        ),
    ]
    params = [
        ParamSpec(
            name="x_col",
            type_token="str",
            default="component_1",
            label="X column",
            help="Column to plot on the x-axis.",
        ),
        ParamSpec(
            name="y_col",
            type_token="str",
            default="component_2",
            label="Y column",
            help="Column to plot on the y-axis.",
        ),
        ParamSpec(
            name="color_col",
            type_token="str",
            default=None,
            required=False,
            label="Color column",
            help="Optional column to color points by (e.g. a cluster/class label).",
        ),
    ]

    def _args(self, node: Node) -> tuple[str, str, str | None]:
        values = {p.name: p.value for p in node.params}
        x_col = values.get("x_col", "component_1")
        if x_col is None:
            x_col = "component_1"
        y_col = values.get("y_col", "component_2")
        if y_col is None:
            y_col = "component_2"
        color_col = values.get("color_col")
        return cast(str, x_col), cast(str, y_col), cast("str | None", color_col)

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        x_col, y_col, color_col = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('plot')} = ef.viz.plot_projection({ctx.in_var('frame')}, "
                f"x_col={x_col!r}, y_col={y_col!r}, color_col={color_col!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        x_col, y_col, color_col = self._args(node)
        return {
            "plot": plot_projection(
                inputs["frame"],
                x_col=x_col,
                y_col=y_col,
                color_col=color_col,
            )
        }
