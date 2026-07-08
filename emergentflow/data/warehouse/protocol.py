"""
emergentflow.data.warehouse.protocol
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The ``WarehouseClient`` seam types (Epic 13, ADR 0018): the single injected
boundary between the pure SDK core and any real or replayed warehouse query.

``QueryRequest`` is a pure, JSON-native, hashable description of one query —
building it from node inputs (including compiling a structured spec to dialect
SQL) is pure. It carries a connection-profile **name** only, never a
credential (ADR 0018 secrets rule), so its content hash — used to key replay
fixtures — is safe to compute and commit.

This module mirrors ``emergentflow.llm.protocol`` deliberately: the warehouse
effect is the same shape of problem as the LLM effect (non-deterministic,
credentialed, metered network I/O), so it reuses the same seam pattern rather
than inventing a new one.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

import pandas as pd


@dataclasses.dataclass(frozen=True)
class QueryRequest:
    """A pure, JSON-native description of one warehouse query.

    Attributes
    ----------
    sql: the fully-compiled SQL string to run (dialect-specific). Building it —
        whether from a raw-SQL node or by compiling a structured spec via
        sqlglot — is pure and happens before this request is constructed.
    dialect: the sqlglot dialect key the ``sql`` is written in, e.g.
        ``"duckdb"``, ``"bigquery"``, ``"redshift"``, ``"postgres"``.
    connection: the connection-profile **name** (e.g. ``"warehouse_prod"``) —
        never a host, DSN, or credential (ADR 0018). The effectful client
        resolves the profile to live credentials at ``run()`` time.
    params: bound query parameters (JSON-native), keyed by name; empty by
        default. Kept explicit so parameterized queries hash stably.
    max_rows: optional row cap the client enforces (LIMIT injection / truncation).
    byte_scan_cap: optional scanned-bytes cap the client enforces
        (e.g. BigQuery ``maximum_bytes_billed``).
    read_only: when True (the default), the client rejects non-SELECT/WITH
        statements — the ADR 0018 read-only-by-default safety rule.
    dry_run: when True, the client returns a cost estimate without running the
        query (see ``CostEstimate``).
    """

    sql: str
    dialect: str
    connection: str
    params: tuple[tuple[str, Any], ...] = ()
    max_rows: int | None = None
    byte_scan_cap: int | None = None
    read_only: bool = True
    dry_run: bool = False

    def content_hash(self) -> str:
        """Return a stable sha256 hex digest identifying this request's content.

        Used by ``ReplayWarehouseClient`` to key recorded fixtures. Built from a
        JSON-native, sorted-keys serialization of every field so the hash is
        stable across process runs and Python versions. Nothing secret is
        present to exclude — the connection is a profile *name* (ADR 0018).
        """
        payload = {
            "sql": self.sql,
            "dialect": self.dialect,
            "connection": self.connection,
            "params": [list(pair) for pair in self.params],
            "max_rows": self.max_rows,
            "byte_scan_cap": self.byte_scan_cap,
            "read_only": self.read_only,
            "dry_run": self.dry_run,
        }
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclasses.dataclass(frozen=True)
class ColumnSchema:
    """One column's schema in a ``QueryResult`` — JSON-native, inspectable.

    ``dtype`` is a string label (e.g. ``"int64"``, ``"object"``, ``"float64"``)
    so the schema round-trips through JSON without a live dtype object.
    """

    name: str
    dtype: str
    nullable: bool = True


@dataclasses.dataclass(frozen=True)
class QueryResult:
    """The inspectable result of one warehouse query (Epic 13 Story 2, ADR 0018).

    Carries a **tidy** ``pandas.DataFrame`` plus JSON-native metadata. A live
    connection, cursor, or driver object is **never** stored here — only the
    materialized frame and plain metadata, so the result rides the ``@public_op``
    inspectable contract (``emergentflow.api.is_inspectable`` accepts a dataclass
    instance) and the ADR-0002 equivalence gate compares it value-for-value.

    Note: do not compare two ``QueryResult`` instances with ``==`` — the ``df``
    field makes dataclass equality ambiguous (a DataFrame ``==`` returns a
    DataFrame). Compare the frame with ``pandas.testing.assert_frame_equal`` and
    the metadata fields individually (the equivalence harness does exactly this).

    Attributes
    ----------
    df: the tidy result frame.
    row_count: number of rows in ``df`` (after any cap).
    columns: per-column schema (name/dtype/nullable).
    dialect: the sqlglot dialect the query ran under.
    bytes_scanned: scanned bytes reported by the warehouse, if available.
    cost_usd: estimated cost for this query, if computable.
    truncated: True when a row/byte cap trimmed the result.
    elapsed_ms: wall-clock latency reported by the client, if available.
    """

    df: pd.DataFrame
    row_count: int
    columns: tuple[ColumnSchema, ...]
    dialect: str
    bytes_scanned: int | None = None
    cost_usd: float | None = None
    truncated: bool = False
    elapsed_ms: float | None = None


@dataclasses.dataclass(frozen=True)
class CostEstimate:
    """A ``dry_run`` cost estimate: what a query *would* scan without running it.

    Returned by ``WarehouseClient.dry_run`` (ADR 0018 dry-run-before-spend rule)
    so the canvas can warn "this scans 4.2 TB" before an analyst hits run.
    JSON-native and inspectable.
    """

    dialect: str
    bytes_scanned: int | None = None
    estimated_rows: int | None = None
    cost_usd: float | None = None


def dry_run_result(estimate: CostEstimate) -> QueryResult:
    """Wrap a ``dry_run`` cost estimate as an empty, inspectable ``QueryResult``.

    ``WarehouseClient.run()`` returns this instead of executing the query when
    ``QueryRequest.dry_run`` is True (Epic 13 Story 8), so a query node's
    ``DataFrame`` OUT port contract still holds even though no query actually
    ran — the frame is empty and the cost metadata carries the estimate, ready
    for the canvas to render a "this scans 4.2 TB" warning before the analyst
    commits to a real run.
    """
    return QueryResult(
        df=pd.DataFrame(),
        row_count=0,
        columns=(),
        dialect=estimate.dialect,
        bytes_scanned=estimate.bytes_scanned,
        cost_usd=estimate.cost_usd,
        truncated=False,
        elapsed_ms=None,
    )


#: Standard column order for the tidy schema frames returned by
#: ``WarehouseClient.list_relations`` / ``describe_relation`` (Story 7 fills these
#: in concretely). Kept here so the frame shape is defined in one place.
RELATION_SCHEMA_COLUMNS: tuple[str, ...] = (
    "database",
    "schema",
    "table",
    "column",
    "data_type",
    "nullable",
)


class FixtureMissError(LookupError):
    """Raised by ``ReplayWarehouseClient`` when a request hash has no fixture.

    Mirrors ``emergentflow.llm.protocol.FixtureMissError``. The message includes
    the request's ``content_hash()`` and a copy-pasteable ``write_fixture(...)``
    hint so a developer hitting it in a test run knows exactly what to record.
    """


class MissingDriverError(RuntimeError):
    """Raised when a cloud warehouse adapter's driver package is not installed.

    Each cloud adapter (BigQuery, Redshift, Postgres) depends on an optional
    extra; the base install never pulls cloud drivers. When an adapter is
    instantiated without its driver, this error tells the user the exact
    ``pip install`` target (the ``[bayes]`` discipline, applied to warehouses).
    """

    def __init__(self, extra: str) -> None:
        self.extra = extra
        super().__init__(
            f"This warehouse adapter requires the optional dependency group {extra!r}; "
            f"install it with: pip install {extra}"
        )


class ByteScanCapExceededError(RuntimeError):
    """Raised when a query scanned more bytes than its ``byte_scan_cap`` allows.

    ADR 0018's row/byte-cap safety rule (Epic 13 Story 8): enforced at the
    client edge only, never inline in ``execute``/``compile_to_code``. For
    BigQuery this is a backstop — ``maximum_bytes_billed`` is also set on the
    job config (Story 6) so the warehouse itself may reject an over-budget
    query before this ever fires; for any adapter that reports ``bytes_scanned``
    without a native billing cap, this is the only enforcement.
    """

    def __init__(self, byte_scan_cap: int, bytes_scanned: int) -> None:
        self.byte_scan_cap = byte_scan_cap
        self.bytes_scanned = bytes_scanned
        super().__init__(
            f"Query scanned {bytes_scanned} bytes, exceeding the connection's "
            f"byte_scan_cap of {byte_scan_cap} bytes."
        )


def enforce_byte_scan_cap(request: QueryRequest, result: QueryResult) -> None:
    """Raise ``ByteScanCapExceededError`` if *result* breached *request*'s cap.

    A no-op when either ``request.byte_scan_cap`` or ``result.bytes_scanned``
    is ``None``. Every ``WarehouseClient`` implementation (live or replayed)
    must call this on its way out of ``run()`` — the cap is a property of the
    request/result pair, not of how the result was produced, so it applies
    identically whether the bytes came from a live adapter or a recorded
    fixture (Epic 13 Story 8).
    """
    if (
        request.byte_scan_cap is not None
        and result.bytes_scanned is not None
        and result.bytes_scanned > request.byte_scan_cap
    ):
        raise ByteScanCapExceededError(request.byte_scan_cap, result.bytes_scanned)


class QueryTimeoutError(RuntimeError):
    """Raised when a query runs longer than its connection profile's ``timeout_s``.

    ADR 0018's timeout safety rule (Epic 13 Story 8): enforced at the client
    edge only, never inline in ``execute``/``compile_to_code``. The underlying
    query call is abandoned in a background thread (Python cannot forcibly
    kill a running thread), not cancelled outright — this error simply stops
    the client from waiting on it any longer.
    """

    def __init__(self, timeout_s: float) -> None:
        self.timeout_s = timeout_s
        super().__init__(
            f"Query exceeded its {timeout_s}s timeout "
            f"(see the connection profile's limits.timeout_s)."
        )


@runtime_checkable
class WarehouseClient(Protocol):
    """The injected data-source seam every query node depends on (ADR 0018).

    Mirrors ``emergentflow.llm.protocol.LLMClient``: any object exposing these
    methods satisfies the protocol structurally (no inheritance required).
    ``ReplayWarehouseClient`` (pure, tests + the gate) and
    ``AdapterWarehouseClient`` (effectful, per-dialect adapters) are the
    implementations that ship with this package.
    """

    def run(self, request: QueryRequest) -> QueryResult:
        """Run one query and return an inspectable ``QueryResult``."""
        ...

    def dry_run(self, request: QueryRequest) -> CostEstimate:
        """Estimate what *request* would scan without running it."""
        ...

    def list_relations(
        self, connection: str, *, database: str | None = None, schema: str | None = None
    ) -> pd.DataFrame:
        """Return a tidy schema frame of relations under *connection*."""
        ...

    def describe_relation(
        self,
        connection: str,
        relation: str,
        *,
        database: str | None = None,
        schema: str | None = None,
    ) -> pd.DataFrame:
        """Return a tidy column-schema frame for *relation* under *connection*.

        *database*/*schema* disambiguate a *relation* name that exists in more than one
        schema (or, for BigQuery, is qualified as ``dataset.table``) — optional because most
        connections have no same-named relation across schemas.
        """
        ...


@runtime_checkable
class WarehouseAdapter(Protocol):
    """A per-dialect backend (ADR 0018 breadth-as-data): execute a resolved query.

    ``AdapterWarehouseClient`` resolves a connection profile to live credentials
    and dispatches to the adapter matching the profile's dialect. Concrete
    adapters (DuckDB, BigQuery, Redshift, Postgres) ship in Epic 13 Story 6; this
    protocol is the contract they implement. The adapter receives already-resolved
    ``credentials`` (a plain mapping) — it never reads the profile store or the IR.
    """

    dialect: str

    def execute(self, request: QueryRequest, credentials: Mapping[str, str]) -> QueryResult:
        """Run *request* against the resolved connection and return a ``QueryResult``."""
        ...

    def dry_run(self, request: QueryRequest, credentials: Mapping[str, str]) -> CostEstimate:
        """Estimate *request* against the resolved connection."""
        ...

    def list_relations(
        self,
        credentials: Mapping[str, str],
        *,
        database: str | None = None,
        schema: str | None = None,
    ) -> pd.DataFrame:
        """Return a tidy schema frame of relations for the resolved connection."""
        ...

    def describe_relation(
        self,
        credentials: Mapping[str, str],
        relation: str,
        *,
        database: str | None = None,
        schema: str | None = None,
    ) -> pd.DataFrame:
        """Return a tidy column-schema frame for *relation*, optionally scoped to
        *database*/*schema* to disambiguate a same-named relation elsewhere."""
        ...
