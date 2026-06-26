"""
emergentflow.nodes.examples.filter_rows
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``clean.filter_rows`` — a *transform* node (1 in, 1 out).

Keeps rows matching a single structured predicate: column <operator> value.
``execute`` calls ``emergentflow.clean.filter_rows`` directly and the code
emitted by ``codegen`` calls the same wrapper via the ``ef.`` alias, so the
two paths are equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.clean import filter_rows
from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class FilterRows(NodeDefinition):
    """Keep rows matching a column/operator/value predicate."""

    type = "clean.filter_rows"
    version = 1
    family = "clean"
    label = "Filter Rows"
    category = "Transform"
    description = "Keep rows matching a column/operator/value predicate."

    ports = [
        PortSpec(
            name="frame",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame to filter.",
        ),
        PortSpec(
            name="frame",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="The filtered DataFrame containing only rows that match the predicate.",
        ),
    ]
    params = [
        ParamSpec(
            name="column",
            type_token="str",
            default=None,
            required=True,
            label="Column",
            help="Column to test.",
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="operator",
            type_token="str",
            default="==",
            label="Operator",
            hints=ValidationHints(
                choices=["==", "!=", "<", "<=", ">", ">=", "isin"],
                widget="select",
            ),
        ),
        ParamSpec(
            name="value",
            type_token="any",
            default=None,
            label="Value",
            help="Scalar to compare against; for 'isin' provide a list.",
            hints=ValidationHints(widget="text"),
        ),
    ]

    def _args(self, node: Node) -> tuple[str, str, object]:
        values = {p.name: p.value for p in node.params}
        column = cast(str, values.get("column"))
        op = values.get("operator", "==") or "=="
        value = values.get("value")
        return column, cast(str, op), value

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        column, op, value = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('frame')} = ef.clean.filter_rows("
                f"{ctx.in_var('frame')}, column={column!r}, operator={op!r}, value={value!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        column, op, value = self._args(node)
        return {"frame": filter_rows(inputs["frame"], column=column, operator=op, value=value)}
