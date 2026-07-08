"""
tests/test_data_connectors_acceptance_demo.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Epic 13 Story 11 — builds the exploration acceptance-demo IR graph
(``sql_query -> describe`` / ``correlation -> heatmap``), writes it to
``examples/data_connectors_acceptance_demo/``, regenerates the bundled parquet
fixture, re-loads and validates the graph, and proves ADR-0002 equivalence under
a ``ReplayWarehouseClient`` (custom harness — ``assert_equivalent`` doesn't
support the ``Clients`` bundle; see ``tests/test_warehouse_equivalence_matrix.py``
for the same bespoke in-process exec pattern).
"""

from __future__ import annotations

import ast
import pathlib
import subprocess
import sys

import duckdb
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from emergentflow.clients import Clients
from emergentflow.codegen.compiler import _assemble, compile_to_code
from emergentflow.codegen.executor import execute
from emergentflow.data.warehouse.protocol import ColumnSchema, QueryRequest, QueryResult
from emergentflow.data.warehouse.replay import ReplayWarehouseClient, write_fixture
from emergentflow.ir import (
    Direction,
    Edge,
    Graph,
    Node,
    Paradigm,
    Param,
    Port,
    PortRef,
    Position,
)

REPO_ROOT = pathlib.Path(__file__).parent.parent
EXAMPLES_DIR = REPO_ROOT / "examples"
DEMO_DIR = EXAMPLES_DIR / "data_connectors_acceptance_demo"


# ---------------------------------------------------------------------------
# Fixture helpers: write parquet and JSON
# ---------------------------------------------------------------------------


def write_parquet_fixture(path: pathlib.Path) -> None:
    """(Re)generate the bundled parquet fixture — small, deterministic sales data."""
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(":memory:")
    con.execute(
        """
        CREATE TABLE sales AS
        SELECT * FROM (VALUES
            (1, 'east', 120.0, 15),
            (2, 'east', 95.0, 11),
            (3, 'east', 210.0, 22),
            (4, 'west', 60.0, 7),
            (5, 'west', 175.0, 19),
            (6, 'west', 140.0, 14),
            (7, 'north', 88.0, 9),
            (8, 'north', 132.0, 16),
            (9, 'south', 205.0, 21),
            (10, 'south', 77.0, 8)
        ) AS t(id, region, revenue, units)
        """
    )
    con.execute(f"COPY sales TO '{path}' (FORMAT PARQUET)")
    con.close()


def write_pipeline(graph: Graph, filename: str) -> pathlib.Path:
    """Dump *graph* as pretty JSON to examples/data_connectors_acceptance_demo/<filename>."""
    DEMO_DIR.mkdir(exist_ok=True)
    path = DEMO_DIR / filename
    path.write_text(graph.model_dump_json(indent=2), encoding="utf-8")
    return path


def build_exploration_demo() -> Graph:
    """A raw sql_query feeds a describe summary and a correlation heatmap."""
    node_query = Node(
        id="n-query",
        type="data.sql_query",
        label="Sales Query",
        paradigm=Paradigm.FUNCTIONAL,
        params=[
            Param(
                name="sql",
                type_token="str",
                value=(
                    "SELECT * FROM read_parquet("
                    "'examples/data_connectors_acceptance_demo/sales.parquet')"
                ),
            ),
            Param(name="connection", type_token="ConnectionRef", value="demo_duckdb"),
            Param(name="dialect", type_token="str", value="duckdb"),
            Param(name="max_rows", type_token="int", value=None),
            Param(name="dry_run", type_token="bool", value=False),
        ],
        ports=[
            Port(id="p-query-frame", name="frame", direction=Direction.OUT, data_type="DataFrame"),
        ],
        position=Position(x=0.0, y=0.0),
    )

    node_describe = Node(
        id="n-describe",
        type="stats.describe",
        label="Describe",
        paradigm=Paradigm.FUNCTIONAL,
        params=[],
        ports=[
            Port(id="p-describe-in", name="frame", direction=Direction.IN, data_type="DataFrame"),
            Port(
                id="p-describe-summary",
                name="summary",
                direction=Direction.OUT,
                data_type="DataFrame",
            ),
        ],
        position=Position(x=200.0, y=-100.0),
    )

    node_corr = Node(
        id="n-corr",
        type="stats.correlation",
        label="Correlation",
        paradigm=Paradigm.FUNCTIONAL,
        params=[],
        ports=[
            Port(id="p-corr-in", name="frame", direction=Direction.IN, data_type="DataFrame"),
            Port(id="p-corr-matrix", name="matrix", direction=Direction.OUT, data_type="DataFrame"),
        ],
        position=Position(x=200.0, y=100.0),
    )

    node_heatmap = Node(
        id="n-heatmap",
        type="viz.plot_correlation_heatmap",
        label="Correlation Heatmap",
        paradigm=Paradigm.FUNCTIONAL,
        params=[],
        ports=[
            Port(id="p-heatmap-in", name="matrix", direction=Direction.IN, data_type="DataFrame"),
            Port(id="p-heatmap-plot", name="plot", direction=Direction.OUT, data_type="PlotSpec"),
        ],
        position=Position(x=400.0, y=100.0),
    )

    edge_query_describe = Edge(
        id="e-query-describe",
        source=PortRef(node_id="n-query", port_id="p-query-frame"),
        target=PortRef(node_id="n-describe", port_id="p-describe-in"),
    )
    edge_query_corr = Edge(
        id="e-query-corr",
        source=PortRef(node_id="n-query", port_id="p-query-frame"),
        target=PortRef(node_id="n-corr", port_id="p-corr-in"),
    )
    edge_corr_heatmap = Edge(
        id="e-corr-heatmap",
        source=PortRef(node_id="n-corr", port_id="p-corr-matrix"),
        target=PortRef(node_id="n-heatmap", port_id="p-heatmap-in"),
    )

    return Graph(
        paradigm=Paradigm.FUNCTIONAL,
        name="Data Connectors Acceptance Demo -- Exploration",
        nodes={n.id: n for n in (node_query, node_describe, node_corr, node_heatmap)},
        edges={e.id: e for e in (edge_query_describe, edge_query_corr, edge_corr_heatmap)},
    )


