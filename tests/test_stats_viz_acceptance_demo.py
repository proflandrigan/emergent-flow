"""
tests/test_stats_viz_acceptance_demo.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Builds the Epic 12 Story 12 acceptance-demo IR graphs -- a hierarchical-modeling pipeline
(auto EDA -> VIF diagnostic + MixedLM fit -> coefficient/forest plot) and an exploratory-analysis
pipeline (describe + correlation heatmap + a faceted scatter with an OLS trendline) -- writes them
to examples/stats_viz_acceptance_demo/, re-loads and validates them, and proves ADR-0002
equivalence end to end.

Mirrors tests/test_sklearn_acceptance_demo.py's builder/fixture/round-trip pattern and reuses its
whole-graph ``assert_equivalent`` harness from tests/test_codegen_equivalence.py.
"""

from __future__ import annotations

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
from tests.test_codegen_equivalence import assert_equivalent

REPO_ROOT = pathlib.Path(__file__).parent.parent
EXAMPLES_DIR = REPO_ROOT / "examples"
DEMO_DIR = EXAMPLES_DIR / "stats_viz_acceptance_demo"


# ---------------------------------------------------------------------------
# Builder (a): hierarchical -- load_sample -> auto_eda -> {diagnostic_frame(vif),
# fit_model(MixedLM)} --(model)--> plot_coefficients
# ---------------------------------------------------------------------------


def build_hierarchical_demo() -> Graph:
    """auto EDA feeds both a VIF diagnostic and a MixedLM fit; the fitted model feeds a
    coefficient/forest plot."""
    node_load = Node(
        id="n-load",
        type="data.load_sample",
        label="Load Sample",
        paradigm=Paradigm.FUNCTIONAL,
        params=[Param(name="name", type_token="str", value="iris")],
        ports=[
            Port(id="p-load-frame", name="frame", direction=Direction.OUT, data_type="DataFrame"),
        ],
        position=Position(x=0.0, y=0.0),
    )

    node_eda = Node(
        id="n-eda",
        type="stats.auto_eda",
        label="Auto EDA",
        paradigm=Paradigm.FUNCTIONAL,
        params=[],
        ports=[
            Port(id="p-eda-in", name="frame", direction=Direction.IN, data_type="DataFrame"),
            Port(id="p-eda-frame", name="frame", direction=Direction.OUT, data_type="DataFrame"),
            Port(
                id="p-eda-profile", name="profile", direction=Direction.OUT, data_type="DataFrame"
            ),
            Port(
                id="p-eda-missingness",
                name="missingness",
                direction=Direction.OUT,
                data_type="DataFrame",
            ),
            Port(
                id="p-eda-correlation",
                name="correlation",
                direction=Direction.OUT,
                data_type="DataFrame",
            ),
            Port(
                id="p-eda-distribution-plot",
                name="distribution_plot",
                direction=Direction.OUT,
                data_type="PlotSpec",
            ),
            Port(
                id="p-eda-correlation-heatmap",
                name="correlation_heatmap",
                direction=Direction.OUT,
                data_type="PlotSpec",
            ),
            Port(
                id="p-eda-missingness-plot",
                name="missingness_plot",
                direction=Direction.OUT,
                data_type="PlotSpec",
            ),
        ],
        position=Position(x=200.0, y=0.0),
    )

    node_vif = Node(
        id="n-vif",
        type="stats.diagnostic_frame",
        label="VIF",
        paradigm=Paradigm.FUNCTIONAL,
        params=[Param(name="diagnostic", type_token="str", value="vif")],
        ports=[
            Port(id="p-vif-in", name="frame", direction=Direction.IN, data_type="DataFrame"),
            Port(
                id="p-vif-diagnostics",
                name="diagnostics",
                direction=Direction.OUT,
                data_type="DataFrame",
            ),
        ],
        position=Position(x=400.0, y=-100.0),
    )

    node_mixed = Node(
        id="n-mixed",
        type="stats.fit_mixed_model",
        label="Mixed-Effects Model",
        paradigm=Paradigm.FUNCTIONAL,
        params=[
            Param(name="target", type_token="str", value="sepal width (cm)"),
            Param(name="fixed_effects", type_token="list[str]", value=["petal length (cm)"]),
            Param(name="random_effects", type_token="list[str]", value=["petal length (cm)"]),
            Param(name="groups", type_token="str", value="target"),
        ],
        ports=[
            Port(id="p-mixed-in", name="frame", direction=Direction.IN, data_type="DataFrame"),
            Port(id="p-mixed-model", name="model", direction=Direction.OUT, data_type="StatsModel"),
        ],
        position=Position(x=400.0, y=100.0),
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
        position=Position(x=600.0, y=100.0),
    )

    edge_load_eda = Edge(
        id="e-load-eda",
        source=PortRef(node_id="n-load", port_id="p-load-frame"),
        target=PortRef(node_id="n-eda", port_id="p-eda-in"),
    )
    edge_eda_vif = Edge(
        id="e-eda-vif",
        source=PortRef(node_id="n-eda", port_id="p-eda-frame"),
        target=PortRef(node_id="n-vif", port_id="p-vif-in"),
    )
    edge_eda_mixed = Edge(
        id="e-eda-mixed",
        source=PortRef(node_id="n-eda", port_id="p-eda-frame"),
        target=PortRef(node_id="n-mixed", port_id="p-mixed-in"),
    )
    edge_mixed_forest = Edge(
        id="e-mixed-forest",
        source=PortRef(node_id="n-mixed", port_id="p-mixed-model"),
        target=PortRef(node_id="n-forest", port_id="p-forest-model"),
    )

    return Graph(
        paradigm=Paradigm.FUNCTIONAL,
        name="Stats/Viz Acceptance Demo -- Hierarchical",
        nodes={n.id: n for n in (node_load, node_eda, node_vif, node_mixed, node_forest)},
        edges={e.id: e for e in (edge_load_eda, edge_eda_vif, edge_eda_mixed, edge_mixed_forest)},
    )


