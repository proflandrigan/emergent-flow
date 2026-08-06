"""
emergentflow.nodes.examples.derive_column
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``clean.derive_column`` — a *transform* node (1 in, 1 out).

Adds computed and conditional (case-when) columns via a restricted, ``ast``-validated
expression grammar. ``execute`` calls ``emergentflow.clean.derive_column`` directly and the
code emitted by ``codegen`` calls the same wrapper via the ``ef.`` alias, so the two paths
are equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from emergentflow.clean import derive_column
from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ColumnEffect, ColumnEffectKind, ParamSpec, PortSpec

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class DeriveColumn(NodeDefinition):
    """Add computed and conditional (case-when) columns to a DataFrame."""

    type = "clean.derive_column"
    version = 1
    family = "clean"
    label = "Derive Column"
    category = "Transform"
    description = (
        "Add computed and conditional (case-when) columns using a safe, restricted "
        "expression grammar."
    )

    column_effect = ColumnEffect(kind=ColumnEffectKind.DERIVE)

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame to derive new columns from.",
        ),
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="A copy of the input with the derived column(s) appended.",
        ),
    ]
    params = [
        ParamSpec(
            name="columns",
            type_token="list[dict[str, any]]",
            default=None,
            required=True,
            label="Derived columns",
            help=(
                "Ordered list of column specs. Each is either {'name': str, 'expr': str} for a "
                "computed column, or {'name': str, 'when': [{'if': str, 'then': value}, ...], "
                "'else': value} for a case-when column. Later specs may reference earlier ones."
            ),
        ),
    ]

    def _args(self, node: Node) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        return {"columns": values.get("columns") or []}

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        args = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('frame')} = ef.clean.derive_column("
                f"{ctx.in_var('frame')}, columns={args['columns']!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        args = self._args(node)
        return {"frame": derive_column(inputs["frame"], columns=args["columns"])}
