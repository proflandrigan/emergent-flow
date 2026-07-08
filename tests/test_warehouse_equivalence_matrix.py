"""
Epic 13 Story 9 — dialect × query-shape ADR-0002 equivalence matrix, computed
dynamically from ``known_connector_dialects()``.

Mirrors ``tests/test_ml_equivalence_matrix.py``'s "one matrix, not one test per
story" shape (Epic 8 Story 9 analog). Unlike that file, the execute/compile-code
comparison mechanism here is bespoke: exec the compiled module in-process and
call ``main(clients=...)`` directly, since ``Clients`` injection has no existing
shared harness.
"""

from __future__ import annotations

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from emergentflow.clients import Clients
from emergentflow.codegen.compiler import compile_to_code
from emergentflow.codegen.executor import execute
from emergentflow.data.warehouse.generator import known_connector_dialects
from emergentflow.data.warehouse.protocol import (
    ColumnSchema,
    CostEstimate,
    QueryRequest,
    QueryResult,
)
from emergentflow.data.warehouse.replay import (
    ReplayWarehouseClient,
    write_dry_run_fixture,
    write_fixture,
)
from emergentflow.data.warehouse.spec_compiler import compile_spec
from emergentflow.ir import Graph
from emergentflow.nodes.examples.query_builder import QueryBuilder
from emergentflow.nodes.examples.sql_query import SqlQuery


def _build_sql_query_graph(dialect: str, *, dry_run: bool = False) -> Graph:
    defn = SqlQuery()
    node = defn.instantiate(
        label="Sales Query",
        sql="SELECT id, region, revenue FROM sales WHERE revenue > 100",
        connection="test_duckdb",
        dialect=dialect,
        max_rows=None,
        dry_run=dry_run,
    )
    return Graph(
        name="sql_query_test",
        nodes={node.id: node},
        edges={},
    )


def _build_query_builder_graph(dialect: str, *, dry_run: bool = False) -> Graph:
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
        dialect=dialect,
        dry_run=dry_run,
    )
    return Graph(
        name="query_builder_test",
        nodes={node.id: node},
        edges={},
    )


def _make_sql_query_fixture(fixtures_dir, dialect: str) -> QueryResult:
    df = pd.DataFrame(
        {"id": [1, 2, 3], "region": ["east", "west", "east"], "revenue": [150.0, 200.0, 175.0]}
    )
    request = QueryRequest(
        sql="SELECT id, region, revenue FROM sales WHERE revenue > 100",
        dialect=dialect,
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
        dialect=dialect,
    )
    write_fixture(fixtures_dir, request, result)
    return result


def _make_query_builder_fixture(fixtures_dir, dialect: str) -> QueryResult:
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
    compiled_sql = compile_spec(spec, dialect)
    df = pd.DataFrame(
        {
            "region": ["east", "west"],
            "total": [500.0, 300.0],
        }
    )
    request = QueryRequest(
        sql=compiled_sql,
        dialect=dialect,
        connection="test_duckdb",
    )
    result = QueryResult(
        df=df,
        row_count=2,
        columns=(
            ColumnSchema(name="region", dtype="object"),
            ColumnSchema(name="total", dtype="float64"),
        ),
        dialect=dialect,
    )
    write_fixture(fixtures_dir, request, result)
    return result


@pytest.mark.equivalence
@pytest.mark.parametrize("dialect", known_connector_dialects())
def test_sql_query_equivalence_matrix(dialect: str, tmp_path) -> None:
    graph = _build_sql_query_graph(dialect)
    _make_sql_query_fixture(tmp_path, dialect)
    replay = ReplayWarehouseClient(tmp_path)

    exec_results = execute(graph, clients=Clients(warehouse=replay))
    node_id = list(graph.nodes.keys())[0]
    exec_frame = exec_results[node_id]["frame"]

    code = compile_to_code(graph)
    ns: dict = {}
    exec(code, ns)  # noqa: S102 -- test-only, on our own emitted code
    main_results = ns["main"](clients=Clients(warehouse=replay))
    code_frame = next(iter(main_results.values()))

    assert_frame_equal(exec_frame, code_frame)


