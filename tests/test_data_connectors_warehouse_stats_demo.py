"""
tests/test_data_connectors_warehouse_stats_demo.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Epic 13 Story 11 — builds the warehouse→stats acceptance-demo IR graph
(``data.query_builder`` (join + group-by, BigQuery dialect) → ``stats.fit_model``
(MixedLM, random intercept by region) → ``viz.plot_coefficients`` (coefficient/forest
plot)), writes it to ``examples/data_connectors_acceptance_demo/``, re-loads and
validates the graph, and proves ADR-0002 equivalence under a ``ReplayWarehouseClient``
(custom harness — ``assert_equivalent`` doesn't support the ``Clients`` bundle; see
``tests/test_warehouse_equivalence_matrix.py`` for the same bespoke in-process exec
pattern).
"""

from __future__ import annotations

import ast
import pathlib
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from emergentflow.clients import Clients
from emergentflow.codegen.compiler import _assemble, compile_to_code
from emergentflow.codegen.executor import execute
from emergentflow.data.warehouse.protocol import ColumnSchema, QueryRequest, QueryResult
from emergentflow.data.warehouse.replay import ReplayWarehouseClient, write_fixture
from emergentflow.data.warehouse.spec_compiler import compile_spec
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
# The structured spec both the node's params and the replay fixture use.
# Must match what QueryBuilder._build_spec assembles from the node's params
# (same keys, same values) so the compiled SQL from compile_spec matches the
# SQL the node generates internally.
# ---------------------------------------------------------------------------

QB_SPEC: dict = {
    "source": "sales",
    "select": [
        "sales.region",
        "sales.rep_id",
        {"agg": "SUM", "column": "sales.revenue", "alias": "total_revenue"},
        {"agg": "AVG", "column": "regions.market_index", "alias": "avg_market_index"},
    ],
    "join": [
        {
            "relation": "regions",
            "on": [{"left": "sales.region", "right": "regions.region"}],
            "type": "INNER",
        }
    ],
    "group_by": ["sales.region", "sales.rep_id"],
}


# ---------------------------------------------------------------------------
# Fixture helpers: write JSON and build synthetic data
# ---------------------------------------------------------------------------


def write_pipeline(graph: Graph, filename: str) -> pathlib.Path:
    """Dump *graph* as pretty JSON to examples/data_connectors_acceptance_demo/<filename>."""
    DEMO_DIR.mkdir(exist_ok=True)
    path = DEMO_DIR / filename
    path.write_text(graph.model_dump_json(indent=2), encoding="utf-8")
    return path


def build_warehouse_stats_demo() -> Graph:
    """query_builder (join + group-by, BigQuery dialect) -> MixedLM (random intercept by
    region) -> coefficient/forest plot."""
    node_query = Node(
        id="n-query",
        type="data.query_builder",
        label="Sales by Rep + Region",
        paradigm=Paradigm.FUNCTIONAL,
        params=[
            Param(name="source", type_token="str", value="sales"),
            Param(
                name="select",
                type_token="list",
                value=[
                    "sales.region",
                    "sales.rep_id",
                    {"agg": "SUM", "column": "sales.revenue", "alias": "total_revenue"},
                    {"agg": "AVG", "column": "regions.market_index", "alias": "avg_market_index"},
                ],
            ),
            Param(name="where", type_token="list", value=[]),
            Param(
                name="join",
                type_token="list",
                value=[
                    {
                        "relation": "regions",
                        "on": [{"left": "sales.region", "right": "regions.region"}],
                        "type": "INNER",
                    }
                ],
            ),
            Param(name="group_by", type_token="list", value=["sales.region", "sales.rep_id"]),
            Param(name="having", type_token="list", value=[]),
            Param(name="order_by", type_token="list", value=[]),
            Param(name="limit", type_token="int", value=None),
            Param(name="distinct", type_token="bool", value=False),
            Param(name="connection", type_token="ConnectionRef", value="demo_bigquery"),
            Param(name="dialect", type_token="str", value="bigquery"),
            Param(name="max_rows", type_token="int", value=None),
            Param(name="dry_run", type_token="bool", value=False),
        ],
        ports=[
            Port(id="p-query-frame", name="frame", direction=Direction.OUT, data_type="DataFrame"),
            Port(
                id="p-query-cost",
                name="cost_estimate",
                direction=Direction.OUT,
                data_type="CostEstimate",
            ),
        ],
        position=Position(x=0.0, y=0.0),
    )

    node_mixed = Node(
        id="n-mixed",
        type="stats.fit_model",
        label="Mixed-Effects Model",
        paradigm=Paradigm.FUNCTIONAL,
        params=[
            Param(name="model", type_token="str", value="MixedLM"),
            Param(name="target", type_token="str", value="total_revenue"),
            Param(name="fixed_effects", type_token="list[str]", value=["avg_market_index"]),
            Param(name="random_effects", type_token="list[str]", value=[]),
            Param(name="groups", type_token="str", value="region"),
        ],
        ports=[
            Port(id="p-mixed-in", name="frame", direction=Direction.IN, data_type="DataFrame"),
            Port(id="p-mixed-model", name="model", direction=Direction.OUT, data_type="StatsModel"),
        ],
        position=Position(x=250.0, y=0.0),
    )

    node_forest = Node(
        id="n-forest",
        type="viz.plot_coefficients",
        label="Plot Coefficients",
        paradigm=Paradigm.FUNCTIONAL,
        params=[],
        ports=[
            Port(id="p-forest-model", name="model", direction=Direction.IN, data_type="StatsModel"),
            Port(id="p-forest-plot", name="plot", direction=Direction.OUT, data_type="PlotSpec"),
        ],
        position=Position(x=500.0, y=0.0),
    )

    edge_query_mixed = Edge(
        id="e-query-mixed",
        source=PortRef(node_id="n-query", port_id="p-query-frame"),
        target=PortRef(node_id="n-mixed", port_id="p-mixed-in"),
    )
    edge_mixed_forest = Edge(
        id="e-mixed-forest",
        source=PortRef(node_id="n-mixed", port_id="p-mixed-model"),
        target=PortRef(node_id="n-forest", port_id="p-forest-model"),
    )

    return Graph(
        paradigm=Paradigm.FUNCTIONAL,
        name="Data Connectors Acceptance Demo -- Warehouse to Stats",
        nodes={n.id: n for n in (node_query, node_mixed, node_forest)},
        edges={e.id: e for e in (edge_query_mixed, edge_mixed_forest)},
    )


