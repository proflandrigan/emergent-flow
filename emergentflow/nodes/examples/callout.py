"""
emergentflow.nodes.examples.callout
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``layout.callout`` — a visual callout region (no data flow).

A callout carries no data flow: it has zero ports and is never wired to
another node. ``codegen`` always emits an empty body and ``execute`` always
returns ``{}``. This satisfies ADR 0002 trivially (empty vs. empty).

The callout is rendered as a styled border box behind other nodes on the
canvas — it is purely a visual annotation, not a structural group (no
``groupId`` relationship).
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
class CalloutNode(NodeDefinition):
    """A visual callout region for grouping nodes visually; no data flows through it."""

    type = "layout.callout"
    version = 1
    family = "layout"
    label = "Callout"
    category = "Annotation"
    description = "A decorative border box that visually groups a region of the canvas."

    ports = []
    params = [
        ParamSpec(
            name="label",
            type_token="str",
            default="Callout",
            required=False,
            label="Label",
            help="Title text shown in the callout header bar.",
        ),
        ParamSpec(
            name="color",
            type_token="str",
            default="blue",
            required=False,
            label="Color",
            help="Border/header color theme.",
            hints=ValidationHints(
                widget="select",
                choices=["slate", "blue", "green", "purple", "amber", "rose"],
            ),
        ),
        ParamSpec(
            name="width",
            type_token="int",
            default=400,
            required=False,
            label="Width",
            help="Width of the callout box in canvas pixels.",
            hints=ValidationHints(widget="number", min=100, step=10),
        ),
        ParamSpec(
            name="height",
            type_token="int",
            default=300,
            required=False,
            label="Height",
            help="Height of the callout box in canvas pixels.",
            hints=ValidationHints(widget="number", min=80, step=10),
        ),
    ]

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        return CodeFragment(imports=[], body="")

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        return {}
