"""
emergentflow.nodes.examples.report
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``reports.generate_html_summary`` — a *transform* node
(1 in, 1 out).

Real, ydata-profiling-backed HTML summary (Epic 1, Story 8). ``execute``
calls ``emergentflow.reports.generate_html_summary`` directly and the code
emitted by ``codegen`` calls the same wrapper via the ``ef.`` alias, so the
two paths are equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.reports import generate_html_summary

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class GenerateHtmlSummary(NodeDefinition):
    """Generate a self-contained HTML profiling report for a DataFrame."""

    type = "reports.generate_html_summary"
    version = 2
    family = "reports"
    label = "HTML Summary"
    category = "Reporting"
    description = "Generate an HTML profiling report summarising a DataFrame."

    ports = [
        PortSpec(
            name="frame",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The DataFrame to profile.",
        ),
        PortSpec(
            name="html",
            direction=Direction.OUT,
            data_type="HTML",
            help="The rendered HTML profiling report.",
        ),
    ]
    params = [
        ParamSpec(
            name="title",
            type_token="str",
            default="Emergent Flow Data Summary",
            label="Title",
            help="Title shown at the top of the report.",
            hints=ValidationHints(widget="text"),
        ),
    ]

    def _args(self, node: Node) -> str:
        values = {p.name: p.value for p in node.params}
        title = values.get("title", "Emergent Flow Data Summary")
        if title is None:
            title = "Emergent Flow Data Summary"
        return cast(str, title)

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        title = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('html')} = ef.reports.generate_html_summary("
                f"{ctx.in_var('frame')}, title={title!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        title = self._args(node)
        return {"html": generate_html_summary(inputs["frame"], title=title)}
