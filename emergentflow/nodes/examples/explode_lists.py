"""
emergentflow.nodes.examples.explode_lists
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``clean.explode_lists`` — a *transform* node (1 in, 1 out).

Explodes one or more index-aligned list columns into long rows. ``execute`` calls
``emergentflow.clean.explode_lists`` directly and the code emitted by ``codegen`` calls the same
wrapper via the ``ef.`` alias, so the two paths are equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.clean import explode_lists
from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class ExplodeLists(NodeDefinition):
    """Explode one or more index-aligned list columns into long rows."""

    type = "clean.explode_lists"
    version = 1
    family = "clean"
    label = "Explode Lists"
    category = "Transform"
    description = (
        "Explode one or more index-aligned list columns into long rows (like pandas explode)."
    )
    keywords = ["explode", "unnest", "flatten", "expand", "list"]

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame containing list-valued column(s) to explode.",
        ),
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="The long-form DataFrame with list elements expanded to one row each.",
        ),
    ]
    params = [
        ParamSpec(
            name="columns",
            type_token="list[str]",
            default=None,
            required=True,
            label="Columns",
            help="List column(s) to explode. Multiple columns are exploded together (aligned).",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="drop_empty",
            type_token="bool",
            default=True,
            label="Drop empty",
            help="Drop rows produced from empty lists / missing values.",
            hints=ValidationHints(widget="checkbox"),
        ),
        ParamSpec(
            name="ignore_index",
            type_token="bool",
            default=True,
            label="Reset index",
            help="Renumber the result index 0..n-1.",
            hints=ValidationHints(widget="checkbox"),
        ),
    ]

    def _args(self, node: Node) -> tuple[list[str], bool, bool]:
        values = {p.name: p.value for p in node.params}
        columns = values.get("columns")
        drop_empty = values.get("drop_empty")
        drop_empty = True if drop_empty is None else drop_empty
        ignore_index = values.get("ignore_index")
        ignore_index = True if ignore_index is None else ignore_index
        return cast("list[str]", columns), cast(bool, drop_empty), cast(bool, ignore_index)

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        columns, drop_empty, ignore_index = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('frame')} = ef.clean.explode_lists("
                f"{ctx.in_var('frame')}, columns={columns!r}, "
                f"drop_empty={drop_empty!r}, ignore_index={ignore_index!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        columns, drop_empty, ignore_index = self._args(node)
        return {
            "frame": explode_lists(
                inputs["frame"],
                columns=columns,
                drop_empty=drop_empty,
                ignore_index=ignore_index,
            )
        }
