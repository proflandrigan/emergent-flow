"""
emergentflow.data.warehouse.query
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``ef.data.query`` — the single wrapper both Epic 13 query nodes route through
(the raw-SQL node, Story 4, and the visual builder, Story 5). It builds a pure
``QueryRequest`` — validating a raw SQL string (read-only allow-list via
sqlglot) or, later, compiling a structured spec to dialect SQL — then delegates
the one effect to the injected ``WarehouseClient.run``. Keeping request-building
in one place is what makes ``codegen`` and ``execute`` route identically, so the
ADR-0002 equivalence holds by construction (the ADR-0017 ``ef.llm.call`` pattern
applied to a second effect).

Pure aside from the single delegated effect ``client.run(request)``. No
``os.environ``, no socket, no driver import — the effect lives entirely inside
the injected client.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.dialects.dialect import Dialect
from sqlglot.errors import SqlglotError

from emergentflow.api import public_op
from emergentflow.data.warehouse.protocol import QueryRequest, QueryResult, WarehouseClient
from emergentflow.data.warehouse.spec_compiler import SpecValidationError, compile_spec

__all__ = [
    "query",
    "MissingWarehouseClientError",
    "UnknownDialectError",
    "QueryParseError",
    "ReadOnlyViolationError",
    "QuerySpecNotSupportedError",
    "SpecValidationError",
]

# Top-level statement types permitted under a read-only connection (ADR 0018).
_READ_ONLY_ALLOWED = (exp.Select, exp.Union, exp.Intersect, exp.Except)


class MissingWarehouseClientError(RuntimeError):
    """Raised by ``query()`` when no ``WarehouseClient`` was injected (ADR 0018).

    The single place that enforces "a warehouse node needs a client" — both
    ``execute`` and a compiled module's ``main()`` route through ``query()``, so
    they raise identically for identical reasons (ADR 0002).
    """


class UnknownDialectError(ValueError):
    """Raised when the requested SQL dialect is not a known sqlglot dialect."""


class QueryParseError(ValueError):
    """Raised when a raw SQL string fails to parse in the requested dialect."""


class ReadOnlyViolationError(ValueError):
    """Raised when a non-SELECT/WITH statement runs under a read-only connection."""


class QuerySpecNotSupportedError(NotImplementedError):
    """Raised for the structured-``spec`` path, which arrives with Epic 13 Story 5."""


def _validate_dialect(dialect: str) -> None:
    try:
        Dialect.get_or_raise(dialect)
    except ValueError as exc:
        raise UnknownDialectError(
            f"Unknown SQL dialect {dialect!r}. Supported dialects are the sqlglot dialect "
            f"keys (e.g. 'duckdb', 'bigquery', 'redshift', 'postgres')."
        ) from exc


def _validate_read_only_sql(sql: str, dialect: str, read_only: bool) -> str:
    """Parse *sql* in *dialect*; under *read_only*, reject non-SELECT/WITH statements.

    Returns the SQL unchanged (LIMIT injection is the Story 4 raw-SQL node's job).
    """
    try:
        statements = [s for s in sqlglot.parse(sql, dialect=dialect) if s is not None]
    except SqlglotError as exc:
        # Catches both ParseError (bad grammar) and TokenError (e.g. an
        # unterminated string literal) -- siblings under SqlglotError, not a
        # subclass relationship -- so any malformed SQL surfaces as the
        # documented typed QueryParseError rather than an uncaught sqlglot
        # exception leaking out of the public ef.data.query op.
        raise QueryParseError(f"Could not parse SQL in dialect {dialect!r}: {exc}") from exc
    if not statements:
        raise QueryParseError(f"No SQL statement found in {sql!r}.")
    if read_only:
        for stmt in statements:
            if not isinstance(stmt, _READ_ONLY_ALLOWED):
                raise ReadOnlyViolationError(
                    f"Statement type {type(stmt).__name__.upper()!r} is not permitted under a "
                    "read-only connection; only SELECT / WITH / set-operations are allowed. "
                    "Enable writes on the connection profile to run a mutating statement."
                )
    return sql


def _inject_limit(sql: str, dialect: str, max_rows: int | None) -> str:
    """Inject a LIMIT clause into *sql* when *max_rows* is set and no LIMIT exists.

    Parses the SQL via sqlglot, checks each top-level statement's own ``limit``
    arg (``stmt.args.get("limit")``, not a recursive ``.find()`` — a subquery's
    LIMIT must not be mistaken for the outer statement already having one, which
    would let an unbounded outer query slip past the *max_rows* cap). If none is
    found and *max_rows* is not None, appends ``LIMIT max_rows + 1`` — one row
    past the cap, so the adapter can tell "there were exactly max_rows matching
    rows" apart from "there were more and we got cut off" (it truncates back down
    to max_rows itself; see the adapters' ``truncated`` check). Returns the
    modified SQL string rendered in *dialect*. If max_rows is None, returns sql
    unchanged.
    """
    if max_rows is None:
        return sql
    statements = [s for s in sqlglot.parse(sql, dialect=dialect) if s is not None]
    for stmt in statements:
        if stmt.args.get("limit") is None:
            stmt.set("limit", exp.Limit(expression=exp.Literal.number(max_rows + 1)))
    return "; ".join(stmt.sql(dialect=dialect) for stmt in statements)


def _prepare_query_spec(spec: dict, dialect: str) -> str:
    """Validate and compile a structured query spec to dialect SQL.

    The single validation gate shared by ``codegen`` and ``execute`` (the
    ``_prepare_declarative`` pattern), so both paths accept/reject identical
    specs. Wraps ``compile_spec`` and re-raises ``SpecValidationError`` as-is
    (it is already a ``ValueError`` subclass).
    """
    return compile_spec(spec, dialect)


@public_op(name="ef.data.query")
def query(
    *,
    connection: str,
    client: WarehouseClient | None,
    dialect: str,
    sql: str | None = None,
    spec: dict | None = None,
    max_rows: int | None = None,
    byte_scan_cap: int | None = None,
    read_only: bool = True,
    dry_run: bool = False,
) -> QueryResult:
    """Run one warehouse query through *client* and return a ``QueryResult``.

    Exactly one of *sql* (a raw SQL string) or *spec* (a structured query spec)
    must be given. The *sql* path validates the statement (read-only allow-list
    via sqlglot); the *spec* path compiles to dialect SQL and arrives with Story 5.

    Pure aside from the single delegated effect ``client.run(request)``.

    Raises
    ------
    MissingWarehouseClientError
        If *client* is ``None``.
    ValueError
        If neither or both of *sql*/*spec* are given.
    UnknownDialectError, QueryParseError, ReadOnlyViolationError
        On dialect / parse / read-only violations.
    SpecValidationError
        If *spec* is given but invalid (missing source, bad aggregate, etc.).
    """
    if client is None:
        raise MissingWarehouseClientError(
            "ef.data.query requires an injected WarehouseClient; pass it via "
            "execute(graph, clients=Clients(warehouse=...)) or the compiled module's "
            "main(clients=...)."
        )
    if (sql is None) == (spec is None):
        raise ValueError("ef.data.query requires exactly one of sql=... or spec=... (not both).")

    _validate_dialect(dialect)

    if spec is not None:
        compiled_sql = _prepare_query_spec(spec, dialect)
        compiled_sql = _inject_limit(compiled_sql, dialect, max_rows)
        request = QueryRequest(
            sql=compiled_sql,
            dialect=dialect,
            connection=connection,
            params=(),
            max_rows=max_rows,
            byte_scan_cap=byte_scan_cap,
            read_only=read_only,
            dry_run=dry_run,
        )
        return client.run(request)

    assert sql is not None  # narrowed by the exactly-one check above
    validated_sql = _validate_read_only_sql(sql, dialect, read_only)
    compiled_sql = _inject_limit(validated_sql, dialect, max_rows)

    request = QueryRequest(
        sql=compiled_sql,
        dialect=dialect,
        connection=connection,
        params=(),
        max_rows=max_rows,
        byte_scan_cap=byte_scan_cap,
        read_only=read_only,
        dry_run=dry_run,
    )
    return client.run(request)
