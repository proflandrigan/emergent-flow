"""Tests for ``emergentflow.data.warehouse.replay``."""

from __future__ import annotations

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from emergentflow.data.warehouse.protocol import (
    ColumnSchema,
    FixtureMissError,
    QueryRequest,
    QueryResult,
    WarehouseClient,
)
from emergentflow.data.warehouse.replay import ReplayWarehouseClient, write_fixture


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
