"""Tests for the warehouse write path (issue #164 Gap 6b): ``ef.data.write_table``.

Covers the ADR 0018 read-only gate (``write_enabled``), the DuckDBAdapter write
(append/truncate/error + file persistence), the ``ReplayWarehouseClient`` refusal,
and the ``data.write_table`` node's client wiring.
"""

from __future__ import annotations

import duckdb
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
    from emergentflow.data.warehouse.protocol import WriteNotSupportedError, WriteRequest
    from emergentflow.data.warehouse.replay import ReplayWarehouseClient

    client = ReplayWarehouseClient(tmp_path)
    request = WriteRequest(table="t1", dialect="duckdb", connection="dw")
    with pytest.raises(WriteNotSupportedError, match="replay"):
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


def _rows(client, sql):
    return client.run(QueryRequest(sql=sql, dialect="duckdb", connection="dw")).df


def test_duckdb_append_matches_columns_by_name(duckdb_client):
    first = pd.DataFrame({"user_id": [1, 2], "account_id": [100, 200]})
    swapped = pd.DataFrame({"account_id": [300], "user_id": [3]})
    write_table(first, table="acct", connection="dw", dialect="duckdb", client=duckdb_client)
    write_table(swapped, table="acct", connection="dw", dialect="duckdb", client=duckdb_client)
    out = _rows(duckdb_client, "SELECT user_id, account_id FROM acct ORDER BY user_id")
    assert out.to_dict("records") == [
        {"user_id": 1, "account_id": 100},
        {"user_id": 2, "account_id": 200},
        {"user_id": 3, "account_id": 300},
    ]


def test_duckdb_table_name_cannot_inject_sql(duckdb_client, frame):
    write_table(frame, table="victim", connection="dw", dialect="duckdb", client=duckdb_client)
    evil = 'junk" AS SELECT 1; DROP TABLE victim; --'
    write_table(frame, table=evil, connection="dw", dialect="duckdb", client=duckdb_client)
    assert _rows(duckdb_client, "SELECT count(*) AS n FROM victim")["n"].iloc[0] == 3
    names = _rows(duckdb_client, "SELECT table_name FROM information_schema.tables")
    assert evil in set(names["table_name"])
    # Reserved words and spaces are ordinary identifiers once quoted.
    for name in ("select", "my table", "Order"):
        write_table(frame, table=name, connection="dw", dialect="duckdb", client=duckdb_client)


def test_duckdb_schema_qualified_tables(duckdb_client, frame, tmp_path):
    import duckdb

    conn = duckdb.connect(str(tmp_path / "test.duckdb"))
    conn.execute("CREATE SCHEMA mart")
    conn.close()
    write_table(frame, table="mart.sales", connection="dw", dialect="duckdb", client=duckdb_client)
    write_table(frame, table="mart.sales", connection="dw", dialect="duckdb", client=duckdb_client)
    assert _rows(duckdb_client, "SELECT count(*) AS n FROM mart.sales")["n"].iloc[0] == 6
    with pytest.raises(RuntimeError, match="exists"):
        write_table(
            frame,
            table="mart.sales",
            connection="dw",
            dialect="duckdb",
            mode="error",
            client=duckdb_client,
        )
    # An unqualified name lives in main and is not confused with mart.sales.
    write_table(
        frame, table="sales", connection="dw", dialect="duckdb", mode="error", client=duckdb_client
    )
    assert _rows(duckdb_client, "SELECT count(*) AS n FROM main.sales")["n"].iloc[0] == 3


def test_duckdb_in_memory_profile_refuses_writes(frame):
    from emergentflow.data import DataError

    store = ProfileStore()
    store.add(WarehouseConnectionProfile(name="mem", dialect="duckdb", write_enabled=True))
    client = AdapterWarehouseClient(store, {"duckdb": DuckDBAdapter()})
    with pytest.raises(DataError, match="path"):
        write_table(frame, table="t", connection="mem", dialect="duckdb", client=client)


