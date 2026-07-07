"""
emergentflow.nodes.examples.viz_plot_acf
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``viz.plot_acf`` — a model-aware plot node (Epic 12, Story 9).

Renders an ACF or PACF bar plot of a fitted ``StatsModel``'s residuals. ``execute`` calls
``emergentflow.viz.plot_acf`` directly and the code emitted by ``codegen`` calls the same
wrapper via the ``ef.`` alias, so the two paths are equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.viz import plot_acf

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class VizPlotAcf(NodeDefinition):
    """Render an ACF or PACF plot of a fitted statistical model's residuals."""

    type = "viz.plot_acf"
    version = 1
    family = "viz"
    label = "Plot ACF/PACF"
    category = "Visualization"
    description = "Render an ACF or PACF bar plot of a fitted StatsModel's residuals."

    ports = [
        PortSpec(
            name="model",
            direction=Direction.IN,
            data_type="StatsModel",
            help="The fitted statistical model to plot residual autocorrelation for.",
        ),
        PortSpec(
            name="plot",
            direction=Direction.OUT,
            data_type="PlotSpec",
            help="The rendered ACF/PACF plot as a JSON-native PlotSpec.",
        ),
    ]
    params = [
        ParamSpec(
            name="kind",
            type_token="str",
            default="acf",
            label="Kind",
            help="Whether to plot the autocorrelation (acf) or partial autocorrelation (pacf).",
            hints=ValidationHints(choices=["acf", "pacf"], widget="select"),
        ),
        ParamSpec(
            name="nlags",
            type_token="int",
            default=20,
            label="Max lags",
            help="Maximum lag to plot (clamped to the residual series length if too large).",
        ),
    ]

    def _args(self, node: Node) -> tuple[str, int]:
        values = {p.name: p.value for p in node.params}
        kind = cast(str, values.get("kind") or "acf")
        nlags = cast(int, values.get("nlags") if values.get("nlags") is not None else 20)
        return kind, nlags

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        kind, nlags = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('plot')} = ef.viz.plot_acf("
                f"{ctx.in_var('model')}, kind={kind!r}, nlags={nlags!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        kind, nlags = self._args(node)
        return {"plot": plot_acf(inputs["model"], kind=kind, nlags=nlags)}
