"""
emergentflow.nodes.examples.sql_query
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``data.sql_query`` — the raw-SQL escape hatch (Epic 13 Story 4).

Both ``execute`` and ``codegen`` route through the same ``ef.data.query(sql=...)``
wrapper, so the two paths are equivalent by construction (ADR 0002). This node
sets ``requires = frozenset({ClientKind.WAREHOUSE})`` (ADR 0018): the injected
``WarehouseClient`` is threaded in by the executor / the compiled module's
``main()``, never constructed here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.clients import ClientKind
from emergentflow.data import query as data_query
from emergentflow.data.warehouse.params import connection_param
from emergentflow.data.warehouse.protocol import WarehouseClient
from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class SqlQuery(NodeDefinition):
    """Run a raw SQL query against a warehouse and return a DataFrame."""

    type = "data.sql_query"
    version = 1
    family = "data"
    label = "SQL Query"
    category = "Ingest"
    description = "Run a raw SQL query against a warehouse connection and return a DataFrame."
    requires = frozenset({ClientKind.WAREHOUSE})
    cacheable = False

    ports = [
        PortSpec(
            name="frame",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="The query result as a pandas DataFrame.",
        ),
    ]
    params = [
        ParamSpec(
            name="sql",
            type_token="str",
            required=True,
            label="SQL",
            help="The SQL query to run (SELECT/WITH only under read-only connections).",
            hints=ValidationHints(widget="sql"),
        ),
        connection_param(),
        ParamSpec(
            name="dialect",
            type_token="str",
            default="duckdb",
            required=True,
            label="Dialect",
            help="SQL dialect (e.g. 'duckdb', 'bigquery', 'redshift', 'postgres').",
            hints=ValidationHints(
                choices=["duckdb", "bigquery", "redshift", "postgres"],
                widget="select",
            ),
        ),
        ParamSpec(
            name="max_rows",
            type_token="int",
            default=None,
            label="Max rows",
            help="Optional row cap; injects LIMIT when absent from the SQL.",
            hints=ValidationHints(min=1, widget="number"),
        ),
        ParamSpec(
            name="dry_run",
            type_token="bool",
            default=False,
            label="Dry run",
            help="When True, return a cost estimate without running the query.",
            hints=ValidationHints(widget="checkbox"),
        ),
    ]

    def _args(self, node: Node) -> tuple[str, str, str, int | None, bool]:
        values = {p.name: p.value for p in node.params}
        sql = cast(str, values.get("sql") or "")
        connection = cast(str, values.get("connection") or "")
        dialect = cast(str, values.get("dialect") or "duckdb")
        max_rows = cast("int | None", values.get("max_rows"))
        dry_run = cast(bool, values.get("dry_run", False) or False)
        return sql, connection, dialect, max_rows, dry_run

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        sql, connection, dialect, max_rows, dry_run = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('frame')} = ef.data.query(\n"
                f"    sql={sql!r},\n"
                f"    connection={connection!r},\n"
                f"    dialect={dialect!r},\n"
                f"    client=warehouse,\n"
                f"    max_rows={max_rows!r},\n"
                f"    dry_run={dry_run!r},\n"
                f")"
            ),
        )

    def execute(
        self, node: Node, inputs: dict[str, Any], *, client: WarehouseClient | None = None
    ) -> dict[str, Any]:
        sql, connection, dialect, max_rows, dry_run = self._args(node)
        result = data_query(
            sql=sql,
            connection=connection,
            dialect=dialect,
            client=client,
            max_rows=max_rows,
            dry_run=dry_run,
        )
        return {"frame": result}
