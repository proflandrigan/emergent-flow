"""
emergentflow.data.warehouse.adapters.postgres_adapter
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Postgres ``WarehouseAdapter`` (Epic 13 Story 6, ADR 0018): optional cloud
adapter behind the ``[postgres]`` extra. Uses SQLAlchemy + psycopg (LGPL —
lives only behind this extra, never on the hard-dep path).
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
    import sqlalchemy as _sa
except ImportError:
    _sa = None

_EXTRA = "emergentflow[postgres]"


def _require_driver() -> None:
    if _sa is None:
        raise MissingDriverError(_EXTRA)


def _escape_literal(value: str) -> str:
    """Escape a value for safe interpolation into a single-quoted SQL literal.

    ``list_relations``/``describe_relation`` build introspection SQL from
    caller-supplied database/schema/relation names; standard SQL escaping
    (doubling embedded single quotes) prevents those names from breaking out
    of the literal and injecting arbitrary SQL.
    """
    return value.replace("'", "''")


class PostgresAdapter:
    """A ``WarehouseAdapter`` for PostgreSQL.

    Attributes
    ----------
    dialect: always ``"postgres"``.
    """

    dialect: str = "postgres"

    def _engine(self, credentials: Mapping[str, str]) -> _sa.Engine:
        """Build a SQLAlchemy engine from resolved credentials.

        Uses ``sqlalchemy.engine.URL.create`` rather than string interpolation so a
        ``coordinates``-sourced value (e.g. a ``host``/``database`` containing ``@``, ``:``,
        or ``/``) is percent-encoded into its URL component instead of corrupting — or
        redirecting — the connection URL.
        """
        _require_driver()
        host = credentials.get("host", "localhost")
        port = credentials.get("port", "5432")
        database = credentials.get("database", "")
        user = credentials.get("user")
        # A password without a user is meaningless for libpq — drop it, matching the
        # pre-existing (pre-URL.create) behavior of ignoring password when user is absent.
        password = credentials.get("password") if user else None
        url = _sa.engine.URL.create(
            drivername="postgresql+psycopg",
            username=user or None,
            password=password or None,
            host=host,
            port=int(port),
            database=database or None,
        )
        return _sa.create_engine(url)

    def execute(
        self,
        request: QueryRequest,
        credentials: Mapping[str, str],
    ) -> QueryResult:
        _require_driver()
        start = time.monotonic()
        engine = self._engine(credentials)
        with engine.connect() as conn:
            df = pd.read_sql(request.sql, conn)
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
            dialect="postgres",
            truncated=truncated,
            elapsed_ms=elapsed_ms,
        )

    def dry_run(
        self,
        request: QueryRequest,
        credentials: Mapping[str, str],
    ) -> CostEstimate:
        _require_driver()
        engine = self._engine(credentials)
        with engine.connect() as conn:
            # Postgres EXPLAIN returns one row per execution-plan operator; its length is a
            # count of plan nodes, not an estimate of the rows the query would scan or return.
            # A real row estimate would require parsing the per-operator ``rows=N`` in the
            # plan text, so report None (honest) rather than a misleading count.
            conn.execute(_sa.text(f"EXPLAIN {request.sql}"))
        return CostEstimate(
            dialect="postgres",
            estimated_rows=None,
        )

    def list_relations(
        self,
        credentials: Mapping[str, str],
        *,
        database: str | None = None,
        schema: str | None = None,
    ) -> pd.DataFrame:
        _require_driver()
        engine = self._engine(credentials)
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
        with engine.connect() as conn:
            df = pd.read_sql(sql, conn)
        df["column"] = None
        df["data_type"] = None
        df["nullable"] = None
        return df[list(RELATION_SCHEMA_COLUMNS)]

    def describe_relation(
        self,
        credentials: Mapping[str, str],
        relation: str,
        *,
        database: str | None = None,
        schema: str | None = None,
    ) -> pd.DataFrame:
        _require_driver()
        engine = self._engine(credentials)
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
        with engine.connect() as conn:
            df = pd.read_sql(sql, conn)
        df["database"] = database
        df["schema"] = schema
        df["table"] = relation
        return df[list(RELATION_SCHEMA_COLUMNS)]
