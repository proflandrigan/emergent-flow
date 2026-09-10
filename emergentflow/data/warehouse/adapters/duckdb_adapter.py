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
    WriteRequest,
    WriteResult,
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
            if request.max_rows is not None and len(df) > request.max_rows:
                df = df.head(request.max_rows)
                truncated = True

            columns = tuple(
                ColumnSchema(
                    name=col,
                    dtype=str(df[col].dtype),
                    nullable=bool(df[col].isna().any()) if len(df) else True,
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
            # DuckDB's EXPLAIN returns one row per execution-plan operator; its length has
            # nothing to do with how many rows the query would scan or return, so it must not
            # be surfaced as an ``estimated_rows`` cost estimate. No row estimate is available
            # without running the query, so report None (honest) rather than a misleading count.
            conn.execute(f"EXPLAIN {request.sql}").fetchdf()
            return CostEstimate(
                dialect="duckdb",
                estimated_rows=None,
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
        *,
        database: str | None = None,
        schema: str | None = None,
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
            )
            if database:
                sql += f"AND table_catalog = '{_escape_literal(database)}' "
            if schema:
                sql += f"AND table_schema = '{_escape_literal(schema)}' "
            sql += "ORDER BY ordinal_position"
            df = conn.execute(sql).fetchdf()
            df["database"] = database
            df["schema"] = schema
            df["table"] = relation
            return df[list(RELATION_SCHEMA_COLUMNS)]
        finally:
            conn.close()

    def write(
        self,
        request: WriteRequest,
        df: pd.DataFrame,
        credentials: Mapping[str, str],
    ) -> WriteResult:
        """Write *df* to *request.table* per the request's mode (issue #164 Gap 6).

        ``"append"`` appends rows (creating/registering the table if absent);
        ``"truncate"`` drops the table if present and recreates it from *df*;
        ``"error"`` refuses when the table already exists. Requires a writable
        connection (a file-backed DuckDB is opened read-write for the write).
        """
        import time

        start = time.monotonic()
        path = credentials.get("path")
        if path and path != ":memory:":
            conn = duckdb.connect(path, read_only=False)
        else:
            conn = duckdb.connect(":memory:", read_only=False)

        table = request.table
        try:
            exists = (
                len(
                    conn.execute(
                        "SELECT 1 FROM information_schema.tables "
                        f"WHERE table_name = '{_escape_literal(table)}'"
                    ).fetchall()
                )
                > 0
            )
            if request.mode == "error" and exists:
                raise RuntimeError(
                    f"table {table!r} already exists (mode='error'); pass mode='append' or "
                    "'truncate' to write anyway."
                )
            if request.mode == "truncate" and exists:
                conn.execute(f"DROP TABLE {table}")
                exists = False
            if not exists:
                conn.execute(f"CREATE TABLE {table} AS SELECT * FROM df")
            else:
                conn.execute(f"INSERT INTO {table} SELECT * FROM df")
            elapsed_ms = (time.monotonic() - start) * 1000
            return WriteResult(
                table=table,
                mode=request.mode,
                rows_written=len(df),
                dialect="duckdb",
                elapsed_ms=elapsed_ms,
            )
        finally:
            conn.close()
