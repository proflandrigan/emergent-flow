"""
emergentflow.nodes.examples.select_columns
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``clean.select_columns`` — a *transform* node (1 in, 1 out).

Pandas-backed column selector (Epic 1, Story 8). ``execute`` calls
``emergentflow.clean.select_columns`` directly and the code emitted by
``codegen`` calls the same wrapper via the ``ef.`` alias, so the two paths are
equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.clean import select_columns
from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class SelectColumns(NodeDefinition):
    """Keep or drop a chosen subset of columns."""

    type = "clean.select_columns"
    version = 1
    family = "clean"
    label = "Select Columns"
    category = "Transform"
    description = "Keep or drop a chosen subset of columns."

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame whose columns should be selected.",
        ),
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="The DataFrame with selected columns kept or dropped.",
        ),
    ]
    params = [
        ParamSpec(
            name="columns",
            type_token="list[str]",
            default=None,
            required=True,
            label="Columns",
            help="Column names to keep or drop.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="drop",
            type_token="bool",
            default=False,
            label="Drop",
            help="If True, drop the named columns; if False, keep only them.",
            hints=ValidationHints(widget="checkbox"),
        ),
    ]

    def _args(self, node: Node) -> tuple[list[str], bool]:
        values = {p.name: p.value for p in node.params}
        columns = values.get("columns")
        drop = values.get("drop") or False
        return cast("list[str]", columns), cast(bool, drop)

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        columns, drop = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('frame')} = ef.clean.select_columns("
                f"{ctx.in_var('frame')}, columns={columns!r}, drop={drop!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        columns, drop = self._args(node)
        return {"frame": select_columns(inputs["frame"], columns=columns, drop=drop)}
