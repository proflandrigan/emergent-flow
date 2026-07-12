"""
emergentflow.nodes.examples.markdown_note
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``notes.markdown`` — a canvas annotation node (Epic ?, notes feature).

A markdown note carries no data flow: it has zero ports and is never wired to
another node. ``codegen`` always emits an empty body (a true no-op — an empty
``CodeFragment.body`` is filtered out of the compiled module by
``emergentflow.codegen.compiler._assemble``) and ``execute`` always returns
``{}``. This satisfies ADR 0002 trivially (empty vs. empty).

A note may optionally set ``anchor_id`` to the id of another node or an edge
in the same graph, marking it as narrating that specific node/connection
rather than floating freely. This node type does not itself validate or
resolve ``anchor_id`` against the graph (no cross-reference check here,
mirroring how ``ir.edge.Edge`` documents that cross-reference validation is a
graph-level concern) — a stale or unset ``anchor_id`` is not an error.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from emergentflow.ir.node import Node

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class MarkdownNote(NodeDefinition):
    """A markdown note for narrating the pipeline; no data flows through it."""

    type = "notes.markdown"
    version = 1
    family = "notes"
    label = "Note"
    category = "Annotation"
    description = "A markdown note for narrating the pipeline; no data flows through it."

    ports = []
    params = [
        ParamSpec(
            name="content",
            type_token="str",
            default="",
            required=False,
            label="Text",
            help="Markdown note body.",
            hints=ValidationHints(widget="markdown"),
        ),
        ParamSpec(
            name="anchor_id",
            type_token="str",
            default=None,
            required=False,
            label="Anchor",
            help=(
                "Id of a node or edge in this graph this note narrates. "
                "Unset means the note floats freely."
            ),
        ),
        ParamSpec(
            name="color",
            type_token="str",
            default="yellow",
            required=False,
            label="Color",
            help="Background color swatch for the note.",
            hints=ValidationHints(
                widget="select",
                choices=["yellow", "pink", "blue", "green", "purple"],
            ),
        ),
    ]

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        return CodeFragment(imports=[], body="")

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        return {}
