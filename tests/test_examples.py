"""
tests/test_examples.py
~~~~~~~~~~~~~~~~~~~~~~
Builds the two worked-example IR graphs (functional pipeline and declarative
module), writes them to examples/*.json, then re-loads and validates each one.

This file is the single source of truth for the example JSON files.  Running
the test suite regenerates examples/*.json deterministically (all ids are
stable explicit strings, never random UUIDs).

ADR refs: ADR 0002 (golden-test corpus), ADR 0003 (two paradigms).
"""

from __future__ import annotations

import json
import pathlib

import pytest

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

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = pathlib.Path(__file__).parent.parent
EXAMPLES_DIR = REPO_ROOT / "examples"


# ---------------------------------------------------------------------------
# Builder: functional_pipeline
# ---------------------------------------------------------------------------


def build_functional_pipeline() -> Graph:
    """Build a FUNCTIONAL graph: load_csv → impute_missing → anova."""

    # --- Node A: data.load_csv ---
    node_load = Node(
        id="n-load",
        type="data.load_csv",
        label="Load CSV",
        paradigm=Paradigm.FUNCTIONAL,
        params=[
            Param(
                name="path",
                type_token="str",
                value="examples/vertical_slice/sample.csv",
            ),
        ],
        ports=[
            Port(
                id="p-load-out",
                name="frame",
                direction=Direction.OUT,
                data_type="DataFrame",
            ),
        ],
        position=Position(x=0.0, y=0.0),
    )

    # --- Node B: clean.impute_missing ---
    node_impute = Node(
        id="n-impute",
        type="clean.impute_missing",
        label="Impute Missing",
        paradigm=Paradigm.FUNCTIONAL,
        params=[
            Param(name="strategy", type_token="str", value="median"),
        ],
        ports=[
            Port(
                id="p-impute-in",
                name="frame",
                direction=Direction.IN,
                data_type="DataFrame",
            ),
            Port(
                id="p-impute-out",
                name="frame",
                direction=Direction.OUT,
                data_type="DataFrame",
            ),
        ],
        position=Position(x=200.0, y=0.0),
    )

    # --- Node C: stats.anova ---
    node_anova = Node(
        id="n-anova",
        type="stats.anova",
        label="ANOVA",
        paradigm=Paradigm.FUNCTIONAL,
        params=[
            Param(name="group_col", type_token="str", value="cohort"),
            Param(name="value_col", type_token="str", value="score"),
        ],
        ports=[
            Port(
                id="p-anova-in",
                name="frame",
                direction=Direction.IN,
                data_type="DataFrame",
            ),
            Port(
                id="p-anova-out",
                name="result",
                direction=Direction.OUT,
                data_type="AnovaResult",
            ),
        ],
        position=Position(x=400.0, y=0.0),
    )

    # --- Edges ---
    edge_load_impute = Edge(
        id="e-load-impute",
        source=PortRef(node_id="n-load", port_id="p-load-out"),
        target=PortRef(node_id="n-impute", port_id="p-impute-in"),
    )
    edge_impute_anova = Edge(
        id="e-impute-anova",
        source=PortRef(node_id="n-impute", port_id="p-impute-out"),
        target=PortRef(node_id="n-anova", port_id="p-anova-in"),
    )

    return Graph(
        paradigm=Paradigm.FUNCTIONAL,
        name="Functional Pipeline Example",
        nodes={
            node_load.id: node_load,
            node_impute.id: node_impute,
            node_anova.id: node_anova,
        },
        edges={
            edge_load_impute.id: edge_load_impute,
            edge_impute_anova.id: edge_impute_anova,
        },
    )


# ---------------------------------------------------------------------------
# Builder: declarative_module
# ---------------------------------------------------------------------------


