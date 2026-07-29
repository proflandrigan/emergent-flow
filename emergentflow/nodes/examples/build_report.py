"""
emergentflow.nodes.examples.build_report
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``research.build_report`` -- composes a variadic ``Cardinality.MANY`` IN port
of upstream artifacts (DataFrames, PlotSpec figures, model-summary dataclasses, HTML/markdown
strings -- including a ``reports.generate_html_summary`` node's HTML output, which this node
supersedes/absorbs as an ordinary section input rather than the sole report surface) into one
``Report`` (Epic 16, Story 16). ``execute`` calls ``emergentflow.research.build_report`` (via
``emergentflow.research.sections_from_values`` for the section translation) directly and the
code emitted by ``codegen`` calls the same wrappers via the ``ef.`` alias, so the two paths are
equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Cardinality, Direction
from emergentflow.ir.node import Node
from emergentflow.research import ReportMeta, build_report, sections_from_values

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class BuildReport(NodeDefinition):
    """Compose upstream artifacts into one multi-section report."""

    type = "research.build_report"
    version = 1
    family = "research"
    label = "Build Report"
    category = "Reporting"
    description = (
        "Compose upstream artifacts (tables, figures, model summaries, markdown/HTML text) "
        "into one multi-section report."
    )

    ports = [
        PortSpec(
            name="sections",
            label="Sections",
            direction=Direction.IN,
            data_type="any",
            cardinality=Cardinality.MANY,
            help=(
                "Upstream artifacts to compose, in order: DataFrames, PlotSpec figures, "
                "model-summary dataclasses, or markdown/HTML strings."
            ),
        ),
        PortSpec(
            name="report",
            direction=Direction.OUT,
            data_type="Report",
            help="The composed report.",
        ),
    ]
    params = [
        ParamSpec(
            name="title",
            type_token="str",
            default="Emergent Flow Report",
            label="Title",
            help="Report title.",
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="author",
            type_token="str",
            default=None,
            label="Author",
            help="Optional report author.",
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="description",
            type_token="str",
            default=None,
            label="Description",
            help="Optional one-line report description.",
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="generated_at",
            type_token="str",
            default=None,
            label="Generated at",
            help=(
                "Optional caller-supplied timestamp/date string. build_report never reads the "
                "wall clock itself (it must stay a pure function), so this is blank unless "
                "explicitly filled in."
            ),
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="titles",
            type_token="list[str]",
            default=None,
            label="Section titles",
            help=(
                "Optional per-section titles, matched positionally to the Sections input. "
                "Missing/blank entries default to 'Section 1', 'Section 2', ..."
            ),
        ),
        ParamSpec(
            name="kinds",
            type_token="list[str]",
            default=None,
            label="Section kinds",
            help=(
                "Optional per-section kind override "
                "('markdown'|'html'|'figure'|'table'|'model_summary'), matched positionally "
                "to the Sections input. Missing/blank entries auto-detect from each value's "
                "Python type."
            ),
        ),
        ParamSpec(
            name="render_pdf",
            type_token="bool",
            default=False,
            label="Render PDF",
            help="Also render a PDF (requires the optional [report-pdf] extra).",
            hints=ValidationHints(widget="checkbox"),
        ),
    ]

    def _args(self, node: Node) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        return {
            "title": values.get("title") or "Emergent Flow Report",
            "author": values.get("author"),
            "description": values.get("description"),
            "generated_at": values.get("generated_at"),
            "titles": values.get("titles"),
            "kinds": values.get("kinds"),
            "render_pdf": bool(values.get("render_pdf") or False),
        }

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        args = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('report')} = ef.research.build_report("
                f"sections=ef.research.sections_from_values({ctx.in_var('sections')}, "
                f"titles={args['titles']!r}, kinds={args['kinds']!r}), "
                f"meta=ef.research.ReportMeta(title={args['title']!r}, "
                f"author={args['author']!r}, description={args['description']!r}, "
                f"generated_at={args['generated_at']!r}), "
                f"render_pdf={args['render_pdf']!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        args = self._args(node)
        sections = sections_from_values(
            cast("list[Any]", inputs["sections"]), titles=args["titles"], kinds=args["kinds"]
        )
        meta = ReportMeta(
            title=args["title"],
            author=args["author"],
            description=args["description"],
            generated_at=args["generated_at"],
        )
        report = build_report(sections=sections, meta=meta, render_pdf=args["render_pdf"])
        return {"report": report}