def _build_query_result_frame(seed: int = 0) -> pd.DataFrame:
    """A well-separated, fixed-seed grouped fixture: 6 regions x 10 reps,
    so a random-intercept-only MixedLM converges deterministically (mirrors
    _grouped_df from test_stats_mixedlm_catalog.py)."""
    rng = np.random.default_rng(seed)
    rows = []
    regions = ["north", "south", "east", "west", "central", "coastal"]
    for g, region in enumerate(regions):
        intercept = g * 4.0
        slope = 2.0 + rng.normal(scale=1.0)
        for rep_id in range(1, 11):
            market_index = rng.normal()
            revenue = intercept + slope * market_index + rng.normal(scale=0.5)
            rows.append(
                {
                    "region": region,
                    "rep_id": rep_id,
                    "total_revenue": revenue,
                    "avg_market_index": market_index,
                }
            )
    return pd.DataFrame(rows)


def _make_query_fixture(fixtures_dir: pathlib.Path) -> QueryResult:
    """Create a replay fixture for the warehouse-stats demo's query_builder node.
    Uses the same QB_SPEC dict the node's params encode, compiled via compile_spec,
    so the fixture SQL matches exactly what the node's _build_spec produces."""
    compiled_sql = compile_spec(QB_SPEC, "bigquery")
    df = _build_query_result_frame()
    request = QueryRequest(
        sql=compiled_sql,
        dialect="bigquery",
        connection="demo_bigquery",
    )
    result = QueryResult(
        df=df,
        row_count=60,
        columns=(
            ColumnSchema(name="region", dtype="object"),
            ColumnSchema(name="rep_id", dtype="int64"),
            ColumnSchema(name="total_revenue", dtype="float64"),
            ColumnSchema(name="avg_market_index", dtype="float64"),
        ),
        dialect="bigquery",
    )
    write_fixture(fixtures_dir, request, result)
    return result


# ---------------------------------------------------------------------------
# Drift guard: committed JSON must match what the builder generates
# ---------------------------------------------------------------------------


def test_committed_warehouse_stats_json_is_current() -> None:
    committed = Graph.model_validate_json(
        (DEMO_DIR / "warehouse_stats_pipeline.json").read_text(encoding="utf-8")
    )
    assert committed == build_warehouse_stats_demo(), (
        "examples/data_connectors_acceptance_demo/warehouse_stats_pipeline.json is stale; run "
        "'pytest tests/test_data_connectors_warehouse_stats_demo.py::TestWarehouseStatsDemo' "
        "to regenerate it"
    )


# ---------------------------------------------------------------------------
# Tests: warehouse -> stats demo
# ---------------------------------------------------------------------------


class TestWarehouseStatsDemo:
    @pytest.fixture(autouse=True)
    def write_json(self) -> None:
        write_pipeline(build_warehouse_stats_demo(), "warehouse_stats_pipeline.json")

    def test_loads_and_validates(self) -> None:
        raw = (DEMO_DIR / "warehouse_stats_pipeline.json").read_text(encoding="utf-8")
        Graph.model_validate_json(raw)

    def test_node_and_edge_counts(self) -> None:
        graph = build_warehouse_stats_demo()
        assert len(graph.nodes) == 3
        assert len(graph.edges) == 2

    def test_node_types(self) -> None:
        graph = build_warehouse_stats_demo()
        node_types = {node.type for node in graph.nodes.values()}
        assert node_types == {
            "data.query_builder",
            "stats.fit_model",
            "viz.plot_coefficients",
        }

    def test_golden_ast_parse(self) -> None:
        code = compile_to_code(build_warehouse_stats_demo())
        ast.parse(code)

    def test_golden_ruff_check(self) -> None:
        code = compile_to_code(build_warehouse_stats_demo())
        proc = subprocess.run(
            [sys.executable, "-m", "ruff", "check", "--stdin-filename", "generated.py", "-"],
            input=code,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, f"ruff check failed:\n{proc.stdout}\n{proc.stderr}"

    @pytest.mark.equivalence
    def test_equivalence(self, tmp_path: pathlib.Path) -> None:
        """ADR-0002: execute() == running the emitted code for the warehouse->stats demo,
        using a ReplayWarehouseClient (custom harness -- assert_equivalent doesn't
        support the Clients bundle)."""
        graph = build_warehouse_stats_demo()
        _make_query_fixture(tmp_path)
        replay = ReplayWarehouseClient(tmp_path)
        clients = Clients(warehouse=replay)

        exec_results = execute(graph, clients=clients)

        code = compile_to_code(graph)
        ns: dict = {}
        exec(code, ns)  # noqa: S102 -- test-only, on our own emitted code
        main_results = ns["main"](clients=clients)

        out_ports = _assemble(graph).out_ports
        forest_var = next(
            var for nid, pname, var in out_ports if nid == "n-forest" and pname == "plot"
        )

        assert exec_results["n-forest"]["plot"] == main_results[forest_var]
