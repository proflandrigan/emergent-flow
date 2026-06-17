"""
tests/test_vertical_slice.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Builds the Story 8 vertical-slice IR graph (the full five-family functional
pipeline: load_csv -> impute_missing -> {anova, train_classifier,
generate_html_summary}), writes it to examples/vertical_slice/pipeline.json,
re-loads and validates it -- then separately runs the runnable demo
(examples/vertical_slice/demo.py) end to end against the bundled sample
dataset.

Mirrors tests/test_examples.py's builder/fixture/round-trip pattern for the
IR half of this file (part a). Part (b) drives the real cm.* pipeline, so
those tests are slow: they invoke ydata-profiling to render the HTML report.

ADR refs: ADR 0002 (golden-test corpus), ADR 0003 (two paradigms).
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

from colonymind.ir import (
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
VERTICAL_SLICE_DIR = EXAMPLES_DIR / "vertical_slice"
DEMO_PATH = VERTICAL_SLICE_DIR / "demo.py"


# ---------------------------------------------------------------------------
# Builder: vertical_slice
# ---------------------------------------------------------------------------


def build_vertical_slice() -> Graph:
    """Build a FUNCTIONAL graph spanning all five SDK wrapper families.

    load_csv -> impute_missing, fanning out to anova, train_classifier, and
    generate_html_summary (three independent terminal consumers of the same
    cleaned frame).
    """

    # --- Node: data.load_csv ---
    node_load = Node(
        id="n-load",
        type="data.load_csv",
        label="Load CSV",
        paradigm=Paradigm.FUNCTIONAL,
        params=[
            Param(name="path", type_token="str", value="sample.csv"),
        ],
        ports=[
            Port(
                id="p-load-frame",
                name="frame",
                direction=Direction.OUT,
                data_type="DataFrame",
            ),
        ],
        position=Position(x=0.0, y=0.0),
    )

    # --- Node: clean.impute_missing ---
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

    # --- Node: stats.anova ---
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
        position=Position(x=400.0, y=-150.0),
    )

    # --- Node: ml.train_classifier ---
    node_train = Node(
        id="n-train",
        type="ml.train_classifier",
        label="Train Classifier",
        paradigm=Paradigm.FUNCTIONAL,
        params=[
            Param(name="target", type_token="str", value="converted"),
            Param(name="features", type_token="list[str]", value=["age", "spend", "score"]),
        ],
        ports=[
            Port(
                id="p-train-in",
                name="frame",
                direction=Direction.IN,
                data_type="DataFrame",
            ),
            Port(
                id="p-train-out",
                name="result",
                direction=Direction.OUT,
                data_type="ClassifierResult",
            ),
        ],
        position=Position(x=400.0, y=0.0),
    )

    # --- Node: reports.generate_html_summary ---
    node_report = Node(
        id="n-report",
        type="reports.generate_html_summary",
        label="HTML Summary",
        paradigm=Paradigm.FUNCTIONAL,
        params=[
            Param(name="title", type_token="str", value="Colony Mind — Vertical Slice"),
        ],
        ports=[
            Port(
                id="p-report-in",
                name="frame",
                direction=Direction.IN,
                data_type="DataFrame",
            ),
            Port(
                id="p-report-out",
                name="html",
                direction=Direction.OUT,
                data_type="HTML",
            ),
        ],
        position=Position(x=400.0, y=150.0),
    )

    # --- Edges: fan-out from impute to the three terminals ---
    edge_load_impute = Edge(
        id="e-load-impute",
        source=PortRef(node_id="n-load", port_id="p-load-frame"),
        target=PortRef(node_id="n-impute", port_id="p-impute-in"),
    )
    edge_impute_anova = Edge(
        id="e-impute-anova",
        source=PortRef(node_id="n-impute", port_id="p-impute-out"),
        target=PortRef(node_id="n-anova", port_id="p-anova-in"),
    )
    edge_impute_train = Edge(
        id="e-impute-train",
        source=PortRef(node_id="n-impute", port_id="p-impute-out"),
        target=PortRef(node_id="n-train", port_id="p-train-in"),
    )
    edge_impute_report = Edge(
        id="e-impute-report",
        source=PortRef(node_id="n-impute", port_id="p-impute-out"),
        target=PortRef(node_id="n-report", port_id="p-report-in"),
    )

    return Graph(
        paradigm=Paradigm.FUNCTIONAL,
        name="Vertical Slice Example",
        nodes={
            node_load.id: node_load,
            node_impute.id: node_impute,
            node_anova.id: node_anova,
            node_train.id: node_train,
            node_report.id: node_report,
        },
        edges={
            edge_load_impute.id: edge_load_impute,
            edge_impute_anova.id: edge_impute_anova,
            edge_impute_train.id: edge_impute_train,
            edge_impute_report.id: edge_impute_report,
        },
    )


# ---------------------------------------------------------------------------
# Fixture helpers: write JSON to examples/vertical_slice/ dir
# ---------------------------------------------------------------------------


def write_pipeline(graph: Graph) -> pathlib.Path:
    """Dump *graph* as pretty JSON to examples/vertical_slice/pipeline.json."""
    VERTICAL_SLICE_DIR.mkdir(exist_ok=True)
    path = VERTICAL_SLICE_DIR / "pipeline.json"
    path.write_text(graph.model_dump_json(indent=2), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Tests (a): IR graph construction and validation
# ---------------------------------------------------------------------------


class TestVerticalSlicePipeline:
    """Build, write, load, validate, and structurally assert the vertical-slice graph."""

    @pytest.fixture(autouse=True)
    def write_json(self) -> None:
        """Regenerate examples/vertical_slice/pipeline.json before each test."""
        graph = build_vertical_slice()
        write_pipeline(graph)

    def test_pipeline_loads_and_validates(self) -> None:
        path = VERTICAL_SLICE_DIR / "pipeline.json"
        assert path.exists(), "examples/vertical_slice/pipeline.json was not written"
        raw = path.read_text(encoding="utf-8")
        graph = Graph.model_validate_json(raw)
        assert graph is not None

    def test_pipeline_node_and_edge_counts(self) -> None:
        raw = (VERTICAL_SLICE_DIR / "pipeline.json").read_text(encoding="utf-8")
        graph = Graph.model_validate_json(raw)
        assert len(graph.nodes) == 5, f"Expected 5 nodes, got {len(graph.nodes)}"
        assert len(graph.edges) == 4, f"Expected 4 edges, got {len(graph.edges)}"

    def test_pipeline_paradigm(self) -> None:
        raw = (VERTICAL_SLICE_DIR / "pipeline.json").read_text(encoding="utf-8")
        graph = Graph.model_validate_json(raw)
        assert graph.paradigm == Paradigm.FUNCTIONAL

    def test_pipeline_round_trip(self) -> None:
        raw = (VERTICAL_SLICE_DIR / "pipeline.json").read_text(encoding="utf-8")
        graph1 = Graph.model_validate_json(raw)
        graph2 = Graph.model_validate_json(graph1.model_dump_json(indent=2))
        assert graph1 == graph2

    def test_pipeline_families_cover_full_slice(self) -> None:
        raw = (VERTICAL_SLICE_DIR / "pipeline.json").read_text(encoding="utf-8")
        graph = Graph.model_validate_json(raw)
        node_types = {node.type for node in graph.nodes.values()}
        assert node_types == {
            "data.load_csv",
            "clean.impute_missing",
            "stats.anova",
            "ml.train_classifier",
            "reports.generate_html_summary",
        }


# ---------------------------------------------------------------------------
# Tests (b): run the runnable demo end to end
#
# NOTE: these tests are slow -- they invoke ydata-profiling to render the
# HTML report for the full sample dataset.
# ---------------------------------------------------------------------------


def _load_demo():
    spec = importlib.util.spec_from_file_location("cm_vertical_slice_demo", DEMO_PATH)
    assert spec is not None and spec.loader is not None
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)
    return demo


class TestDemoRuns:
    """Drive examples/vertical_slice/demo.py end to end against the sample dataset."""

    def test_demo_produces_report(self, tmp_path: pathlib.Path) -> None:
        demo = _load_demo()
        summary = demo.run(output_dir=tmp_path)
        assert summary["report_path"].exists()
        text = summary["report_path"].read_text(encoding="utf-8")
        assert len(text) > 0
        assert "<html" in text.lower()

    def test_demo_anova_is_significant(self, tmp_path: pathlib.Path) -> None:
        demo = _load_demo()
        summary = demo.run(output_dir=tmp_path)
        assert summary["anova_p_value"] < 0.05
        assert summary["anova_f_statistic"] > 0

    def test_demo_classifier_trained(self, tmp_path: pathlib.Path) -> None:
        demo = _load_demo()
        summary = demo.run(output_dir=tmp_path)
        assert 0.0 <= summary["accuracy"] <= 1.0
