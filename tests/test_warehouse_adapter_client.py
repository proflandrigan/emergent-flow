"""Tests for `AdapterWarehouseClient` (Epic 13 Story 3/6, ADR 0018).

Uses a `_FakeAdapter` standing in for the real per-dialect adapters (DuckDB/
BigQuery/Redshift/Postgres, Story 6) to test the resolve-then-dispatch seam.
"""

from __future__ import annotations

import time
from collections.abc import Mapping

import pandas as pd
import pytest

from emergentflow.data.warehouse.adapter_client import AdapterWarehouseClient, NoAdapterError
from emergentflow.data.warehouse.profiles import (
    ConnectionProfile,
    ProfileStore,
    UnknownConnectionError,
)
from emergentflow.data.warehouse.protocol import (
    ByteScanCapExceededError,
    ColumnSchema,
    CostEstimate,
    QueryRequest,
    QueryResult,
    QueryTimeoutError,
    WarehouseClient,
)

_QUERY_RESULT = QueryResult(
    df=pd.DataFrame({"a": [1, 2]}),
    row_count=2,
    columns=(ColumnSchema(name="a", dtype="int64"),),
    dialect="duckdb",
)

_COST_ESTIMATE = CostEstimate(dialect="duckdb", bytes_scanned=100, estimated_rows=2, cost_usd=0.0)

_RELATIONS_FRAME = pd.DataFrame({"table": ["t1"]})
_DESCRIBE_FRAME = pd.DataFrame({"column": ["a"], "data_type": ["int64"]})


class _FakeAdapter:
    """Records the credentials/args it was called with; returns canned values."""

    dialect = "duckdb"

    def __init__(self) -> None:
        self.execute_calls: list[tuple[QueryRequest, Mapping[str, str]]] = []
        self.dry_run_calls: list[tuple[QueryRequest, Mapping[str, str]]] = []
        self.list_relations_calls: list[Mapping[str, str]] = []
        self.describe_relation_calls: list[tuple[Mapping[str, str], str]] = []

    def execute(self, request: QueryRequest, credentials: Mapping[str, str]) -> QueryResult:
        self.execute_calls.append((request, credentials))
        return _QUERY_RESULT

    def dry_run(self, request: QueryRequest, credentials: Mapping[str, str]) -> CostEstimate:
        self.dry_run_calls.append((request, credentials))
        return _COST_ESTIMATE

    def list_relations(
        self,
        credentials: Mapping[str, str],
        *,
        database: str | None = None,
        schema: str | None = None,
    ) -> pd.DataFrame:
        self.list_relations_calls.append(credentials)
        return _RELATIONS_FRAME

    def describe_relation(self, credentials: Mapping[str, str], relation: str) -> pd.DataFrame:
        self.describe_relation_calls.append((credentials, relation))
        return _DESCRIBE_FRAME


def _duckdb_profile() -> ConnectionProfile:
    return ConnectionProfile(name="duckdb_local", dialect="duckdb", auth_method="none")


def _postgres_profile() -> ConnectionProfile:
    return ConnectionProfile(name="pg_prod", dialect="postgres", auth_method="none")


def _request(connection: str = "duckdb_local") -> QueryRequest:
    return QueryRequest(sql="SELECT 1", dialect="duckdb", connection=connection)


def test_run_resolves_and_dispatches() -> None:
    store = ProfileStore()
    store.add(_duckdb_profile())
    fake = _FakeAdapter()
    client = AdapterWarehouseClient(store, {"duckdb": fake})

    result = client.run(_request())

    assert result is _QUERY_RESULT
    assert len(fake.execute_calls) == 1
    _, credentials = fake.execute_calls[0]
    assert credentials == {}


def test_run_unknown_connection_raises() -> None:
    store = ProfileStore()
    fake = _FakeAdapter()
    client = AdapterWarehouseClient(store, {"duckdb": fake})

    with pytest.raises(UnknownConnectionError):
        client.run(_request(connection="does_not_exist"))


def test_run_no_adapter_for_dialect_raises() -> None:
    store = ProfileStore()
    store.add(_postgres_profile())
    fake = _FakeAdapter()
    client = AdapterWarehouseClient(store, {"duckdb": fake})

    with pytest.raises(NoAdapterError):
        client.run(_request(connection="pg_prod"))


def test_adapter_client_satisfies_protocol() -> None:
    store = ProfileStore()
    fake = _FakeAdapter()
    client = AdapterWarehouseClient(store, {"duckdb": fake})

    assert isinstance(client, WarehouseClient)