def build_declarative_module() -> Graph:
    """Build a DECLARATIVE graph: single composite nn.module node with
    a subgraph containing three layer nodes (linear→relu→linear) wired in series.

    Option A nesting (ADR 0003): outer graph holds ONE composite node;
    layer nodes live in that node's subgraph, not the outer graph.
    """

    # --- Subgraph nodes ---
    node_linear1 = Node(
        id="n-linear1",
        type="nn.linear",
        label="Linear 128→64",
        paradigm=Paradigm.DECLARATIVE,
        params=[
            Param(name="in_features", type_token="int", value=128),
            Param(name="out_features", type_token="int", value=64),
        ],
        ports=[
            Port(
                id="p-linear1-in",
                name="x",
                direction=Direction.IN,
                data_type="Tensor",
            ),
            Port(
                id="p-linear1-out",
                name="out",
                direction=Direction.OUT,
                data_type="Tensor",
            ),
        ],
        position=Position(x=0.0, y=0.0),
    )

    node_relu = Node(
        id="n-relu",
        type="nn.relu",
        label="ReLU",
        paradigm=Paradigm.DECLARATIVE,
        ports=[
            Port(
                id="p-relu-in",
                name="x",
                direction=Direction.IN,
                data_type="Tensor",
            ),
            Port(
                id="p-relu-out",
                name="out",
                direction=Direction.OUT,
                data_type="Tensor",
            ),
        ],
        position=Position(x=200.0, y=0.0),
    )

    node_linear2 = Node(
        id="n-linear2",
        type="nn.linear",
        label="Linear 64→10",
        paradigm=Paradigm.DECLARATIVE,
        params=[
            Param(name="in_features", type_token="int", value=64),
            Param(name="out_features", type_token="int", value=10),
        ],
        ports=[
            Port(
                id="p-linear2-in",
                name="x",
                direction=Direction.IN,
                data_type="Tensor",
            ),
            Port(
                id="p-linear2-out",
                name="out",
                direction=Direction.OUT,
                data_type="Tensor",
            ),
        ],
        position=Position(x=400.0, y=0.0),
    )

    # --- Subgraph edges ---
    edge_l1_relu = Edge(
        id="e-linear1-relu",
        source=PortRef(node_id="n-linear1", port_id="p-linear1-out"),
        target=PortRef(node_id="n-relu", port_id="p-relu-in"),
    )
    edge_relu_l2 = Edge(
        id="e-relu-linear2",
        source=PortRef(node_id="n-relu", port_id="p-relu-out"),
        target=PortRef(node_id="n-linear2", port_id="p-linear2-in"),
    )

    # --- Inner subgraph ---
    subgraph = Graph(
        paradigm=Paradigm.DECLARATIVE,
        name="SimpleClassifier body",
        nodes={
            node_linear1.id: node_linear1,
            node_relu.id: node_relu,
            node_linear2.id: node_linear2,
        },
        edges={
            edge_l1_relu.id: edge_l1_relu,
            edge_relu_l2.id: edge_relu_l2,
        },
    )

    # --- Composite node (outer graph holds only this) ---
    node_module = Node(
        id="n-module",
        type="nn.module",
        label="SimpleClassifier",
        paradigm=Paradigm.DECLARATIVE,
        subgraph=subgraph,
    )

    return Graph(
        paradigm=Paradigm.DECLARATIVE,
        name="Declarative Module Example",
        nodes={node_module.id: node_module},
        edges={},
    )


# ---------------------------------------------------------------------------
# Fixture helpers: write JSON to examples/ dir
# ---------------------------------------------------------------------------


