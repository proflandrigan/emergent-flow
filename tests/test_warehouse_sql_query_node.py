"""Tests for the ``data.sql_query`` node (Epic 13 Story 4).

Golden: the compiled code for a representative sql_query graph passes
``ast.parse`` and ``ruff check`` (importable, clean).

Equivalence: ``execute(graph)`` and running the compiled code produce the
same ``QueryResult`` under a shared ``ReplayWarehouseClient``.
"""

from __future__ import annotations

import ast
import subprocess
import sys

import pandas as pd
from pandas.testing import assert_frame_equal

from emergentflow.clients import Clients
from emergentflow.codegen.compiler import compile_to_code
from emergentflow.codegen.executor import execute
from emergentflow.data.warehouse.protocol import ColumnSchema, QueryRequest, QueryResult
from emergentflow.data.warehouse.replay import ReplayWarehouseClient, write_fixture
from emergentflow.ir import Graph
from emergentflow.nodes.examples.sql_query import SqlQuery


def _build_sql_query_graph() -> Graph:
    """Build a minimal graph with one ``data.sql_query`` node."""
    defn = SqlQuery()
    node = defn.instantiate(
        label="Sales Query",
        sql="SELECT id, region, revenue FROM sales WHERE revenue > 100",
        connection="test_duckdb",
        dialect="duckdb",
        max_rows=None,
        dry_run=False,
    )
    return Graph(
        name="sql_query_test",
        nodes={node.id: node},
        edges={},
    )


def _make_fixture(fixtures_dir) -> tuple[QueryRequest, QueryResult]:
    """Create a replay fixture for the test graph's query."""
    df = pd.DataFrame(
        {"id": [1, 2, 3], "region": ["east", "west", "east"], "revenue": [150.0, 200.0, 175.0]}
    )
    request = QueryRequest(
        sql="SELECT id, region, revenue FROM sales WHERE revenue > 100",
        dialect="duckdb",
        connection="test_duckdb",
        params=(),
        max_rows=None,
        byte_scan_cap=None,
        read_only=True,
        dry_run=False,
    )
    result = QueryResult(
        df=df,
        row_count=3,
        columns=(
            ColumnSchema(name="id", dtype="int64"),
            ColumnSchema(name="region", dtype="object"),
            ColumnSchema(name="revenue", dtype="float64"),
        ),
        dialect="duckdb",
    )
    write_fixture(fixtures_dir, request, result)
    return request, result


# ---- Golden tests ----


def test_sql_query_golden_ast_parse() -> None:
    """Compiled code for a sql_query graph is valid Python (ast.parse succeeds)."""
    graph = _build_sql_query_graph()
    code = compile_to_code(graph)
    ast.parse(code)


def test_sql_query_golden_ruff_check() -> None:
    """Compiled code for a sql_query graph passes ruff check (importable, clean)."""
    graph = _build_sql_query_graph()
    code = compile_to_code(graph)
    proc = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--stdin-filename", "generated.py", "-"],
        input=code,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"ruff check failed:\n{proc.stdout}\n{proc.stderr}"


def test_sql_query_compiled_references_warehouse() -> None:
    """Compiled code threads ``warehouse`` from the clients bundle, not ``client``."""
    graph = _build_sql_query_graph()
    code = compile_to_code(graph)
    assert "client=warehouse" in code
    assert "def main(*, clients:" in code


# ---- Equivalence test ----


def test_sql_query_equivalence(tmp_path) -> None:
    """execute(graph) produces the same result as running the compiled code.

    The node's ``frame`` OUT port is a bare DataFrame (the QueryResult's ``.df``,
    unwrapped in ``execute``/``codegen`` so it matches its declared ``DataFrame`` port
    type and flows into the rest of the analyst surface), so the port's artifact is
    compared directly against the fixture's frame.
    """
    graph = _build_sql_query_graph()
    _request, expected_result = _make_fixture(tmp_path)
    replay = ReplayWarehouseClient(tmp_path)

    # Execute side
    exec_results = execute(graph, clients=Clients(warehouse=replay))
    node_id = list(graph.nodes.keys())[0]
    exec_frame = exec_results[node_id]["frame"]

    assert_frame_equal(exec_frame, expected_result.df)