class _ScanReportingAdapter:
    """A fake adapter whose ``execute`` reports a caller-specified bytes_scanned."""

    dialect = "duckdb"

    def __init__(self, bytes_scanned: int) -> None:
        self._bytes_scanned = bytes_scanned

    def execute(self, request: QueryRequest, credentials: Mapping[str, str]) -> QueryResult:
        return QueryResult(
            df=pd.DataFrame({"a": [1]}),
            row_count=1,
            columns=(ColumnSchema(name="a", dtype="int64"),),
            dialect="duckdb",
            bytes_scanned=self._bytes_scanned,
        )

    def dry_run(self, request: QueryRequest, credentials: Mapping[str, str]) -> CostEstimate:
        raise NotImplementedError


class _SlowAdapter:
    """A fake adapter whose ``execute`` sleeps before returning, for timeout tests."""

    dialect = "duckdb"

    def __init__(self, sleep_s: float) -> None:
        self._sleep_s = sleep_s

    def execute(self, request: QueryRequest, credentials: Mapping[str, str]) -> QueryResult:
        time.sleep(self._sleep_s)
        return _QUERY_RESULT

    def dry_run(self, request: QueryRequest, credentials: Mapping[str, str]) -> CostEstimate:
        raise NotImplementedError


def _timeout_profile(name: str, timeout_s: float) -> ConnectionProfile:
    return ConnectionProfile.model_construct(
        name=name, dialect="duckdb", auth_method="none", limits={"timeout_s": timeout_s}
    )


# ---- dry_run short-circuit ----


def test_run_with_dry_run_true_calls_dry_run_not_execute() -> None:
    store = ProfileStore()
    store.add(_duckdb_profile())
    fake = _FakeAdapter()
    client = AdapterWarehouseClient(store, {"duckdb": fake})
    request = QueryRequest(
        sql="SELECT 1", dialect="duckdb", connection="duckdb_local", dry_run=True
    )

    result = client.run(request)

    assert len(fake.dry_run_calls) == 1
    assert len(fake.execute_calls) == 0
    assert len(result.df) == 0
    assert result.bytes_scanned == _COST_ESTIMATE.bytes_scanned
    assert result.cost_usd == _COST_ESTIMATE.cost_usd


# ---- byte_scan_cap enforcement ----


def test_run_raises_byte_scan_cap_exceeded_error_on_breach() -> None:
    store = ProfileStore()
    store.add(_duckdb_profile())
    client = AdapterWarehouseClient(store, {"duckdb": _ScanReportingAdapter(5_000_000)})
    request = QueryRequest(
        sql="SELECT 1", dialect="duckdb", connection="duckdb_local", byte_scan_cap=1_000_000
    )

    with pytest.raises(ByteScanCapExceededError) as exc_info:
        client.run(request)

    assert exc_info.value.byte_scan_cap == 1_000_000
    assert exc_info.value.bytes_scanned == 5_000_000


def test_run_passes_when_under_byte_scan_cap() -> None:
    store = ProfileStore()
    store.add(_duckdb_profile())
    client = AdapterWarehouseClient(store, {"duckdb": _ScanReportingAdapter(500_000)})
    request = QueryRequest(
        sql="SELECT 1", dialect="duckdb", connection="duckdb_local", byte_scan_cap=1_000_000
    )

    result = client.run(request)

    assert result.bytes_scanned == 500_000


# ---- timeout enforcement ----


def test_run_raises_query_timeout_error_on_slow_adapter() -> None:
    store = ProfileStore()
    store.add(_timeout_profile("duckdb_local", timeout_s=0.2))
    client = AdapterWarehouseClient(store, {"duckdb": _SlowAdapter(sleep_s=2.0)})

    start = time.monotonic()
    with pytest.raises(QueryTimeoutError) as exc_info:
        client.run(_request())
    elapsed = time.monotonic() - start

    assert exc_info.value.timeout_s == 0.2
    assert elapsed < 1.5, f"took too long to raise: {elapsed}s"


def test_run_passes_when_under_timeout() -> None:
    store = ProfileStore()
    store.add(_timeout_profile("duckdb_local", timeout_s=5.0))
    fake = _FakeAdapter()
    client = AdapterWarehouseClient(store, {"duckdb": fake})

    result = client.run(_request())

    assert result is _QUERY_RESULT


def test_coordinates_merged_into_adapter_credentials() -> None:
    """Adapter receives both profile coordinates and resolved credential values."""
    profile = ConnectionProfile(
        name="bq_adc",
        dialect="duckdb",  # use duckdb dialect to match _FakeAdapter.dialect
        auth_method="adc",
        coordinates={"project": "my-gcp-project", "location": "us-central1"},
        credential_refs={},
    )
    store = ProfileStore()
    store.add(profile)
    fake = _FakeAdapter()
    client = AdapterWarehouseClient(store, {"duckdb": fake})

    client.run(QueryRequest(sql="SELECT 1", dialect="duckdb", connection="bq_adc"))

    assert len(fake.execute_calls) == 1
    _, credentials = fake.execute_calls[0]
    assert credentials["project"] == "my-gcp-project"
    assert credentials["location"] == "us-central1"
