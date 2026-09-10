"""
emergentflow.nodes.examples.write_table
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``data.write_table`` — warehouse write-back (issue #164 Gap 6).

Materializes the input frame as a warehouse table via the injected ``WarehouseClient``
(requires the warehouse client capability, ADR 0018) and passes the frame through
unchanged. ``execute`` calls ``emergentflow.data.write_table`` directly and ``codegen``
calls the same wrapper via the ``ef.`` alias with ``client=warehouse``, so the two paths
are equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.clients import ClientKind
from emergentflow.data import write_table
from emergentflow.data.warehouse.protocol import WarehouseClient
from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.ir.params import ParamValue

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ColumnEffect, ColumnEffectKind, ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext

_MODE_CHOICES = ["append", "truncate", "error"]


@register
class WriteTable(NodeDefinition):
    """Write the input DataFrame to a warehouse table and pass it through."""

    type = "data.write_table"
    version = 1
    family = "data"
    label = "Write Table"
    category = "Export"
    description = "Materialize the input DataFrame as a warehouse table (write-enabled profile)."

    column_effect = ColumnEffect(kind=ColumnEffectKind.PASSTHROUGH)
    requires = frozenset({ClientKind.WAREHOUSE})

    # Effectful: a cached result would skip the warehouse write on re-run (mode="append"
    # would silently stop appending), so never serve this node from the execution cache.
    cacheable = False

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame to materialize.",
        ),
        PortSpec(
            name="result",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="The same DataFrame, unchanged (chainable pass-through).",
        ),
    ]
    params = [
        ParamSpec(
            name="table",
            type_token="str",
            required=True,
            label="Table",
            help="Target table (optionally schema.table).",
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="connection",
            type_token="str",
            required=True,
            label="Connection",
            help="Connection profile name (must have write_enabled=true).",
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="dialect",
            type_token="str",
            required=True,
            label="Dialect",
            help="sqlglot dialect key (duckdb, postgres, ...).",
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="mode",
            type_token="str",
            default="append",
            label="Mode",
            help="append (default), truncate (delete rows, keep the table, then append), or error "
            "(refuse if exists).",
            hints=ValidationHints(choices=cast("list[ParamValue]", _MODE_CHOICES), widget="select"),
        ),
    ]

    def _args(self, node: Node) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        return {
            "table": cast(str, values.get("table")),
            "connection": cast(str, values.get("connection")),
            "dialect": cast(str, values.get("dialect")),
            "mode": cast(str, values.get("mode", "append")),
        }

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        args = self._args(node)
        codegen_mode = f", mode={args['mode']!r}" if args["mode"] != "append" else ""
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('result')} = ef.data.write_table("
                f"{ctx.in_var('frame')}, table={args['table']!r}, "
                f"connection={args['connection']!r}, dialect={args['dialect']!r}"
                f"{codegen_mode}, client=warehouse)"
            ),
        )

    def execute(
        self,
        node: Node,
        inputs: dict[str, Any],
        *,
        client: WarehouseClient | None = None,
    ) -> dict[str, Any]:
        args = self._args(node)
        return {
            "result": write_table(
                inputs["frame"],
                table=args["table"],
                connection=args["connection"],
                dialect=args["dialect"],
                mode=args["mode"],
                client=client,
            )
        }
