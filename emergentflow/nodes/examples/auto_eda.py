"""
emergentflow.nodes.examples.auto_eda
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``stats.auto_eda`` — the one-shot exploratory-data-analysis node (Epic 12,
Story 11).

Runs a whole EDA pass in one node and fans the result out onto typed OUT ports: a pass-through of
the input ``frame`` (so the node can sit inline in a pipeline), the ``profile``/``missingness``/
``correlation`` tidy frames, and three ``PlotSpec`` plots (per-column distributions, correlation
heatmap, co-missingness heatmap). ``execute`` calls ``emergentflow.stats.auto_eda`` once and
unpacks its :class:`~emergentflow.stats.eda.AutoEdaResult`; ``codegen`` emits the same single call
into a private bundle variable and unpacks the identical fields, so the two paths are equivalent
by construction (ADR 0002) and the bundle is never computed more than once.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.stats import auto_eda

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class AutoEda(NodeDefinition):
    """Run a one-shot EDA pass: summary frames + curated plots, plus a frame pass-through."""

    type = "stats.auto_eda"
    version = 1
    family = "stats"
    label = "Auto EDA"
    category = "Statistics"
    description = "One-shot exploratory data analysis: summary frames + curated plots."

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame to analyze.",
        ),
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="The input DataFrame, passed through unchanged so this node can sit inline.",
        ),
        PortSpec(
            name="profile",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="Per-column profile (dtype, missingness, cardinality, skew/kurtosis).",
        ),
        PortSpec(
            name="missingness",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="Per-column null counts and percentages.",
        ),
        PortSpec(
            name="correlation",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="Pairwise correlation matrix (tidy).",
        ),
        PortSpec(
            name="distribution_plot",
            direction=Direction.OUT,
            data_type="PlotSpec",
            help="Per-column distribution histograms (faceted).",
        ),
        PortSpec(
            name="correlation_heatmap",
            direction=Direction.OUT,
            data_type="PlotSpec",
            help="Correlation heatmap.",
        ),
        PortSpec(
            name="missingness_plot",
            direction=Direction.OUT,
            data_type="PlotSpec",
            help="Co-missingness heatmap (which columns tend to go missing together).",
        ),
    ]
    params = [
        ParamSpec(
            name="columns",
            type_token="list[str]",
            default=None,
            label="Columns",
            help="Columns to analyze; empty/unset analyzes all columns.",
            hints=ValidationHints(widget="column"),
        ),
    ]

    def _args(self, node: Node) -> tuple[list[str] | None]:
        values = {p.name: p.value for p in node.params}
        return (cast("list[str] | None", values.get("columns")),)

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        (columns,) = self._args(node)
        frame_in = ctx.in_var("frame")
        # A private, collision-free bundle name derived from an OUT var (already globally unique
        # per compile), so ``auto_eda`` runs exactly once and every OUT port reads the same bundle.
        bundle = f"_{ctx.out_var('profile')}_bundle"
        lines = [
            f"{bundle} = ef.stats.auto_eda({frame_in}, columns={columns!r})",
            f"{ctx.out_var('frame')} = {frame_in}",
            f"{ctx.out_var('profile')} = {bundle}.frames['profile']",
            f"{ctx.out_var('missingness')} = {bundle}.frames['missingness']",
            f"{ctx.out_var('correlation')} = {bundle}.frames['correlation']",
            f"{ctx.out_var('distribution_plot')} = {bundle}.plots['distributions']",
            f"{ctx.out_var('correlation_heatmap')} = {bundle}.plots['correlation_heatmap']",
            f"{ctx.out_var('missingness_plot')} = {bundle}.plots['missingness']",
        ]
        return CodeFragment(imports=["import emergentflow as ef"], body="\n".join(lines))

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        (columns,) = self._args(node)
        result = auto_eda(inputs["frame"], columns=columns)
        return {
            "frame": inputs["frame"],
            "profile": result.frames["profile"],
            "missingness": result.frames["missingness"],
            "correlation": result.frames["correlation"],
            "distribution_plot": result.plots["distributions"],
            "correlation_heatmap": result.plots["correlation_heatmap"],
            "missingness_plot": result.plots["missingness"],
        }
