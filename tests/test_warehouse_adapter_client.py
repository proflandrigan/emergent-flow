"""Tests for `AdapterWarehouseClient` (Epic 13 Story 3/6, ADR 0018).

Uses a `_FakeAdapter` standing in for the real per-dialect adapters (DuckDB/
BigQuery/Redshift/Postgres, Story 6) to test the resolve-then-dispatch seam.
"""

from __future__ import annotations

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
    ColumnSchema,
    CostEstimate,
    QueryRequest,
    QueryResult,
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
