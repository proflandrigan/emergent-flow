"""Tests for warehouse-node execution through the server (Epic 13 Story 10).

Verifies that _execute_node's hardcoded warehouse=None was replaced with a real
AdapterWarehouseClient so data.sql_query nodes run against a real DuckDB adapter
through /execute_node instead of crashing on a None client.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from emergentflow.ir import Graph
from emergentflow.nodes.examples.sql_query import SqlQuery
from emergentflow.server import app


def test_execute_node_sql_query_against_duckdb(tmp_path, monkeypatch) -> None:
    """data.sql_query run via /execute_node reaches a real DuckDB adapter, not None."""
    # Write a minimal connection profile for DuckDB.
    connections_toml = tmp_path / "connections.toml"
    connections_toml.write_text('[test_duckdb]\ndialect = "duckdb"\n')
    monkeypatch.setenv("EMERGENTFLOW_CONNECTIONS", str(connections_toml))

    defn = SqlQuery()
    node = defn.instantiate(
        label="Test Query",
        sql="SELECT 1 AS x",
        connection="test_duckdb",
        dialect="duckdb",
        max_rows=None,
        dry_run=False,
    )
    graph = Graph(
        name="sql_query_execute_test",
        nodes={node.id: node},
        edges={},
    )
    graph_dict = graph.model_dump(mode="json")

    with TestClient(app) as test_client:
        resp = test_client.post(
            "/execute_node",
            json={"graph": graph_dict, "run_node": node.id, "inputs": {}},
        )

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    statuses = data.get("statuses", {})
    node_status = statuses.get(node.id, {})
    assert node_status.get("status") == "ok", (
        f"Expected status 'ok', got {node_status!r}. Response: {data}"
    )
