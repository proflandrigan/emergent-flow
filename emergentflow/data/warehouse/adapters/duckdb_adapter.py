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
from typing import Any

import duckdb
import pandas as pd

from emergentflow.data.errors import DataError
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


def _split_table(table: str) -> tuple[str, str]:
    """Split ``schema.table`` into ``(schema, table)``; an unqualified name lives in ``main``."""
    schema, _, name = table.rpartition(".")
    return (schema or "main"), name


def _quote_part(part: str) -> str:
    """Quote one identifier component with embedded quotes doubled."""
    return '"' + part.replace('"', '""') + '"'


def _quoted_table(schema: str, name: str) -> str:
    """Quote an already-split ``schema.name`` for DDL/DML.

    The schema and table are quoted separately so a dotted *schema* or a name containing
    dots/quotes cannot break out of the identifier position or disagree with how the
    information-schema lookups resolve the two parts (``_split_table`` splits on the LAST
    dot only, so ``a.b.c`` is schema ``a.b`` table ``c``, never three catalog levels).
    """
    return f"{_quote_part(schema)}.{_quote_part(name)}"


def _duckdb_type(dtype: Any) -> str:
    """Map a pandas dtype to a DuckDB column type for empty-frame DDL.

    ``CREATE TABLE ... AS SELECT`` on a zero-row frame infers junk types (an object column
    becomes ``INTEGER``), so an empty frame's schema is declared explicitly from its dtypes.
    Only reachable for the empty create path; non-empty frames keep the fast ``AS SELECT``
    inference. Fall back to ``VARCHAR`` for anything exotic rather than guessing wrong.
    """
    dtype = pd.api.types.pandas_dtype(dtype)
    if pd.api.types.is_bool_dtype(dtype):
        return "BOOLEAN"
    if isinstance(dtype, pd.DatetimeTZDtype) or dtype.kind in "Mm":
        return "TIMESTAMP"
    if dtype.kind == "m":
        return "INTERVAL"
    if isinstance(dtype, pd.CategoricalDtype):
        return "VARCHAR"
    if pd.api.types.is_integer_dtype(dtype):
        return "BIGINT" if dtype.itemsize >= 8 else "INTEGER"
    if pd.api.types.is_float_dtype(dtype):
        return "DOUBLE"
    return "VARCHAR"


class DuckDBAdapter:
    """A ``WarehouseAdapter`` for the in-process DuckDB backend.

    Attributes
    ----------
    dialect: always ``"duckdb"``.
    """

    dialect: str = "duckdb"

    def _connect(
        self, credentials: Mapping[str, str], *, read_only: bool = True
    ) -> duckdb.DuckDBPyConnection:
        """Open a DuckDB connection from resolved credentials.

        ``credentials`` may contain a ``"path"`` key pointing to a
        ``.duckdb`` file; if absent, connects to ``:memory:``. File paths default
        to read-only and are opened read-write only when a caller explicitly asks
        for it (``query.read_only=False`` / the write path) -- so a read-only
        database file stays read-only unless a write was requested.
        """
        path = credentials.get("path", ":memory:")
        if path == ":memory:":
            return duckdb.connect(":memory:", read_only=False)
        return duckdb.connect(path, read_only=read_only)

    def execute(
        self,
        request: QueryRequest,
        credentials: Mapping[str, str],
    ) -> QueryResult:
        start = time.monotonic()
        conn = self._connect(credentials, read_only=request.read_only)
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

        ``"append"`` appends rows matched by column NAME (``INSERT ... BY NAME``, so a
        reordered frame never lands one column's values in another), creating the table if
        absent; ``"truncate"`` deletes every row and appends, keeping the table definition;
        ``"error"`` refuses when the table already exists. ``table`` may be ``schema.table``
        (unqualified names live in ``main``); every identifier is quoted. The create/delete/
        insert runs in ONE transaction, so a failed insert (e.g. a frame whose columns do not
        match) rolls back and the existing rows survive. Requires a file-backed DuckDB (the
        profile's ``path`` coordinate): an in-memory database cannot persist a write, so a
        path-less profile is refused instead of reporting a success nobody can read back.

        A frame whose columns do not match the *existing* table's columns is refused up front
        (``DataError``): ``INSERT ... BY NAME`` treats a missing column as NULL -- an append
        would silently pollute the table and a ``truncate`` (which deletes first) would
        silently destroy the existing rows. A successful write is only ever reported when the
        schema actually lined up.
        """
        start = time.monotonic()
        path = credentials.get("path")
        if not path or path == ":memory:":
            raise DataError(
                "connection has no `path` coordinate; an in-memory DuckDB cannot persist a "
                "write. Point the profile at a .duckdb file to write tables."
            )
        schema, name = _split_table(request.table)
        qtable = _quoted_table(schema, name)
        conn = duckdb.connect(path, read_only=False)
        try:
            exists = (
                conn.execute(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = ? AND table_name = ?",
                    [schema, name],
                ).fetchone()
                is not None
            )
            if request.mode == "error" and exists:
                raise RuntimeError(
                    f"table {request.table!r} already exists (mode='error'); pass mode='append' "
                    "or 'truncate' to write anyway."
                )
            if exists:
                table_cols = [
                    row[0]
                    for row in conn.execute(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = ? AND table_name = ? "
                        "ORDER BY ordinal_position",
                        [schema, name],
                    ).fetchall()
                ]
                frame_cols = list(df.columns)
                if set(table_cols) != set(frame_cols):
                    raise DataError(
                        f"frame columns {frame_cols!r} do not match table {request.table!r} "
                        f"columns {table_cols!r}; refusing to write (existing rows preserved). "
                        "Align the frame's columns with the table before writing."
                    )
            conn.begin()
            try:
                if not exists:
                    if len(df):
                        conn.execute(f"CREATE TABLE {qtable} AS SELECT * FROM df")
                    else:
                        # An empty frame has no rows to infer types from; ``AS SELECT *`` on
                        # zero rows would create a table with wrong (junk) column types, so
                        # build the DDL explicitly from the frame's dtypes.
                        columns = ", ".join(
                            f"{_quote_part(str(col))} {_duckdb_type(df[col].dtype)}"
                            for col in df.columns
                        )
                        conn.execute(f"CREATE TABLE {qtable} ({columns})")
                else:
                    if request.mode == "truncate":
                        conn.execute(f"DELETE FROM {qtable}")
                    conn.execute(f"INSERT INTO {qtable} BY NAME SELECT * FROM df")
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            elapsed_ms = (time.monotonic() - start) * 1000
            return WriteResult(
                table=request.table,
                mode=request.mode,
                rows_written=len(df),
                dialect="duckdb",
                elapsed_ms=elapsed_ms,
            )
        finally:
            conn.close()
