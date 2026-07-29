"""
emergentflow.nodes.examples.sort
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``clean.sort`` — a *transform* node (1 in, 1 out), Epic 16 Story 7.

Sort rows by one or more columns, with per-key direction and NA placement. ``execute`` calls
``emergentflow.clean.sort`` directly and the code emitted by ``codegen`` calls the same wrapper
via the ``ef.`` alias, so the two paths are equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from emergentflow.clean import NA_POSITIONS, sort
from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class Sort(NodeDefinition):
    """Sort rows by one or more columns, with per-key direction and NA placement."""

    type = "clean.sort"
    version = 1
    family = "clean"
    label = "Sort"
    category = "Transform"
    description = "Sort rows by one or more columns, with per-key direction and NA placement."

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame to sort.",
        ),
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="The sorted DataFrame.",
        ),
    ]
    params = [
        ParamSpec(
            name="by",
            type_token="list[str]",
            default=None,
            required=True,
            label="By",
            help="Sort key column(s), in priority order.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="ascending",
            type_token="list[bool]",
            default=None,
            label="Ascending",
            help="One bool per sort key. Leave unset to sort every key ascending.",
        ),
        ParamSpec(
            name="na_position",
            type_token="str",
            default="last",
            label="NA position",
            help="Place missing values first or last.",
            hints=ValidationHints(choices=list(NA_POSITIONS), widget="select"),
        ),
        ParamSpec(
            name="ignore_index",
            type_token="bool",
            default=False,
            label="Reset index",
            help="Renumber the result index 0..n-1.",
            hints=ValidationHints(widget="checkbox"),
        ),
    ]

    def _args(self, node: Node) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        ascending = values.get("ascending")
        ignore_index = values.get("ignore_index")
        return {
            "by": values.get("by") or [],
            # An unset per-key list means "every key ascending" -- the wrapper accepts a bare
            # bool.
            "ascending": True if ascending is None else ascending,
            "na_position": values.get("na_position") or "last",
            "ignore_index": False if ignore_index is None else ignore_index,
        }

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        args = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('frame')} = ef.clean.sort("
                f"{ctx.in_var('frame')}, by={args['by']!r}, "
                f"ascending={args['ascending']!r}, na_position={args['na_position']!r}, "
                f"ignore_index={args['ignore_index']!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        args = self._args(node)
        return {
            "frame": sort(
                inputs["frame"],
                by=args["by"],
                ascending=args["ascending"],
                na_position=args["na_position"],
                ignore_index=args["ignore_index"],
            )
        }