def _make_query_fixture(fixtures_dir: pathlib.Path) -> QueryResult:
    """Create a replay fixture for the exploration demo's sql_query node."""
    df = pd.DataFrame(
        {
            "id": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
            "region": [
                "east",
                "east",
                "east",
                "west",
                "west",
                "west",
                "north",
                "north",
                "south",
                "south",
            ],
            "revenue": [120.0, 95.0, 210.0, 60.0, 175.0, 140.0, 88.0, 132.0, 205.0, 77.0],
            "units": [15, 11, 22, 7, 19, 14, 9, 16, 21, 8],
        }
    )
    request = QueryRequest(
        sql="SELECT * FROM read_parquet('examples/data_connectors_acceptance_demo/sales.parquet')",
        dialect="duckdb",
        connection="demo_duckdb",
        params=(),
        max_rows=None,
        byte_scan_cap=None,
        read_only=True,
        dry_run=False,
    )
    result = QueryResult(
        df=df,
        row_count=10,
        columns=(
            ColumnSchema(name="id", dtype="int64"),
            ColumnSchema(name="region", dtype="object"),
            ColumnSchema(name="revenue", dtype="float64"),
            ColumnSchema(name="units", dtype="int64"),
        ),
        dialect="duckdb",
    )
    write_fixture(fixtures_dir, request, result)
    return result


# ---------------------------------------------------------------------------
# Drift guard: committed JSON must match what the builder generates
# ---------------------------------------------------------------------------


def test_committed_exploration_json_is_current() -> None:
    committed = Graph.model_validate_json(
        (DEMO_DIR / "exploration_pipeline.json").read_text(encoding="utf-8")
    )
    assert committed == build_exploration_demo(), (
        "examples/data_connectors_acceptance_demo/exploration_pipeline.json is stale; run "
        "'pytest tests/test_data_connectors_acceptance_demo.py::TestExplorationDemo' "
        "to regenerate it"
    )


# ---------------------------------------------------------------------------
# Tests: exploration demo
# ---------------------------------------------------------------------------


class TestExplorationDemo:
    @pytest.fixture(autouse=True)
    def write_json(self) -> None:
        write_pipeline(build_exploration_demo(), "exploration_pipeline.json")
        write_parquet_fixture(DEMO_DIR / "sales.parquet")

    def test_loads_and_validates(self) -> None:
        raw = (DEMO_DIR / "exploration_pipeline.json").read_text(encoding="utf-8")
        Graph.model_validate_json(raw)

    def test_node_and_edge_counts(self) -> None:
        graph = build_exploration_demo()
        assert len(graph.nodes) == 4
        assert len(graph.edges) == 3

    def test_node_types(self) -> None:
        graph = build_exploration_demo()
        node_types = {node.type for node in graph.nodes.values()}
        assert node_types == {
            "data.sql_query",
            "stats.describe",
            "stats.correlation",
            "viz.plot_correlation_heatmap",
        }

    def test_golden_ast_parse(self) -> None:
        code = compile_to_code(build_exploration_demo())
        ast.parse(code)

    def test_golden_ruff_check(self) -> None:
        code = compile_to_code(build_exploration_demo())
        proc = subprocess.run(
            [sys.executable, "-m", "ruff", "check", "--stdin-filename", "generated.py", "-"],
            input=code,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, f"ruff check failed:\n{proc.stdout}\n{proc.stderr}"

    @pytest.mark.equivalence
    def test_equivalence(self, tmp_path: pathlib.Path) -> None:
        """ADR-0002: execute() == running the emitted code for the exploration demo,
        using a ReplayWarehouseClient (custom harness — assert_equivalent doesn't
        support the Clients bundle)."""
        graph = build_exploration_demo()
        _make_query_fixture(tmp_path)
        replay = ReplayWarehouseClient(tmp_path)
        clients = Clients(warehouse=replay)

        exec_results = execute(graph, clients=clients)

        code = compile_to_code(graph)
        ns: dict = {}
        exec(code, ns)  # noqa: S102 -- test-only, on our own emitted code
        main_results = ns["main"](clients=clients)

        out_ports = _assemble(graph).out_ports
        describe_var = next(
            var for nid, pname, var in out_ports if nid == "n-describe" and pname == "summary"
        )
        heatmap_var = next(
            var for nid, pname, var in out_ports if nid == "n-heatmap" and pname == "plot"
        )

        assert_frame_equal(exec_results["n-describe"]["summary"], main_results[describe_var])
        assert exec_results["n-heatmap"]["plot"] == main_results[heatmap_var]
