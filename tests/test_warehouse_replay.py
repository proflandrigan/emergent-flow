"""Tests for ``emergentflow.data.warehouse.replay``."""

from __future__ import annotations

import dataclasses

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from emergentflow.data.warehouse.protocol import (
    ColumnSchema,
    CostEstimate,
    FixtureMissError,
    QueryRequest,
    QueryResult,
    WarehouseClient,
)
from emergentflow.data.warehouse.replay import (
    ReplayWarehouseClient,
    write_describe_fixture,
    write_dry_run_fixture,
    write_fixture,
    write_relations_fixture,
)


def _make_request() -> QueryRequest:
    return QueryRequest(
        sql="SELECT id, name, score FROM widgets",
        dialect="duckdb",
        connection="warehouse_prod",
    )


def _make_result() -> QueryResult:
    df = pd.DataFrame(
        {
            "id": [1, 2, 3],
            "name": ["alpha", "beta", "gamma"],
            "score": [1.5, 2.25, 3.125],
        }
    )
    columns = (
        ColumnSchema(name="id", dtype="int64", nullable=False),
        ColumnSchema(name="name", dtype="object", nullable=True),
        ColumnSchema(name="score", dtype="float64", nullable=True),
    )
    return QueryResult(
        df=df,
        row_count=3,
        columns=columns,
        dialect="duckdb",
        bytes_scanned=1024,
        cost_usd=0.0,
        truncated=False,
        elapsed_ms=12.5,
    )


def test_write_then_replay_round_trips(tmp_path):
    request = _make_request()
    result = _make_result()

    write_fixture(tmp_path, request, result)

    replayed = ReplayWarehouseClient(tmp_path).run(request)

    assert_frame_equal(replayed.df, result.df)
    assert replayed.row_count == result.row_count
    assert replayed.dialect == result.dialect
    assert replayed.columns == result.columns
    assert replayed.truncated == result.truncated


def test_replay_miss_raises_fixture_miss_error(tmp_path):
    request = _make_request()

    with pytest.raises(FixtureMissError) as exc_info:
        ReplayWarehouseClient(tmp_path).run(request)

    message = str(exc_info.value)
    assert request.content_hash() in message
    assert "write_fixture" in message


def test_fixture_filename_is_content_hash(tmp_path):
    request = _make_request()
    result = _make_result()

    path = write_fixture(tmp_path, request, result)

    assert path.name == f"{request.content_hash()}.json"


def test_replay_client_satisfies_protocol(tmp_path):
    assert isinstance(ReplayWarehouseClient(tmp_path), WarehouseClient)


def _make_relations_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "database": ["analytics", "analytics"],
            "schema": ["public", "public"],
            "table": ["widgets", "orders"],
            "column": [float("nan"), float("nan")],
            "data_type": [float("nan"), float("nan")],
            "nullable": [float("nan"), float("nan")],
        }
    )


def _make_describe_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "database": [float("nan"), float("nan")],
            "schema": [float("nan"), float("nan")],
            "table": ["widgets", "widgets"],
            "column": ["id", "name"],
            "data_type": ["int64", "object"],
            "nullable": [False, True],
        }
    )


def test_write_then_replay_list_relations_round_trips(tmp_path):
    df = _make_relations_frame()
    write_relations_fixture(tmp_path, "warehouse_prod", df, schema="public")

    replayed = ReplayWarehouseClient(tmp_path).list_relations("warehouse_prod", schema="public")

    assert_frame_equal(replayed, df)


def test_list_relations_miss_raises_fixture_miss_error(tmp_path):
    with pytest.raises(FixtureMissError) as exc_info:
        ReplayWarehouseClient(tmp_path).list_relations("warehouse_prod")

    message = str(exc_info.value)
    assert "write_relations_fixture" in message


def test_write_then_replay_describe_relation_round_trips(tmp_path):
    df = _make_describe_frame()
    write_describe_fixture(tmp_path, "warehouse_prod", "widgets", df)

    replayed = ReplayWarehouseClient(tmp_path).describe_relation("warehouse_prod", "widgets")

    assert_frame_equal(replayed, df)


def test_describe_relation_miss_raises_fixture_miss_error(tmp_path):
    with pytest.raises(FixtureMissError) as exc_info:
        ReplayWarehouseClient(tmp_path).describe_relation("warehouse_prod", "widgets")

    message = str(exc_info.value)
    assert "write_describe_fixture" in message


def test_list_relations_and_describe_relation_fixtures_do_not_collide(tmp_path):
    relations_df = _make_relations_frame()
    describe_df = _make_describe_frame()
    write_relations_fixture(tmp_path, "warehouse_prod", relations_df, schema="public")
    write_describe_fixture(tmp_path, "warehouse_prod", "public", describe_df)

    client = ReplayWarehouseClient(tmp_path)
    out_relations = client.list_relations("warehouse_prod", schema="public")
    out_describe = client.describe_relation("warehouse_prod", "public")

    assert_frame_equal(out_relations, relations_df)
    assert_frame_equal(out_describe, describe_df)


def _make_estimate() -> CostEstimate:
    return CostEstimate(dialect="duckdb", bytes_scanned=999, estimated_rows=42, cost_usd=0.05)


def test_write_then_replay_dry_run_round_trips(tmp_path):
    request = dataclasses.replace(_make_request(), dry_run=True)
    estimate = _make_estimate()

    write_dry_run_fixture(tmp_path, request, estimate)

    replayed = ReplayWarehouseClient(tmp_path).dry_run(request)

    assert replayed == estimate


def test_dry_run_miss_raises_fixture_miss_error(tmp_path):
    request = dataclasses.replace(_make_request(), dry_run=True)

    with pytest.raises(FixtureMissError) as exc_info:
        ReplayWarehouseClient(tmp_path).dry_run(request)

    message = str(exc_info.value)
    assert "write_dry_run_fixture" in message


def test_run_with_dry_run_true_short_circuits_to_empty_result(tmp_path):
    request = dataclasses.replace(_make_request(), dry_run=True)
    estimate = _make_estimate()
    write_dry_run_fixture(tmp_path, request, estimate)

    result = ReplayWarehouseClient(tmp_path).run(request)

    assert len(result.df) == 0
    assert result.row_count == 0
    assert result.bytes_scanned == estimate.bytes_scanned
    assert result.cost_usd == estimate.cost_usd
