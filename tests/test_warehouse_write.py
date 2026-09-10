"""Tests for the warehouse write path (issue #164 Gap 6b): ``ef.data.write_table``.

Covers the ADR 0018 read-only gate (``write_enabled``), the DuckDBAdapter write
(append/truncate/error + file persistence), the ``ReplayWarehouseClient`` refusal,
and the ``data.write_table`` node's client wiring.
"""

from __future__ import annotations

import pandas as pd
import pytest

from emergentflow.connections.profiles import WarehouseConnectionProfile
from emergentflow.data.warehouse.adapter_client import AdapterWarehouseClient
from emergentflow.data.warehouse.adapters.duckdb_adapter import DuckDBAdapter
from emergentflow.data.warehouse.profiles import ProfileStore
from emergentflow.data.warehouse.protocol import QueryRequest, WriteNotEnabledError
from emergentflow.data.warehouse.query import MissingWarehouseClientError
from emergentflow.data.warehouse.write import write_table


@pytest.fixture
def duckdb_client(tmp_path):
    store = ProfileStore()
    store.add(
        WarehouseConnectionProfile(
            name="dw",
            dialect="duckdb",
            coordinates={"path": str(tmp_path / "test.duckdb")},
            write_enabled=True,
        )
    )
    store.add(
        WarehouseConnectionProfile(
            name="dw_ro",
            dialect="duckdb",
            coordinates={"path": str(tmp_path / "test.duckdb")},
        )
    )
    return AdapterWarehouseClient(store, {"duckdb": DuckDBAdapter()})


@pytest.fixture
def frame() -> pd.DataFrame:
    return pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})


def test_write_table_read_only_profile_raises(duckdb_client, frame):
    with pytest.raises(WriteNotEnabledError, match="write_enabled"):
        write_table(frame, table="t1", connection="dw_ro", dialect="duckdb", client=duckdb_client)


def test_write_table_requires_client(frame):
    with pytest.raises(MissingWarehouseClientError):
        write_table(frame, table="t1", connection="dw", dialect="duckdb", client=None)


def test_write_table_append_and_persist(duckdb_client, frame):
    out = write_table(frame, table="t1", connection="dw", dialect="duckdb", client=duckdb_client)
    pd.testing.assert_frame_equal(out, frame)  # chainable pass-through
    q = QueryRequest(sql="SELECT * FROM t1", dialect="duckdb", connection="dw")
    assert duckdb_client.run(q).row_count == 3
    write_table(frame, table="t1", connection="dw", dialect="duckdb", client=duckdb_client)
    assert duckdb_client.run(q).row_count == 6


def test_write_table_truncate_resets(duckdb_client, frame):
    write_table(frame, table="t1", connection="dw", dialect="duckdb", client=duckdb_client)
    write_table(frame, table="t1", connection="dw", dialect="duckdb", client=duckdb_client)
    write_table(
        frame, table="t1", connection="dw", dialect="duckdb", mode="truncate", client=duckdb_client
    )
    q = QueryRequest(sql="SELECT * FROM t1", dialect="duckdb", connection="dw")
    assert duckdb_client.run(q).row_count == 3


def test_write_table_mode_error_refuses_existing(duckdb_client, frame):
    write_table(frame, table="t1", connection="dw", dialect="duckdb", client=duckdb_client)
    with pytest.raises(RuntimeError, match="exists"):
        write_table(
            frame, table="t1", connection="dw", dialect="duckdb", mode="error", client=duckdb_client
        )


def test_write_table_unknown_mode_raises(duckdb_client, frame):
    with pytest.raises(ValueError, match="mode"):
        write_table(
            frame, table="t2", connection="dw", dialect="duckdb", mode="bogus", client=duckdb_client
        )


def test_replay_client_refuses_writes(frame, tmp_path):
    from emergentflow.data.warehouse.protocol import WriteRequest
    from emergentflow.data.warehouse.replay import ReplayWarehouseClient

    client = ReplayWarehouseClient(tmp_path)
    request = WriteRequest(table="t1", dialect="duckdb", connection="dw")
    with pytest.raises(WriteNotEnabledError):
        client.write(request, frame)


def test_write_table_registered_as_public_op():
    from emergentflow.api import PUBLIC_OPS

    assert "ef.data.write_table" in PUBLIC_OPS


def test_write_table_node_requires_warehouse_client():
    from emergentflow.clients import ClientKind
    from emergentflow.nodes.examples.write_table import WriteTable

    assert ClientKind.WAREHOUSE in WriteTable().required_client_kinds()


def test_write_table_node_execute_with_client(duckdb_client, frame):
    from emergentflow.nodes.examples.write_table import WriteTable

    defn = WriteTable()
    node = defn.instantiate(table="t1", connection="dw", dialect="duckdb")
    result = defn.execute(node, inputs={"frame": frame.copy()}, client=duckdb_client)["result"]
    pd.testing.assert_frame_equal(result, frame)
    q = QueryRequest(sql="SELECT * FROM t1", dialect="duckdb", connection="dw")
    assert duckdb_client.run(q).row_count == 3
