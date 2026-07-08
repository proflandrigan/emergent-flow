"""Epic 13 Story 10 — proves the full canvas round trip (/compile → ruff-clean .py,
/execute → per-node "ok" status) for a sql_query-terminal graph and a
query_builder → DataFrame edge feeding an Epic 12 node, through the real server
app (not execute()/compile_to_code() called directly).
"""

from __future__ import annotations

import ast
import subprocess
import sys

import duckdb
import pytest
from fastapi.testclient import TestClient

from emergentflow.ir import Edge, Graph, PortRef
from emergentflow.nodes.examples.describe import Describe
from emergentflow.nodes.examples.query_builder import QueryBuilder
from emergentflow.nodes.examples.sql_query import SqlQuery
from emergentflow.server import app, service


@pytest.fixture(scope="module")
def _shared_db_path(tmp_path_factory):
    """Create a shared DuckDB database with a real sales table for all tests.

    Both test profiles in every test's connections.toml point *test_duckdb_file*
    at this same path, so whichever test initialises the
    ``_get_warehouse_client()`` singleton first caches a store whose
    ``test_duckdb_file`` entry is valid for every test in this module.
    """
    path = tmp_path_factory.mktemp("warehouse_data") / "sales.duckdb"
    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE sales (region VARCHAR, revenue DOUBLE)")
    con.execute("INSERT INTO sales VALUES ('east', 100.0), ('east', 50.0), ('west', 200.0)")
    con.close()
    return path


def _find_port(node, name):
    for p in node.ports:
        if p.name == name:
            return p
    raise ValueError(f"Port {name!r} not found on node {node.id!r}")


def _write_connections_toml(connections_toml, *, db_path):
    """Write a connections.toml with both profiles needed by this module's tests."""
    connections_toml.write_text(
        "[test_duckdb]\n"
        'dialect = "duckdb"\n'
        "\n"
        "[test_duckdb_file]\n"
        'dialect = "duckdb"\n'
        "\n"
        "[test_duckdb_file.credential_refs]\n"
        f'path = "{db_path}"\n'
    )


def _ruff_check(code: str) -> None:
    """Assert that *code* passes ruff check (importable, clean)."""
    proc = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--stdin-filename", "generated.py", "-"],
        input=code,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"ruff check failed:\n{proc.stdout}\n{proc.stderr}"


class TestSqlQueryTerminal:
    """A data.sql_query-terminal graph (one node, no downstream)."""

    def test_roundtrip(self, tmp_path, monkeypatch, _shared_db_path) -> None:
        _write_connections_toml(tmp_path / "connections.toml", db_path=_shared_db_path)
        monkeypatch.setenv("EMERGENTFLOW_CONNECTIONS", str(tmp_path / "connections.toml"))
        monkeypatch.setattr(service, "_warehouse_client_singleton", None)

        defn = SqlQuery()
        node = defn.instantiate(
            sql="SELECT 1 AS x",
            connection="test_duckdb",
            dialect="duckdb",
            max_rows=None,
            dry_run=False,
        )
        graph = Graph(
            name="sql_query_roundtrip_test",
            nodes={node.id: node},
            edges={},
        )
        graph_dict = graph.model_dump(mode="json")

        with TestClient(app) as test_client:
            resp = test_client.post("/compile", json=graph_dict)
            assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
            body = resp.json()
            code = body["code"]
            ast.parse(code)
            _ruff_check(code)

            resp = test_client.post("/execute", json=graph_dict)
            assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
            data = resp.json()
            statuses = data.get("statuses", {})
            node_status = statuses.get(node.id, {})
            assert node_status.get("status") == "ok", (
                f"Expected status 'ok', got {node_status!r}. Response: {data}"
            )
            results = data.get("results", {})
            node_results = results.get(node.id, {})
            frame = node_results.get("frame", {})
            assert frame.get("kind") == "table", f"Expected kind 'table', got {frame!r}"


class TestQueryBuilderToDescribe:
    """A data.query_builder → stats.describe graph (two nodes, wired edge)."""

    def test_roundtrip(self, tmp_path, monkeypatch, _shared_db_path) -> None:
        _write_connections_toml(tmp_path / "connections.toml", db_path=_shared_db_path)
        monkeypatch.setenv("EMERGENTFLOW_CONNECTIONS", str(tmp_path / "connections.toml"))
        monkeypatch.setattr(service, "_warehouse_client_singleton", None)

        qb_defn = QueryBuilder()
        qb_node = qb_defn.instantiate(
            label="Sales by Region",
            source="sales",
            select=[
                "region",
                {"agg": "SUM", "column": "revenue", "alias": "total"},
            ],
            group_by=["region"],
            connection="test_duckdb_file",
            dialect="duckdb",
        )

        describe_defn = Describe()
        describe_node = describe_defn.instantiate(columns=None)

        qb_frame = _find_port(qb_node, "frame")
        describe_frame = _find_port(describe_node, "frame")
        edge = Edge(
            source=PortRef(node_id=qb_node.id, port_id=qb_frame.id),
            target=PortRef(node_id=describe_node.id, port_id=describe_frame.id),
        )
        graph = Graph(
            name="query_builder_to_describe_test",
            nodes={
                qb_node.id: qb_node,
                describe_node.id: describe_node,
            },
            edges={edge.id: edge},
        )
        graph_dict = graph.model_dump(mode="json")

        with TestClient(app) as test_client:
            resp = test_client.post("/compile", json=graph_dict)
            assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
            body = resp.json()
            code = body["code"]
            ast.parse(code)
            _ruff_check(code)

            resp = test_client.post("/execute", json=graph_dict)
            assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
            data = resp.json()
            statuses = data.get("statuses", {})
            for node_id in (qb_node.id, describe_node.id):
                node_status = statuses.get(node_id, {})
                assert node_status.get("status") == "ok", (
                    f"Node {node_id!r} expected 'ok', got {node_status!r}. Response: {data}"
                )

            results = data.get("results", {})
            qb_results = results.get(qb_node.id, {})
            frame = qb_results.get("frame", {})
            assert frame.get("kind") == "table", f"Expected qb frame kind 'table', got {frame!r}"

            describe_results = results.get(describe_node.id, {})
            summary = describe_results.get("summary", {})
            assert summary.get("kind") == "table", (
                f"Expected describe summary kind 'table', got {summary!r}"
            )
            head = summary.get("head", [])
            assert len(head) > 0, (
                f"Expected at least one row in describe summary head, got empty: {summary!r}"
            )