def test_duckdb_truncate_is_atomic_and_keeps_the_table(duckdb_client, frame):
    write_table(frame, table="t1", connection="dw", dialect="duckdb", client=duckdb_client)
    bad = pd.DataFrame({"zzz": [1.0]})
    with pytest.raises(Exception, match="zzz"):
        write_table(
            bad,
            table="t1",
            connection="dw",
            dialect="duckdb",
            mode="truncate",
            client=duckdb_client,
        )
    out = _rows(duckdb_client, "SELECT * FROM t1")
    assert len(out) == 3 and list(out.columns) == ["a", "b"]
    write_table(
        frame.iloc[:1],
        table="t1",
        connection="dw",
        dialect="duckdb",
        mode="truncate",
        client=duckdb_client,
    )
    assert len(_rows(duckdb_client, "SELECT * FROM t1")) == 1


def test_write_request_validates_mode_and_table():
    from emergentflow.data.warehouse.protocol import WriteRequest

    with pytest.raises(ValueError, match="mode"):
        WriteRequest(table="t", dialect="duckdb", connection="dw", mode="frobnicate")
    with pytest.raises(ValueError, match="table"):
        WriteRequest(table="", dialect="duckdb", connection="dw")


def test_write_table_validates_dialect_and_profile_mismatch(duckdb_client, frame):
    from emergentflow.data.warehouse.query import UnknownDialectError

    with pytest.raises(UnknownDialectError):
        write_table(frame, table="t", connection="dw", dialect="nonsense", client=duckdb_client)
    with pytest.raises(ValueError, match="does not match"):
        write_table(frame, table="t", connection="dw", dialect="postgres", client=duckdb_client)


def test_write_to_adapter_without_write_support_is_typed(frame):
    from emergentflow.data.warehouse.protocol import (
        WarehouseAdapter,
        WritableWarehouseAdapter,
        WriteNotSupportedError,
    )

    class _ReadOnlyAdapter:
        dialect = "duckdb"

        def execute(self, request, credentials):
            raise NotImplementedError

        def dry_run(self, request, credentials):
            raise NotImplementedError

        def list_relations(self, credentials, *, database=None, schema=None):
            raise NotImplementedError

        def describe_relation(self, credentials, relation, *, database=None, schema=None):
            raise NotImplementedError

    adapter = _ReadOnlyAdapter()
    assert isinstance(adapter, WarehouseAdapter)  # pre-existing adapters still satisfy the protocol
    assert not isinstance(adapter, WritableWarehouseAdapter)
    assert isinstance(DuckDBAdapter(), WritableWarehouseAdapter)
    store = ProfileStore()
    store.add(WarehouseConnectionProfile(name="ro", dialect="duckdb", write_enabled=True))
    client = AdapterWarehouseClient(store, {"duckdb": adapter})
    with pytest.raises(WriteNotSupportedError, match="duckdb"):
        write_table(frame, table="t", connection="ro", dialect="duckdb", client=client)


def test_dml_query_requires_write_enabled(duckdb_client):
    request = QueryRequest(
        sql="CREATE TABLE zz AS SELECT 1 AS a",
        dialect="duckdb",
        connection="dw_ro",
        read_only=False,
    )
    with pytest.raises(WriteNotEnabledError, match="write_enabled"):
        duckdb_client.run(request)


class _RecordingWarehouseClient:
    """Test double: records every write request + frame and returns a plausible WriteResult."""

    def __init__(self) -> None:
        self.writes: list[tuple[object, pd.DataFrame]] = []

    def write(self, request, df):
        from emergentflow.data.warehouse.protocol import WriteResult

        self.writes.append((request, df.copy()))
        return WriteResult(
            table=request.table, mode=request.mode, rows_written=len(df), dialect=request.dialect
        )


def test_write_table_node_codegen_equivalence_with_recording_client(frame):
    from emergentflow.nodes.examples.write_table import WriteTable

    defn = WriteTable()
    node = defn.instantiate(table="mart.t1", connection="dw", dialect="duckdb", mode="truncate")
    executed_client = _RecordingWarehouseClient()
    executed = defn.execute(node, inputs={"frame": frame.copy()}, client=executed_client)["result"]
    codegen_client = _RecordingWarehouseClient()
    scope = {"frame": frame.copy(), "warehouse": codegen_client}
    exec(defn.preview(node).render(), scope)  # noqa: S102 - test-only on our own emitted code
    pd.testing.assert_frame_equal(executed, scope["result"])
    assert executed_client.writes[0][0] == codegen_client.writes[0][0]
    pd.testing.assert_frame_equal(executed_client.writes[0][1], codegen_client.writes[0][1])