# ---------------------------------------------------------------------------
# Builder (b): exploratory -- load_sample -> describe; load_sample -> correlation ->
# plot_correlation_heatmap; load_sample -> viz.plot(scatter, faceted, OLS trendline)
# ---------------------------------------------------------------------------


def build_exploratory_demo() -> Graph:
    """One load feeds three independent branches: a describe summary, a correlation heatmap,
    and a faceted scatter plot with an OLS trendline."""
    node_load = Node(
        id="n-load",
        type="data.load_sample",
        label="Load Sample",
        paradigm=Paradigm.FUNCTIONAL,
        params=[Param(name="name", type_token="str", value="iris")],
        ports=[
            Port(id="p-load-frame", name="frame", direction=Direction.OUT, data_type="DataFrame"),
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
        position=Position(x=200.0, y=-200.0),
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
        position=Position(x=200.0, y=0.0),
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
        position=Position(x=400.0, y=0.0),
    )

    node_scatter = Node(
        id="n-scatter",
        type="viz.plot",
        label="Scatter (faceted, OLS trendline)",
        paradigm=Paradigm.FUNCTIONAL,
        params=[
            Param(name="chart", type_token="str", value="scatter"),
            Param(
                name="encoding",
                type_token="dict[str, any]",
                value={
                    "x": "sepal length (cm)",
                    "y": "petal length (cm)",
                    "facet_col": "target",
                },
            ),
            Param(
                name="options",
                type_token="dict[str, any]",
                value={"trendline": "ols"},
            ),
        ],
        ports=[
            Port(id="p-scatter-in", name="frame", direction=Direction.IN, data_type="DataFrame"),
            Port(id="p-scatter-plot", name="plot", direction=Direction.OUT, data_type="PlotSpec"),
        ],
        position=Position(x=200.0, y=200.0),
    )

    edge_load_describe = Edge(
        id="e-load-describe",
        source=PortRef(node_id="n-load", port_id="p-load-frame"),
        target=PortRef(node_id="n-describe", port_id="p-describe-in"),
    )
    edge_load_corr = Edge(
        id="e-load-corr",
        source=PortRef(node_id="n-load", port_id="p-load-frame"),
        target=PortRef(node_id="n-corr", port_id="p-corr-in"),
    )
    edge_corr_heatmap = Edge(
        id="e-corr-heatmap",
        source=PortRef(node_id="n-corr", port_id="p-corr-matrix"),
        target=PortRef(node_id="n-heatmap", port_id="p-heatmap-in"),
    )
    edge_load_scatter = Edge(
        id="e-load-scatter",
        source=PortRef(node_id="n-load", port_id="p-load-frame"),
        target=PortRef(node_id="n-scatter", port_id="p-scatter-in"),
    )

    return Graph(
        paradigm=Paradigm.FUNCTIONAL,
        name="Stats/Viz Acceptance Demo -- Exploratory",
        nodes={n.id: n for n in (node_load, node_describe, node_corr, node_heatmap, node_scatter)},
        edges={
            e.id: e
            for e in (
                edge_load_describe,
                edge_load_corr,
                edge_corr_heatmap,
                edge_load_scatter,
            )
        },
    )


# ---------------------------------------------------------------------------
# Fixture helpers: write JSON to examples/stats_viz_acceptance_demo/
# ---------------------------------------------------------------------------


def write_pipeline(graph: Graph, filename: str) -> pathlib.Path:
    """Dump *graph* as pretty JSON to examples/stats_viz_acceptance_demo/<filename>."""
    DEMO_DIR.mkdir(exist_ok=True)
    path = DEMO_DIR / filename
    path.write_text(graph.model_dump_json(indent=2), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Drift guards: committed JSON must match what the builders generate. These run BEFORE the
# fixture classes below (pytest runs top-to-bottom in file-definition order), so they read the
# committed file before the autouse fixtures regenerate it.
# ---------------------------------------------------------------------------


def test_committed_hierarchical_json_is_current() -> None:
    committed = Graph.model_validate_json(
        (DEMO_DIR / "hierarchical_pipeline.json").read_text(encoding="utf-8")
    )
    assert committed == build_hierarchical_demo(), (
        "examples/stats_viz_acceptance_demo/hierarchical_pipeline.json is stale; run "
        "'pytest tests/test_stats_viz_acceptance_demo.py::TestHierarchicalDemo' to regenerate it"
    )


def test_committed_exploratory_json_is_current() -> None:
    committed = Graph.model_validate_json(
        (DEMO_DIR / "exploratory_pipeline.json").read_text(encoding="utf-8")
    )
    assert committed == build_exploratory_demo(), (
        "examples/stats_viz_acceptance_demo/exploratory_pipeline.json is stale; run "
        "'pytest tests/test_stats_viz_acceptance_demo.py::TestExploratoryDemo' to regenerate it"
    )


# ---------------------------------------------------------------------------
# Tests (a): hierarchical demo
# ---------------------------------------------------------------------------


class TestHierarchicalDemo:
    @pytest.fixture(autouse=True)
    def write_json(self) -> None:
        write_pipeline(build_hierarchical_demo(), "hierarchical_pipeline.json")

    def test_loads_and_validates(self) -> None:
        raw = (DEMO_DIR / "hierarchical_pipeline.json").read_text(encoding="utf-8")
        Graph.model_validate_json(raw)

    def test_node_and_edge_counts(self) -> None:
        graph = build_hierarchical_demo()
        assert len(graph.nodes) == 5
        assert len(graph.edges) == 4

    def test_node_types(self) -> None:
        graph = build_hierarchical_demo()
        node_types = {node.type for node in graph.nodes.values()}
        assert node_types == {
            "data.load_sample",
            "stats.auto_eda",
            "stats.diagnostic_frame",
            "stats.fit_mixed_model",
            "viz.plot_coefficients",
        }

    @pytest.mark.equivalence
    def test_equivalence(self) -> None:
        """ADR-0002: execute() == running the emitted code for the full hierarchical demo."""
        assert_equivalent(build_hierarchical_demo())


# ---------------------------------------------------------------------------
# Tests (b): exploratory demo
# ---------------------------------------------------------------------------


class TestExploratoryDemo:
    @pytest.fixture(autouse=True)
    def write_json(self) -> None:
        write_pipeline(build_exploratory_demo(), "exploratory_pipeline.json")

    def test_loads_and_validates(self) -> None:
        raw = (DEMO_DIR / "exploratory_pipeline.json").read_text(encoding="utf-8")
        Graph.model_validate_json(raw)

    def test_node_and_edge_counts(self) -> None:
        graph = build_exploratory_demo()
        assert len(graph.nodes) == 5
        assert len(graph.edges) == 4

    def test_node_types(self) -> None:
        graph = build_exploratory_demo()
        node_types = {node.type for node in graph.nodes.values()}
        assert node_types == {
            "data.load_sample",
            "stats.describe",
            "stats.correlation",
            "viz.plot_correlation_heatmap",
            "viz.plot",
        }

    @pytest.mark.equivalence
    def test_equivalence(self) -> None:
        """ADR-0002: execute() == running the emitted code for the full exploratory demo."""
        assert_equivalent(build_exploratory_demo())
