"""
emergentflow.nodes.examples.describe_relation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``data.describe_relation`` — schema introspection in-graph
(Epic 13 Story 7).

Both ``execute`` and ``codegen`` route through the same
``ef.data.describe_relation(...)`` wrapper, so the two paths are equivalent by
construction (ADR 0002). This node sets ``requires = frozenset({ClientKind.WAREHOUSE})``
(ADR 0018): the injected ``WarehouseClient`` is threaded in by the executor / the
compiled module's ``main()``, never constructed here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.clients import ClientKind
from emergentflow.data import describe_relation as data_describe_relation
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
class DescribeRelation(NodeDefinition):
    """Describe a relation's columns and return a tidy schema DataFrame."""

    type = "data.describe_relation"
    version = 2
    family = "data"
    label = "Describe Relation"
    category = "Ingest"
    description = "Describe a relation's columns (name/dtype/nullable) as a tidy DataFrame."
    requires = frozenset({ClientKind.WAREHOUSE})
    cacheable = False

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="The relation's column schema as a tidy pandas DataFrame.",
        ),
    ]
    params = [
        connection_param(),
        ParamSpec(
            name="relation",
            type_token="str",
            required=True,
            label="Relation",
            help="The relation (table) name to describe.",
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="database",
            type_token="str",
            required=False,
            label="Database",
            help="Optional database/catalog to disambiguate a relation name that exists "
            "in more than one database.",
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="schema",
            type_token="str",
            required=False,
            label="Schema",
            help="Optional schema (or, for BigQuery, dataset) to disambiguate a relation "
            "name that exists in more than one schema.",
            hints=ValidationHints(widget="text"),
        ),
    ]

    def _args(self, node: Node) -> tuple[str, str, str | None, str | None]:
        values = {p.name: p.value for p in node.params}
        connection = cast(str, values.get("connection") or "")
        relation = cast(str, values.get("relation") or "")
        database = cast("str | None", values.get("database") or None)
        schema = cast("str | None", values.get("schema") or None)
        return connection, relation, database, schema

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        connection, relation, database, schema = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('frame')} = ef.data.describe_relation(\n"
                f"    connection={connection!r},\n"
                f"    relation={relation!r},\n"
                f"    database={database!r},\n"
                f"    schema={schema!r},\n"
                f"    client=warehouse,\n"
                f")"
            ),
        )

    def execute(
        self, node: Node, inputs: dict[str, Any], *, client: WarehouseClient | None = None
    ) -> dict[str, Any]:
        connection, relation, database, schema = self._args(node)
        result = data_describe_relation(
            connection=connection,
            relation=relation,
            database=database,
            schema=schema,
            client=client,
        )
        return {"frame": result}