def write_example(graph: Graph, filename: str) -> pathlib.Path:
    """Dump *graph* as pretty JSON to examples/<filename> and return the path."""
    EXAMPLES_DIR.mkdir(exist_ok=True)
    path = EXAMPLES_DIR / filename
    path.write_text(graph.model_dump_json(indent=2), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFunctionalPipeline:
    """Build, write, load, validate, and structurally assert the functional example."""

    @pytest.fixture(autouse=True)
    def write_json(self):
        """Regenerate examples/functional_pipeline.json before each test."""
        graph = build_functional_pipeline()
        write_example(graph, "functional_pipeline.json")

    def test_loads_and_validates(self):
        path = EXAMPLES_DIR / "functional_pipeline.json"
        assert path.exists(), "examples/functional_pipeline.json was not written"
        raw = path.read_text(encoding="utf-8")
        graph = Graph.model_validate_json(raw)
        assert graph is not None

    def test_paradigm(self):
        raw = (EXAMPLES_DIR / "functional_pipeline.json").read_text(encoding="utf-8")
        graph = Graph.model_validate_json(raw)
        assert graph.paradigm == Paradigm.FUNCTIONAL

    def test_node_and_edge_counts(self):
        raw = (EXAMPLES_DIR / "functional_pipeline.json").read_text(encoding="utf-8")
        graph = Graph.model_validate_json(raw)
        assert len(graph.nodes) == 3, f"Expected 3 nodes, got {len(graph.nodes)}"
        assert len(graph.edges) == 2, f"Expected 2 edges, got {len(graph.edges)}"

    def test_round_trip(self):
        raw = (EXAMPLES_DIR / "functional_pipeline.json").read_text(encoding="utf-8")
        graph1 = Graph.model_validate_json(raw)
        graph2 = Graph.model_validate_json(graph1.model_dump_json(indent=2))
        assert graph1 == graph2

    def test_json_is_valid_json(self):
        raw = (EXAMPLES_DIR / "functional_pipeline.json").read_text(encoding="utf-8")
        obj = json.loads(raw)
        assert isinstance(obj, dict)
        assert obj["paradigm"] == "functional"


class TestDeclarativeModule:
    """Build, write, load, validate, and structurally assert the declarative example."""

    @pytest.fixture(autouse=True)
    def write_json(self):
        """Regenerate examples/declarative_module.json before each test."""
        graph = build_declarative_module()
        write_example(graph, "declarative_module.json")

    def test_loads_and_validates(self):
        path = EXAMPLES_DIR / "declarative_module.json"
        assert path.exists(), "examples/declarative_module.json was not written"
        raw = path.read_text(encoding="utf-8")
        graph = Graph.model_validate_json(raw)
        assert graph is not None

    def test_paradigm(self):
        raw = (EXAMPLES_DIR / "declarative_module.json").read_text(encoding="utf-8")
        graph = Graph.model_validate_json(raw)
        assert graph.paradigm == Paradigm.DECLARATIVE

    def test_outer_graph_has_one_node(self):
        raw = (EXAMPLES_DIR / "declarative_module.json").read_text(encoding="utf-8")
        graph = Graph.model_validate_json(raw)
        assert len(graph.nodes) == 1, f"Expected 1 top-level node, got {len(graph.nodes)}"
        assert len(graph.edges) == 0, f"Expected 0 top-level edges, got {len(graph.edges)}"

    def test_subgraph_has_three_child_nodes(self):
        raw = (EXAMPLES_DIR / "declarative_module.json").read_text(encoding="utf-8")
        graph = Graph.model_validate_json(raw)
        module_node = graph.nodes["n-module"]
        assert module_node.subgraph is not None, "Composite node must have a subgraph"
        assert len(module_node.subgraph.nodes) == 3, (
            f"Expected 3 child nodes in subgraph, got {len(module_node.subgraph.nodes)}"
        )

    def test_subgraph_wired_with_two_edges(self):
        raw = (EXAMPLES_DIR / "declarative_module.json").read_text(encoding="utf-8")
        graph = Graph.model_validate_json(raw)
        subgraph = graph.nodes["n-module"].subgraph
        assert len(subgraph.edges) == 2, f"Expected 2 edges in subgraph, got {len(subgraph.edges)}"

    def test_round_trip(self):
        raw = (EXAMPLES_DIR / "declarative_module.json").read_text(encoding="utf-8")
        graph1 = Graph.model_validate_json(raw)
        graph2 = Graph.model_validate_json(graph1.model_dump_json(indent=2))
        assert graph1 == graph2

    def test_json_is_valid_json(self):
        raw = (EXAMPLES_DIR / "declarative_module.json").read_text(encoding="utf-8")
        obj = json.loads(raw)
        assert isinstance(obj, dict)
        assert obj["paradigm"] == "declarative"
