"""Tests for the ``data.query_builder`` node (Epic 13 Story 5).

Golden: the compiled code passes ``ast.parse`` and ``ruff check``.
Equivalence: ``execute(graph)`` matches the compile path under a replay client.
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
from emergentflow.data.warehouse.protocol import (
    ColumnSchema,
    QueryRequest,
    QueryResult,
)
from emergentflow.data.warehouse.replay import (
    ReplayWarehouseClient,
    write_fixture,
)
from emergentflow.data.warehouse.spec_compiler import compile_spec
from emergentflow.ir import Graph
from emergentflow.nodes.examples.query_builder import QueryBuilder


def _build_query_builder_graph() -> Graph:
    defn = QueryBuilder()
    node = defn.instantiate(
        label="Sales by Region",
        source="sales",
        select=[
            "region",
            {"agg": "SUM", "column": "revenue", "alias": "total"},
        ],
        where=[{"column": "revenue", "op": ">", "value": 0}],
        group_by=["region"],
        order_by=[{"column": "total", "desc": True}],
        connection="test_duckdb",
        dialect="duckdb",
    )
    return Graph(
        name="query_builder_test",
        nodes={node.id: node},
        edges={},
    )


def _make_fixture(fixtures_dir, graph: Graph):
    spec = {
        "source": "sales",
        "select": [
            "region",
            {"agg": "SUM", "column": "revenue", "alias": "total"},
        ],
        "where": [{"column": "revenue", "op": ">", "value": 0}],
        "group_by": ["region"],
        "order_by": [{"column": "total", "desc": True}],
    }
    compiled_sql = compile_spec(spec, "duckdb")
    df = pd.DataFrame(
        {
            "region": ["east", "west"],
            "total": [500.0, 300.0],
        }
    )
    request = QueryRequest(
        sql=compiled_sql,
        dialect="duckdb",
        connection="test_duckdb",
    )
    result = QueryResult(
        df=df,
        row_count=2,
        columns=(
            ColumnSchema(name="region", dtype="object"),
            ColumnSchema(name="total", dtype="float64"),
        ),
        dialect="duckdb",
    )
    write_fixture(fixtures_dir, request, result)
    return result


def test_query_builder_golden_ast_parse() -> None:
    graph = _build_query_builder_graph()
    code = compile_to_code(graph)
    ast.parse(code)


def test_query_builder_golden_ruff_check() -> None:
    graph = _build_query_builder_graph()
    code = compile_to_code(graph)
    proc = subprocess.run(
        [
            sys.executable, "-m", "ruff", "check",
            "--stdin-filename", "generated.py", "-",
        ],
        input=code,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        f"ruff check failed:\n{proc.stdout}\n{proc.stderr}"
    )


def test_query_builder_compiled_uses_spec() -> None:
    graph = _build_query_builder_graph()
    code = compile_to_code(graph)
    assert "spec=" in code
    assert "client=warehouse" in code


def test_query_builder_equivalence(tmp_path) -> None:
    graph = _build_query_builder_graph()
    expected = _make_fixture(tmp_path, graph)
    replay = ReplayWarehouseClient(tmp_path)

    exec_results = execute(
        graph, clients=Clients(warehouse=replay)
    )
    node_id = list(graph.nodes.keys())[0]
    exec_qr = exec_results[node_id]["frame"]

    assert_frame_equal(exec_qr.df, expected.df)
    assert exec_qr.row_count == expected.row_count
