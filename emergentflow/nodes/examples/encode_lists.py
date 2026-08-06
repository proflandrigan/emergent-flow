"""
emergentflow.nodes.examples.encode_lists
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``clean.encode_lists`` — a *transform* node (1 in, 1 out).

Multi-hot encodes a single list-valued column into wide 0/1 indicator columns. ``execute`` calls
``emergentflow.clean.encode_lists`` directly and the code emitted by ``codegen`` calls the same
wrapper via the ``ef.`` alias, so the two paths are equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.clean import encode_lists
from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ColumnEffect, ColumnEffectKind, ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class EncodeLists(NodeDefinition):
    """Multi-hot encode a list-valued column into wide indicator columns."""

    type = "clean.encode_lists"
    version = 1
    family = "clean"
    label = "Encode Lists"
    category = "Transform"
    description = (
        "Multi-hot encode a list-valued column into wide 0/1 indicator columns "
        "(one per distinct label)."
    )

    column_effect = ColumnEffect(kind=ColumnEffectKind.PASSTHROUGH)

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame containing a list-valued column to encode.",
        ),
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="The DataFrame with wide indicator columns appended.",
        ),
    ]
    params = [
        ParamSpec(
            name="column",
            type_token="str",
            default=None,
            required=True,
            label="Column",
            help="The list-valued column to multi-hot encode.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="prefix",
            type_token="str",
            default=None,
            label="Prefix",
            help="Prefix for the generated indicator columns (defaults to the column name).",
        ),
        ParamSpec(
            name="drop",
            type_token="bool",
            default=True,
            label="Drop original",
            help="Drop the original list column from the output.",
            hints=ValidationHints(widget="checkbox"),
        ),
        ParamSpec(
            name="sep",
            type_token="str",
            default=None,
            label="Separator",
            help="If set, split string cells on this separator instead of expecting lists.",
        ),
    ]

    def _args(self, node: Node) -> tuple[str, str | None, bool, str | None]:
        values = {p.name: p.value for p in node.params}
        column = values.get("column", "")
        prefix = values.get("prefix")
        if prefix == "":
            prefix = None
        drop = values.get("drop")
        drop = True if drop is None else drop
        sep = values.get("sep")
        if sep == "":
            sep = None
        return (
            cast(str, column),
            cast("str | None", prefix),
            cast(bool, drop),
            cast("str | None", sep),
        )

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        column, prefix, drop, sep = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('frame')} = ef.clean.encode_lists("
                f"{ctx.in_var('frame')}, column={column!r}, prefix={prefix!r}, "
                f"drop={drop!r}, sep={sep!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        column, prefix, drop, sep = self._args(node)
        return {
            "frame": encode_lists(inputs["frame"], column=column, prefix=prefix, drop=drop, sep=sep)
        }