def _raw_duckdb(duckdb_client) -> duckdb.DuckDBPyConnection:
    coords = duckdb_client._store.get("dw").coordinates
    return duckdb.connect(coords["path"], read_only=True)


def test_duckdb_truncate_refuses_missing_column_without_data_loss(duckdb_client, frame):
    """A truncate whose frame lacks a table column must refuse BEFORE deleting (issue #164
    follow-up): INSERT BY NAME would otherwise treat the missing column as NULL and destroy
    every existing row."""
    from emergentflow.data import DataError

    write_table(frame, table="t1", connection="dw", dialect="duckdb", client=duckdb_client)
    missing = frame.drop(columns=["b"])
    with pytest.raises(DataError, match="do not match"):
        write_table(
            missing,
            table="t1",
            connection="dw",
            dialect="duckdb",
            mode="truncate",
            client=duckdb_client,
        )
    out = _rows(duckdb_client, "SELECT * FROM t1")
    assert len(out) == 3 and list(out.columns) == ["a", "b"]


def test_duckdb_append_refuses_missing_column_without_null_pollution(duckdb_client, frame):
    """Append with a missing column likewise refuses instead of inserting NULL rows."""
    from emergentflow.data import DataError

    write_table(frame, table="t1", connection="dw", dialect="duckdb", client=duckdb_client)
    with pytest.raises(DataError, match="do not match"):
        write_table(
            frame.drop(columns=["a"]),
            table="t1",
            connection="dw",
            dialect="duckdb",
            mode="append",
            client=duckdb_client,
        )
    assert _rows(duckdb_client, "SELECT count(*) AS n FROM t1")["n"].iloc[0] == 3


def test_duckdb_empty_frame_create_keeps_types_and_appends(duckdb_client):
    """Writing an empty frame to a NEW table must not lock in junk column types."""
    write_table(
        pd.DataFrame(
            {
                "a": pd.Series([], dtype="int64"),
                "b": pd.Series([], dtype=str),
            }
        ),
        table="empty_t",
        connection="dw",
        dialect="duckdb",
        client=duckdb_client,
    )
    conn = _raw_duckdb(duckdb_client)
    cols = conn.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_name = 'empty_t' ORDER BY ordinal_position"
    ).fetchall()
    conn.close()
    assert cols[1][1] == "VARCHAR"
    write_table(
        pd.DataFrame({"a": [1], "b": ["x"]}),
        table="empty_t",
        connection="dw",
        dialect="duckdb",
        client=duckdb_client,
    )
    out = _rows(duckdb_client, "SELECT * FROM empty_t")
    assert out.to_dict("records") == [{"a": 1, "b": "x"}]


def test_duckdb_read_only_false_dml_via_execute(duckdb_client, frame):
    """A DML request sent with read_only=False runs on an open read-write connection.

    The profile's write_enabled gate already fires in the client's run(); once it passes,
    the adapter must not still open the file read-only (issue #164 follow-up), which would
    make the documented read_only=False path never able to run DML."""
    write_table(frame, table="t1", connection="dw", dialect="duckdb", client=duckdb_client)
    request = QueryRequest(
        sql="INSERT INTO t1 VALUES (4, 'w')",
        dialect="duckdb",
        connection="dw",
        read_only=False,
    )
    duckdb_client.run(request)
    assert _rows(duckdb_client, "SELECT count(*) AS n FROM t1")["n"].iloc[0] == 4


def test_write_table_node_uses_connection_ref_and_dialect_select():
    """The write_table node must declare its connection param as a ConnectionRef (profile
    picker) and its dialect as a select with the family's choices/default -- a free-text
    spec would strand the only effectful warehouse node outside the family's UI contract
    (issue #164 follow-up)."""
    from emergentflow.data.warehouse.params import (
        CONNECTION_REF_TOKEN,
        CONNECTION_WIDGET,
    )
    from emergentflow.nodes.examples.write_table import WriteTable

    defn = WriteTable()
    conn = next(p for p in defn.params if p.name == "connection")
    assert conn.type_token == CONNECTION_REF_TOKEN
    assert conn.hints.widget == CONNECTION_WIDGET
    dial = next(p for p in defn.params if p.name == "dialect")
    assert dial.default == "duckdb"
    assert dial.hints.widget == "select"
    assert dial.hints.choices == ["duckdb", "bigquery", "redshift", "postgres"]
