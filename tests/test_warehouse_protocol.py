"""Tests for emergentflow.data.warehouse.protocol.QueryRequest."""

from __future__ import annotations

import dataclasses

import pandas as pd
import pytest

from emergentflow.api import is_inspectable
from emergentflow.data.warehouse.protocol import (
    ColumnSchema,
    CostEstimate,
    FixtureMissError,
    QueryRequest,
    QueryResult,
    WarehouseClient,
)


def _make_request(**overrides: object) -> QueryRequest:
    fields: dict[str, object] = {
        "sql": "SELECT 1",
        "dialect": "duckdb",
        "connection": "warehouse_prod",
        "params": (("limit", 10),),
        "max_rows": 1000,
        "byte_scan_cap": None,
        "read_only": True,
        "dry_run": False,
    }
    fields.update(overrides)
    return QueryRequest(**fields)  # type: ignore[arg-type]


def test_query_request_content_hash_stable() -> None:
    a = _make_request()
    b = _make_request()
    assert a.content_hash() == b.content_hash()

    diff_sql = _make_request(sql="SELECT 2")
    assert diff_sql.content_hash() != a.content_hash()

    diff_dialect = _make_request(dialect="bigquery")
    assert diff_dialect.content_hash() != a.content_hash()

    diff_connection = _make_request(connection="warehouse_staging")
    assert diff_connection.content_hash() != a.content_hash()


def test_query_request_content_hash_is_hex_sha256() -> None:
    request = _make_request()
    digest = request.content_hash()
    assert len(digest) == 64
    assert digest == digest.lower()
    int(digest, 16)  # raises ValueError if not valid hex


def test_query_request_is_frozen() -> None:
    request = _make_request()
    with pytest.raises(dataclasses.FrozenInstanceError):
        request.sql = "SELECT 2"  # type: ignore[misc]


def test_query_request_hash_ignores_field_order_in_params() -> None:
    params = (("a", 1), ("b", 2))
    first = QueryRequest(
        sql="SELECT 1",
        dialect="duckdb",
        connection="warehouse_prod",
        params=params,
    )
    second = QueryRequest(
        sql="SELECT 1",
        dialect="duckdb",
        connection="warehouse_prod",
        params=tuple(params),
    )
    assert first.content_hash() == second.content_hash()


def _make_query_result(**overrides: object) -> QueryResult:
    fields: dict[str, object] = {
        "df": pd.DataFrame({"a": [1, 2], "b": ["x", "y"]}),
        "row_count": 2,
        "columns": (ColumnSchema("a", "int64"), ColumnSchema("b", "object")),
        "dialect": "duckdb",
    }
    fields.update(overrides)
    return QueryResult(**fields)  # type: ignore[arg-type]


def test_query_result_is_inspectable() -> None:
    result = _make_query_result()
    assert is_inspectable(result) is True


def test_query_result_holds_no_live_cursor() -> None:
    result = _make_query_result()
    allowed_scalar_types = (pd.DataFrame, int, str, bool, float, type(None))
    for field in dataclasses.fields(result):
        value = getattr(result, field.name)
        if isinstance(value, tuple):
            assert all(isinstance(item, ColumnSchema) for item in value)
        else:
            assert isinstance(value, allowed_scalar_types)


def test_cost_estimate_is_inspectable() -> None:
    assert is_inspectable(CostEstimate(dialect="duckdb")) is True


def test_column_schema_fields() -> None:
    schema = ColumnSchema("a", "int64")
    assert schema.nullable is True


def test_warehouse_client_protocol_runtime_checkable() -> None:
    class StubWarehouseClient:
        def run(self, request: object) -> object:
            raise NotImplementedError

        def dry_run(self, request: object) -> object:
            raise NotImplementedError

        def list_relations(self, connection: object, **kwargs: object) -> object:
            raise NotImplementedError

        def describe_relation(self, connection: object, relation: object) -> object:
            raise NotImplementedError

    assert isinstance(StubWarehouseClient(), WarehouseClient)
    assert not isinstance(object(), WarehouseClient)


def test_fixture_miss_error_is_lookup_error() -> None:
    assert issubclass(FixtureMissError, LookupError)
