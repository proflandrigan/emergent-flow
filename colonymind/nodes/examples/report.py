"""
colonymind.nodes.examples.report
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``reports.generate_html_summary`` — a *transform* node
(1 in, 1 out).

Real, ydata-profiling-backed HTML summary (Epic 1, Story 8). ``execute``
calls ``colonymind.reports.generate_html_summary`` directly and the code
emitted by ``codegen`` calls the same wrapper via the ``cm.`` alias, so the
two paths are equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from colonymind.ir.common import Direction
from colonymind.ir.node import Node
from colonymind.reports import generate_html_summary

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from colonymind.codegen.context import CodegenContext


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
            default="Colony Mind Data Summary",
            label="Title",
            help="Title shown at the top of the report.",
            hints=ValidationHints(widget="text"),
        ),
    ]

    def _args(self, node: Node) -> str:
        values = {p.name: p.value for p in node.params}
        title = values.get("title", "Colony Mind Data Summary")
        if title is None:
            title = "Colony Mind Data Summary"
        return cast(str, title)

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        title = self._args(node)
        return CodeFragment(
            imports=["import colonymind as cm"],
            body=(
                f"{ctx.out_var('html')} = cm.reports.generate_html_summary("
                f"{ctx.in_var('frame')}, title={title!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        title = self._args(node)
        return {"html": generate_html_summary(inputs["frame"], title=title)}
