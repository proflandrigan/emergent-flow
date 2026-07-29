"""
emergentflow.nodes.examples.clean_text
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``clean.clean_text`` — a *transform* node (1 in, 1 out).

Applies an ordered pipeline of text-cleaning operations to one or more columns.
``execute`` calls ``emergentflow.clean.clean_text`` directly and the code emitted by
``codegen`` calls the same wrapper via the ``ef.`` alias, so the two paths are
equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from emergentflow.clean import clean_text
from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class CleanText(NodeDefinition):
    """Apply an ordered pipeline of text-cleaning operations to one or more columns."""

    type = "clean.clean_text"
    version = 1
    family = "clean"
    label = "Clean Text"
    category = "Transform"
    description = (
        "Apply an ordered pipeline of text operations (trim, case, regex replace/extract, "
        "split) to one or more string columns."
    )

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame containing the text column(s) to clean.",
        ),
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="The DataFrame with the cleaned text column(s).",
        ),
    ]
    params = [
        ParamSpec(
            name="columns",
            type_token="list[str]",
            default=None,
            required=True,
            label="Columns",
            help="Text column(s) to clean.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="operations",
            type_token="list[dict[str, any]]",
            default=None,
            required=True,
            label="Operations",
            help=(
                "Ordered pipeline of operation specs, e.g. {'op': 'trim'}, {'op': 'lower'}, "
                "{'op': 'replace', 'pattern': ..., 'replacement': ...}, "
                "{'op': 'extract', 'pattern': ...}, {'op': 'split', 'sep': ...}. "
                "Put 'split' last."
            ),
        ),
        ParamSpec(
            name="suffix",
            type_token="str",
            default=None,
            label="Suffix",
            help=(
                "When set, write results to new columns named <column><suffix> instead of "
                "cleaning in place."
            ),
            hints=ValidationHints(widget="text"),
        ),
    ]

    def _args(self, node: Node) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        return {
            "columns": values.get("columns") or [],
            "operations": values.get("operations") or [],
            "suffix": values.get("suffix"),
        }

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        args = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('frame')} = ef.clean.clean_text("
                f"{ctx.in_var('frame')}, columns={args['columns']!r}, "
                f"operations={args['operations']!r}, suffix={args['suffix']!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        args = self._args(node)
        return {
            "frame": clean_text(
                inputs["frame"],
                columns=args["columns"],
                operations=args["operations"],
                suffix=args["suffix"],
            )
        }
