"""
emergentflow.data.warehouse.adapters.redshift_adapter
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Redshift ``WarehouseAdapter`` (Epic 13 Story 6, ADR 0018): optional cloud
adapter behind the ``[redshift]`` extra. Uses ``redshift-connector``
(Apache-2.0).
"""

from __future__ import annotations

import time
from collections.abc import Mapping

import pandas as pd

from emergentflow.data.warehouse.protocol import (
    RELATION_SCHEMA_COLUMNS,
    ColumnSchema,
    CostEstimate,
    MissingDriverError,
    QueryRequest,
    QueryResult,
)

try:
    import redshift_connector as _rs
except ImportError:
    _rs = None

_EXTRA = "emergentflow[redshift]"


def _require_driver() -> None:
    if _rs is None:
        raise MissingDriverError(_EXTRA)


def _escape_literal(value: str) -> str:
    """Escape a value for safe interpolation into a single-quoted SQL literal.

    ``list_relations``/``describe_relation`` build introspection SQL from
    caller-supplied database/schema/relation names; standard SQL escaping
    (doubling embedded single quotes) prevents those names from breaking out
    of the literal and injecting arbitrary SQL.
    """
    return value.replace("'", "''")


class RedshiftAdapter:
    """A ``WarehouseAdapter`` for Amazon Redshift.

    Attributes
    ----------
    dialect: always ``"redshift"``.
    """

    dialect: str = "redshift"

    def _connect(self, credentials: Mapping[str, str]) -> _rs.Connection:
        """Open a Redshift connection from resolved credentials."""
        _require_driver()
        return _rs.connect(
            host=credentials["host"],
            port=int(credentials.get("port", "5439")),
            database=credentials["database"],
            user=credentials["user"],
            password=credentials["password"],
        )

    def execute(
        self,
        request: QueryRequest,
        credentials: Mapping[str, str],
    ) -> QueryResult:
        _require_driver()
        start = time.monotonic()
        conn = self._connect(credentials)
        try:
            cursor = conn.cursor()
            cursor.execute(request.sql)
            df = cursor.fetch_dataframe()
            elapsed_ms = (time.monotonic() - start) * 1000

            truncated = False
            if request.max_rows is not None and len(df) > request.max_rows:
                df = df.head(request.max_rows)
                truncated = True

            columns = tuple(
                ColumnSchema(
                    name=col,
                    dtype=str(df[col].dtype),
                    nullable=bool(df[col].isna().any()),
                )
                for col in df.columns
            )
            return QueryResult(
                df=df,
                row_count=len(df),
                columns=columns,
                dialect="redshift",
                truncated=truncated,
                elapsed_ms=elapsed_ms,
            )
        finally:
            conn.close()

    def dry_run(
        self,
        request: QueryRequest,
        credentials: Mapping[str, str],
    ) -> CostEstimate:
        _require_driver()
        conn = self._connect(credentials)
        try:
            cursor = conn.cursor()
            cursor.execute(f"EXPLAIN {request.sql}")
            rows = cursor.fetchall()
            # Parse estimated row count from the EXPLAIN output
            estimated_rows = len(rows)
            return CostEstimate(
                dialect="redshift",
                estimated_rows=estimated_rows,
            )
        finally:
            conn.close()

    def list_relations(
        self,
        credentials: Mapping[str, str],
        *,
        database: str | None = None,
        schema: str | None = None,
    ) -> pd.DataFrame:
        _require_driver()
        conn = self._connect(credentials)
        try:
            sql = (
                "SELECT table_catalog AS database, "
                "table_schema AS schema, "
                'table_name AS "table" '
                "FROM information_schema.tables "
                "WHERE table_schema NOT IN ('pg_catalog', 'information_schema')"
            )
            filters: list[str] = []
            if database:
                filters.append(f"table_catalog = '{_escape_literal(database)}'")
            if schema:
                filters.append(f"table_schema = '{_escape_literal(schema)}'")
            if filters:
                sql += " AND " + " AND ".join(filters)
            sql += ' ORDER BY database, schema, "table"'
            cursor = conn.cursor()
            cursor.execute(sql)
            df = cursor.fetch_dataframe()
            df.columns = ["database", "schema", "table"]
            df["column"] = None
            df["data_type"] = None
            df["nullable"] = None
            return df[list(RELATION_SCHEMA_COLUMNS)]
        finally:
            conn.close()

    def describe_relation(
        self,
        credentials: Mapping[str, str],
        relation: str,
        *,
        database: str | None = None,
        schema: str | None = None,
    ) -> pd.DataFrame:
        _require_driver()
        conn = self._connect(credentials)
        try:
            sql = (
                "SELECT column_name AS column, "
                "data_type, "
                "CASE WHEN is_nullable = 'YES' "
                "THEN true ELSE false END AS nullable "
                "FROM information_schema.columns "
                f"WHERE table_name = '{_escape_literal(relation)}' "
            )
            if database:
                sql += f"AND table_catalog = '{_escape_literal(database)}' "
            if schema:
                sql += f"AND table_schema = '{_escape_literal(schema)}' "
            sql += "ORDER BY ordinal_position"
            cursor = conn.cursor()
            cursor.execute(sql)
            df = cursor.fetch_dataframe()
            df.columns = ["column", "data_type", "nullable"]
            df["database"] = database
            df["schema"] = schema
            df["table"] = relation
            return df[list(RELATION_SCHEMA_COLUMNS)]
        finally:
            conn.close()
