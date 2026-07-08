"""
emergentflow.data.warehouse.adapters.duckdb_adapter
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
DuckDB ``WarehouseAdapter`` (Epic 13 Story 6, ADR 0018): the bundled,
in-process, credential-free backend. Queries local parquet/CSV/duckdb
files and serves as the offline fixture-recording backend.
"""

from __future__ import annotations

import time
from collections.abc import Mapping

import duckdb
import pandas as pd

from emergentflow.data.warehouse.protocol import (
    RELATION_SCHEMA_COLUMNS,
    ColumnSchema,
    CostEstimate,
    QueryRequest,
    QueryResult,
)


def _escape_literal(value: str) -> str:
    """Escape a value for safe interpolation into a single-quoted SQL literal.

    ``list_relations``/``describe_relation`` build introspection SQL from
    caller-supplied database/schema/relation names; standard SQL escaping
    (doubling embedded single quotes) prevents those names from breaking out
    of the literal and injecting arbitrary SQL.
    """
    return value.replace("'", "''")


class DuckDBAdapter:
    """A ``WarehouseAdapter`` for the in-process DuckDB backend.

    Attributes
    ----------
    dialect: always ``"duckdb"``.
    """

    dialect: str = "duckdb"

    def _connect(self, credentials: Mapping[str, str]) -> duckdb.DuckDBPyConnection:
        """Open a DuckDB connection from resolved credentials.

        ``credentials`` may contain a ``"path"`` key pointing to a
        ``.duckdb`` file; if absent, connects to ``:memory:``.
        """
        path = credentials.get("path", ":memory:")
        return duckdb.connect(path, read_only=(path != ":memory:"))

    def execute(
        self,
        request: QueryRequest,
        credentials: Mapping[str, str],
    ) -> QueryResult:
        start = time.monotonic()
        conn = self._connect(credentials)
        try:
            result = conn.execute(request.sql)
            df = result.fetchdf()
            elapsed_ms = (time.monotonic() - start) * 1000

            truncated = False
            if request.max_rows is not None and len(df) >= request.max_rows:
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
                dialect="duckdb",
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
        conn = self._connect(credentials)
        try:
            explained = conn.execute(f"EXPLAIN {request.sql}").fetchdf()
            estimated_rows = len(explained)
            return CostEstimate(
                dialect="duckdb",
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
        conn = self._connect(credentials)
        try:
            sql = (
                "SELECT table_catalog AS database, "
                "table_schema AS schema, "
                'table_name AS "table" '
                "FROM information_schema.tables"
            )
            filters: list[str] = []
            if database:
                filters.append(f"table_catalog = '{_escape_literal(database)}'")
            if schema:
                filters.append(f"table_schema = '{_escape_literal(schema)}'")
            if filters:
                sql += " WHERE " + " AND ".join(filters)
            sql += ' ORDER BY database, schema, "table"'
            df = conn.execute(sql).fetchdf()
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
    ) -> pd.DataFrame:
        conn = self._connect(credentials)
        try:
            sql = (
                "SELECT column_name AS column, "
                "data_type, "
                "CASE WHEN is_nullable = 'YES' "
                "THEN true ELSE false END AS nullable "
                "FROM information_schema.columns "
                f"WHERE table_name = '{_escape_literal(relation)}' "
                "ORDER BY ordinal_position"
            )
            df = conn.execute(sql).fetchdf()
            df["database"] = None
            df["schema"] = None
            df["table"] = relation
            return df[list(RELATION_SCHEMA_COLUMNS)]
        finally:
            conn.close()
