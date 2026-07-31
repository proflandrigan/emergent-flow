"""
emergentflow.nodes.examples.group_container
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``layout.group`` — a canvas organization node for grouping nodes into containers.

A group container carries no data flow: it has zero ports and is never wired to
another node. ``codegen`` always emits an empty body (a true no-op — an empty
``CodeFragment.body`` is filtered out of the compiled module by
``emergentflow.codegen.compiler._assemble``) and ``execute`` always returns
``{}``. This satisfies ADR 0002 trivially (empty vs. empty).

Member nodes reference this group via their ``group_id`` field. This node type
does not itself validate or resolve ``group_id`` cross-references against the
graph (mirroring how ``ir.edge.Edge`` documents that cross-reference validation
is a graph-level concern) — a stale or unset ``group_id`` is not an error.
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
class GroupContainer(NodeDefinition):
    """A visual container grouping other nodes; carries no data flow."""

    type = "layout.group"
    version = 1
    family = "layout"
    label = "Group"
    category = "Organization"
    description = "A visual container grouping other nodes; carries no data flow."

    ports = []
    params = [
        ParamSpec(
            name="label",
            type_token="str",
            default="Group",
            required=False,
            label="Label",
            help="Display name for this group.",
        ),
        ParamSpec(
            name="color",
            type_token="str",
            default="slate",
            required=False,
            label="Color",
            help="Background color swatch for the group container.",
            hints=ValidationHints(
                widget="select",
                choices=["slate", "blue", "green", "purple", "amber", "rose"],
            ),
        ),
    ]

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        return CodeFragment(imports=[], body="")

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        return {}
