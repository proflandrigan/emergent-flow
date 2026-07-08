"""
emergentflow.nodes.examples.query_builder
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``data.query_builder`` — the visual query builder (Epic 13 Story 5).

Both ``execute`` and ``codegen`` route through the same ``ef.data.query(spec=...)``
wrapper, so the two paths are equivalent by construction (ADR 0002). The wrapper
compiles the structured spec to dialect SQL via ``compile_spec`` (one place, one
function) — the node never touches SQL directly.
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
class QueryBuilder(NodeDefinition):
    """Build a SQL query from structured spec and return a DataFrame."""

    type = "data.query_builder"
    version = 1
    family = "data"
    label = "Query Builder"
    category = "Ingest"
    description = (
        "Build a SQL query from a structured spec "
        "(source, select, where, join, group_by, order_by) "
        "and return a DataFrame."
    )
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
            name="source",
            type_token="str",
            required=True,
            label="Source table",
            help="The base relation to query (e.g. 'sales').",
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="select",
            type_token="list",
            default=[],
            label="Select columns",
            help=(
                "Columns / aggregates to select. "
                "Each item is a string or "
                "{'column': ..., 'agg': ..., 'alias': ...}."
            ),
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="where",
            type_token="list",
            default=[],
            label="Where predicates",
            help=(
                "Filter predicates. Each: "
                "{'column': ..., 'op': ..., 'value': ...}."
            ),
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="join",
            type_token="list",
            default=[],
            label="Joins",
            help=(
                "Join specs. Each: "
                "{'relation': ..., 'on': [...], 'type': ...}."
            ),
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="group_by",
            type_token="list",
            default=[],
            label="Group by",
            help="Column names to group by.",
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="having",
            type_token="list",
            default=[],
            label="Having predicates",
            help="HAVING filter predicates (same format as where).",
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="order_by",
            type_token="list",
            default=[],
            label="Order by",
            help=(
                "Ordering specs. Each: a string or "
                "{'column': ..., 'desc': bool}."
            ),
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="limit",
            type_token="int",
            default=None,
            label="Limit",
            help="Row limit applied in the compiled SQL.",
            hints=ValidationHints(min=1, widget="number"),
        ),
        ParamSpec(
            name="distinct",
            type_token="bool",
            default=False,
            label="Distinct",
            help="When True, adds SELECT DISTINCT.",
            hints=ValidationHints(widget="checkbox"),
        ),
        connection_param(),
        ParamSpec(
            name="dialect",
            type_token="str",
            default="duckdb",
            required=True,
            label="Dialect",
            help="SQL dialect.",
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
            help="Optional row cap (injected as LIMIT if absent).",
            hints=ValidationHints(min=1, widget="number"),
        ),
        ParamSpec(
            name="dry_run",
            type_token="bool",
            default=False,
            label="Dry run",
            help="Return a cost estimate without running.",
            hints=ValidationHints(widget="checkbox"),
        ),
    ]

    def _build_spec(self, node: Node) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        spec: dict[str, Any] = {
            "source": cast(str, values.get("source") or ""),
        }
        for key in (
            "select", "where", "join",
            "group_by", "having", "order_by",
        ):
            val = values.get(key)
            if val:
                spec[key] = val
        limit = values.get("limit")
        if limit is not None:
            spec["limit"] = limit
        distinct = values.get("distinct", False)
        if distinct:
            spec["distinct"] = True
        return spec

    def _meta(self, node: Node) -> tuple[
        str, str, int | None, bool
    ]:
        values = {p.name: p.value for p in node.params}
        connection = cast(str, values.get("connection") or "")
        dialect = cast(str, values.get("dialect") or "duckdb")
        max_rows = cast("int | None", values.get("max_rows"))
        dry_run = cast(
            bool, values.get("dry_run", False) or False
        )
        return connection, dialect, max_rows, dry_run

    def codegen(
        self, node: Node, ctx: CodegenContext
    ) -> CodeFragment:
        spec = self._build_spec(node)
        connection, dialect, max_rows, dry_run = self._meta(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('frame')} = ef.data.query(\n"
                f"    spec={spec!r},\n"
                f"    connection={connection!r},\n"
                f"    dialect={dialect!r},\n"
                f"    client=warehouse,\n"
                f"    max_rows={max_rows!r},\n"
                f"    dry_run={dry_run!r},\n"
                f")"
            ),
        )

    def execute(
        self,
        node: Node,
        inputs: dict[str, Any],
        *,
        client: WarehouseClient | None = None,
    ) -> dict[str, Any]:
        spec = self._build_spec(node)
        connection, dialect, max_rows, dry_run = self._meta(node)
        result = data_query(
            spec=spec,
            connection=connection,
            dialect=dialect,
            client=client,
            max_rows=max_rows,
            dry_run=dry_run,
        )
        return {"frame": result}