@pytest.mark.equivalence
@pytest.mark.parametrize("dialect", known_connector_dialects())
def test_query_builder_equivalence_matrix(dialect: str, tmp_path) -> None:
    graph = _build_query_builder_graph(dialect)
    _make_query_builder_fixture(tmp_path, dialect)
    replay = ReplayWarehouseClient(tmp_path)

    exec_results = execute(graph, clients=Clients(warehouse=replay))
    node_id = list(graph.nodes.keys())[0]
    exec_frame = exec_results[node_id]["frame"]

    code = compile_to_code(graph)
    ns: dict = {}
    exec(code, ns)  # noqa: S102 -- test-only, on our own emitted code
    main_results = ns["main"](clients=Clients(warehouse=replay))
    code_frame = next(iter(main_results.values()))

    assert_frame_equal(exec_frame, code_frame)


# ---- dry_run: 'frame' must stay a genuine DataFrame; cost metadata goes out
# ---- its own 'cost_estimate' port instead of overloading 'frame' with two shapes.


def _make_sql_query_dry_run_fixture(fixtures_dir, dialect: str) -> CostEstimate:
    request = QueryRequest(
        sql="SELECT id, region, revenue FROM sales WHERE revenue > 100",
        dialect=dialect,
        connection="test_duckdb",
        dry_run=True,
    )
    estimate = CostEstimate(
        dialect=dialect, bytes_scanned=123456, estimated_rows=3, cost_usd=0.0012
    )
    write_dry_run_fixture(fixtures_dir, request, estimate)
    return estimate


def _make_query_builder_dry_run_fixture(fixtures_dir, dialect: str) -> CostEstimate:
    spec = {
        "source": "sales",
        "select": ["region", {"agg": "SUM", "column": "revenue", "alias": "total"}],
        "where": [{"column": "revenue", "op": ">", "value": 0}],
        "group_by": ["region"],
        "order_by": [{"column": "total", "desc": True}],
    }
    compiled_sql = compile_spec(spec, dialect)
    request = QueryRequest(
        sql=compiled_sql, dialect=dialect, connection="test_duckdb", dry_run=True
    )
    estimate = CostEstimate(
        dialect=dialect, bytes_scanned=654321, estimated_rows=2, cost_usd=0.0034
    )
    write_dry_run_fixture(fixtures_dir, request, estimate)
    return estimate


@pytest.mark.equivalence
@pytest.mark.parametrize("dialect", known_connector_dialects())
def test_sql_query_dry_run_equivalence_matrix(dialect: str, tmp_path) -> None:
    graph = _build_sql_query_graph(dialect, dry_run=True)
    _make_sql_query_dry_run_fixture(tmp_path, dialect)
    replay = ReplayWarehouseClient(tmp_path)

    exec_results = execute(graph, clients=Clients(warehouse=replay))
    node_id = list(graph.nodes.keys())[0]
    exec_frame = exec_results[node_id]["frame"]
    exec_cost = exec_results[node_id]["cost_estimate"]

    code = compile_to_code(graph)
    ns: dict = {}
    exec(code, ns)  # noqa: S102 -- test-only, on our own emitted code
    main_results = ns["main"](clients=Clients(warehouse=replay))
    code_frame, code_cost = main_results.values()

    # The port's declared type is "DataFrame" regardless of dry_run, so the value must
    # actually be one here too -- not the QueryResult wrapper the client returns.
    assert isinstance(exec_frame, pd.DataFrame)
    assert exec_frame.empty
    assert_frame_equal(exec_frame, code_frame)
    assert (
        exec_cost
        == code_cost
        == {
            "dialect": dialect,
            "bytes_scanned": 123456,
            "cost_usd": 0.0012,
        }
    )


@pytest.mark.equivalence
@pytest.mark.parametrize("dialect", known_connector_dialects())
def test_query_builder_dry_run_equivalence_matrix(dialect: str, tmp_path) -> None:
    graph = _build_query_builder_graph(dialect, dry_run=True)
    _make_query_builder_dry_run_fixture(tmp_path, dialect)
    replay = ReplayWarehouseClient(tmp_path)

    exec_results = execute(graph, clients=Clients(warehouse=replay))
    node_id = list(graph.nodes.keys())[0]
    exec_frame = exec_results[node_id]["frame"]
    exec_cost = exec_results[node_id]["cost_estimate"]

    code = compile_to_code(graph)
    ns: dict = {}
    exec(code, ns)  # noqa: S102 -- test-only, on our own emitted code
    main_results = ns["main"](clients=Clients(warehouse=replay))
    code_frame, code_cost = main_results.values()

    assert isinstance(exec_frame, pd.DataFrame)
    assert exec_frame.empty
    assert_frame_equal(exec_frame, code_frame)
    assert (
        exec_cost
        == code_cost
        == {
            "dialect": dialect,
            "bytes_scanned": 654321,
            "cost_usd": 0.0034,
        }
    )
