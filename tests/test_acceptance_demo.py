"""
tests/test_acceptance_demo.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Builds the Story 7 acceptance-demo IR graph (8-node functional pipeline:
load_sample(diabetes) -> drop_missing -> select_columns -> train_test_split
-> train_regressor --(model)--> evaluate, with select_columns also fanning
out to stats.describe and reports.generate_html_summary), writes it to
examples/acceptance_demo/pipeline.json, re-loads and validates it.

Mirrors tests/test_vertical_slice.py (part a) — same imports, same
builder/fixture/round-trip pattern, same style.

ADR refs: ADR 0002 (golden-test corpus), ADR 0003 (two paradigms).
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

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = pathlib.Path(__file__).parent.parent
EXAMPLES_DIR = REPO_ROOT / "examples"
ACCEPTANCE_DIR = EXAMPLES_DIR / "acceptance_demo"


# ---------------------------------------------------------------------------
# Builder: acceptance_demo
# ---------------------------------------------------------------------------


def build_acceptance_demo() -> Graph:
    """Build a FUNCTIONAL graph spanning the Story 7 acceptance-demo pipeline.

    load_sample(diabetes) -> drop_missing -> select_columns --+--> train_test_split
      --+->(train) train_regressor --(model)--> evaluate
        +->(test) ----------------------+-------> evaluate
      +--> stats.describe
      +--> reports.generate_html_summary
    """

    # --- Node 1: data.load_sample ---
    node_load = Node(
        id="n-load",
        type="data.load_sample",
        label="Load Sample",
        paradigm=Paradigm.FUNCTIONAL,
        params=[
            Param(name="name", type_token="str", value="diabetes"),
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

    # --- Node 2: clean.drop_missing ---
    node_drop = Node(
        id="n-drop",
        type="clean.drop_missing",
        label="Drop Missing",
        paradigm=Paradigm.FUNCTIONAL,
        params=[
            Param(name="axis", type_token="str", value="rows"),
            Param(name="how", type_token="str", value="any"),
        ],
        ports=[
            Port(
                id="p-drop-in",
                name="frame",
                direction=Direction.IN,
                data_type="DataFrame",
            ),
            Port(
                id="p-drop-out",
                name="frame",
                direction=Direction.OUT,
                data_type="DataFrame",
            ),
        ],
        position=Position(x=200.0, y=0.0),
    )

    # --- Node 3: clean.select_columns ---
    node_select = Node(
        id="n-select",
        type="clean.select_columns",
        label="Select Columns",
        paradigm=Paradigm.FUNCTIONAL,
        params=[
            Param(
                name="columns",
                type_token="list[str]",
                value=["age", "bmi", "bp", "s1", "target"],
            ),
            Param(name="drop", type_token="bool", value=False),
        ],
        ports=[
            Port(
                id="p-select-in",
                name="frame",
                direction=Direction.IN,
                data_type="DataFrame",
            ),
            Port(
                id="p-select-out",
                name="frame",
                direction=Direction.OUT,
                data_type="DataFrame",
            ),
        ],
        position=Position(x=400.0, y=0.0),
    )

    # --- Node 4: ml.train_test_split ---
    node_split = Node(
        id="n-split",
        type="ml.train_test_split",
        label="Train/Test Split",
        paradigm=Paradigm.FUNCTIONAL,
        params=[
            Param(name="test_size", type_token="float", value=0.25),
            Param(name="random_state", type_token="int", value=0),
        ],
        ports=[
            Port(
                id="p-split-in",
                name="frame",
                direction=Direction.IN,
                data_type="DataFrame",
            ),
            Port(
                id="p-split-train",
                name="train",
                direction=Direction.OUT,
                data_type="DataFrame",
            ),
            Port(
                id="p-split-test",
                name="test",
                direction=Direction.OUT,
                data_type="DataFrame",
            ),
        ],
        position=Position(x=600.0, y=0.0),
    )

    # --- Node 5: ml.train_regressor ---
    node_train = Node(
        id="n-train",
        type="ml.train_regressor",
        label="Train Regressor",
        paradigm=Paradigm.FUNCTIONAL,
        params=[
            Param(name="target", type_token="str", value="target"),
            Param(
                name="features",
                type_token="list[str]",
                value=["age", "bmi", "bp", "s1"],
            ),
        ],
        ports=[
            Port(
                id="p-train-in",
                name="frame",
                direction=Direction.IN,
                data_type="DataFrame",
            ),
            Port(
                id="p-train-model",
                name="model",
                direction=Direction.OUT,
                data_type="Model",
            ),
        ],
        position=Position(x=800.0, y=-100.0),
    )

    # --- Node 6: ml.evaluate ---
    node_eval = Node(
        id="n-eval",
        type="ml.evaluate",
        label="Evaluate",
        paradigm=Paradigm.FUNCTIONAL,
        params=[],
        ports=[
            Port(
                id="p-eval-model",
                name="model",
                direction=Direction.IN,
                data_type="Model",
            ),
            Port(
                id="p-eval-frame",
                name="frame",
                direction=Direction.IN,
                data_type="DataFrame",
            ),
            Port(
                id="p-eval-result",
                name="result",
                direction=Direction.OUT,
                data_type="EvaluationResult",
            ),
        ],
        position=Position(x=1000.0, y=0.0),
    )

    # --- Node 7: stats.describe ---
    node_describe = Node(
        id="n-describe",
        type="stats.describe",
        label="Describe",
        paradigm=Paradigm.FUNCTIONAL,
        params=[
            Param(name="columns", type_token="list[str]", value=None),
        ],
        ports=[
            Port(
                id="p-describe-in",
                name="frame",
                direction=Direction.IN,
                data_type="DataFrame",
            ),
            Port(
                id="p-describe-out",
                name="summary",
                direction=Direction.OUT,
                data_type="DataFrame",
            ),
        ],
        position=Position(x=600.0, y=150.0),
    )

    # --- Node 8: reports.generate_html_summary ---
    node_report = Node(
        id="n-report",
        type="reports.generate_html_summary",
        label="HTML Summary",
        paradigm=Paradigm.FUNCTIONAL,
        params=[
            Param(
                name="title",
                type_token="str",
                value="Emergent Flow — Acceptance Demo",
            ),
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
        position=Position(x=600.0, y=300.0),
    )

    # --- Edges (8 total — one per IN port) ---
    edge_load_drop = Edge(
        id="e-load-drop",
        source=PortRef(node_id="n-load", port_id="p-load-frame"),
        target=PortRef(node_id="n-drop", port_id="p-drop-in"),
    )
    edge_drop_select = Edge(
        id="e-drop-select",
        source=PortRef(node_id="n-drop", port_id="p-drop-out"),
        target=PortRef(node_id="n-select", port_id="p-select-in"),
    )
    edge_select_split = Edge(
        id="e-select-split",
        source=PortRef(node_id="n-select", port_id="p-select-out"),
        target=PortRef(node_id="n-split", port_id="p-split-in"),
    )
    edge_select_describe = Edge(
        id="e-select-describe",
        source=PortRef(node_id="n-select", port_id="p-select-out"),
        target=PortRef(node_id="n-describe", port_id="p-describe-in"),
    )
    edge_select_report = Edge(
        id="e-select-report",
        source=PortRef(node_id="n-select", port_id="p-select-out"),
        target=PortRef(node_id="n-report", port_id="p-report-in"),
    )
    edge_split_train = Edge(
        id="e-split-train",
        source=PortRef(node_id="n-split", port_id="p-split-train"),
        target=PortRef(node_id="n-train", port_id="p-train-in"),
    )
    edge_train_eval = Edge(
        id="e-train-eval",
        source=PortRef(node_id="n-train", port_id="p-train-model"),
        target=PortRef(node_id="n-eval", port_id="p-eval-model"),
    )
    edge_split_eval_test = Edge(
        id="e-split-eval-test",
        source=PortRef(node_id="n-split", port_id="p-split-test"),
        target=PortRef(node_id="n-eval", port_id="p-eval-frame"),
    )

    return Graph(
        paradigm=Paradigm.FUNCTIONAL,
        name="Acceptance Demo",
        nodes={
            node_load.id: node_load,
            node_drop.id: node_drop,
            node_select.id: node_select,
            node_split.id: node_split,
            node_train.id: node_train,
            node_eval.id: node_eval,
            node_describe.id: node_describe,
            node_report.id: node_report,
        },
        edges={
            edge_load_drop.id: edge_load_drop,
            edge_drop_select.id: edge_drop_select,
            edge_select_split.id: edge_select_split,
            edge_select_describe.id: edge_select_describe,
            edge_select_report.id: edge_select_report,
            edge_split_train.id: edge_split_train,
            edge_train_eval.id: edge_train_eval,
            edge_split_eval_test.id: edge_split_eval_test,
        },
    )


# ---------------------------------------------------------------------------
# Fixture helpers: write JSON to examples/acceptance_demo/ dir
# ---------------------------------------------------------------------------


def write_pipeline(graph: Graph) -> pathlib.Path:
    """Dump *graph* as pretty JSON to examples/acceptance_demo/pipeline.json."""
    ACCEPTANCE_DIR.mkdir(exist_ok=True)
    path = ACCEPTANCE_DIR / "pipeline.json"
    path.write_text(graph.model_dump_json(indent=2), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Drift guard: committed JSON must match what the builder generates
# ---------------------------------------------------------------------------


def test_committed_pipeline_json_is_current() -> None:
    """Committed pipeline.json must round-trip identically to build_acceptance_demo().

    Runs before TestAcceptanceDemoPipeline so it reads the committed file before
    the autouse fixture regenerates it. Fails fast if the builder changed without
    the committed artifact being updated.
    """
    committed = Graph.model_validate_json(
        (ACCEPTANCE_DIR / "pipeline.json").read_text(encoding="utf-8")
    )
    assert committed == build_acceptance_demo(), (
        "examples/acceptance_demo/pipeline.json is stale; run "
        "'pytest tests/test_acceptance_demo.py::TestAcceptanceDemoPipeline' to regenerate it"
    )


# ---------------------------------------------------------------------------
# Tests (a): IR graph construction and validation
# ---------------------------------------------------------------------------


class TestAcceptanceDemoPipeline:
    """Build, write, load, validate, and structurally assert the acceptance-demo graph."""

    @pytest.fixture(autouse=True)
    def write_json(self) -> None:
        """Regenerate examples/acceptance_demo/pipeline.json before each test."""
        graph = build_acceptance_demo()
        write_pipeline(graph)

    def test_pipeline_loads_and_validates(self) -> None:
        path = ACCEPTANCE_DIR / "pipeline.json"
        assert path.exists(), "examples/acceptance_demo/pipeline.json was not written"
        raw = path.read_text(encoding="utf-8")
        Graph.model_validate_json(raw)

    def test_pipeline_node_and_edge_counts(self) -> None:
        raw = (ACCEPTANCE_DIR / "pipeline.json").read_text(encoding="utf-8")
        graph = Graph.model_validate_json(raw)
        assert len(graph.nodes) == 8, f"Expected 8 nodes, got {len(graph.nodes)}"
        assert len(graph.edges) == 8, f"Expected 8 edges, got {len(graph.edges)}"

    def test_pipeline_paradigm(self) -> None:
        raw = (ACCEPTANCE_DIR / "pipeline.json").read_text(encoding="utf-8")
        graph = Graph.model_validate_json(raw)
        assert graph.paradigm == Paradigm.FUNCTIONAL

    def test_pipeline_round_trip(self) -> None:
        raw = (ACCEPTANCE_DIR / "pipeline.json").read_text(encoding="utf-8")
        graph1 = Graph.model_validate_json(raw)
        graph2 = Graph.model_validate_json(graph1.model_dump_json(indent=2))
        assert graph1 == graph2

    def test_pipeline_node_types(self) -> None:
        raw = (ACCEPTANCE_DIR / "pipeline.json").read_text(encoding="utf-8")
        graph = Graph.model_validate_json(raw)
        node_types = {node.type for node in graph.nodes.values()}
        assert node_types == {
            "data.load_sample",
            "clean.drop_missing",
            "clean.select_columns",
            "ml.train_test_split",
            "ml.train_regressor",
            "ml.evaluate",
            "stats.describe",
            "reports.generate_html_summary",
        }

    def test_pipeline_has_model_edge(self) -> None:
        raw = (ACCEPTANCE_DIR / "pipeline.json").read_text(encoding="utf-8")
        graph = Graph.model_validate_json(raw)

        # Locate the source port on n-train that carries data_type="Model"
        train_node = graph.nodes["n-train"]
        model_out_port = next(
            (p for p in train_node.ports if p.id == "p-train-model"),
            None,
        )
        assert model_out_port is not None, "n-train must have port p-train-model"
        assert model_out_port.data_type == "Model", (
            f"Expected data_type='Model', got {model_out_port.data_type!r}"
        )

        # Confirm an edge exists from p-train-model to n-eval's p-eval-model IN port
        model_edge = next(
            (
                e
                for e in graph.edges.values()
                if e.source.node_id == "n-train"
                and e.source.port_id == "p-train-model"
                and e.target.node_id == "n-eval"
                and e.target.port_id == "p-eval-model"
            ),
            None,
        )
        assert model_edge is not None, (
            "Expected an edge from n-train:p-train-model to n-eval:p-eval-model"
        )


# ---------------------------------------------------------------------------
# Tests (b): run the runnable demo end to end
#
# NOTE: these tests are slow -- they invoke ydata-profiling to render the
# HTML report for the full diabetes dataset.
# ---------------------------------------------------------------------------

DEMO_PATH = ACCEPTANCE_DIR / "demo.py"


def _load_demo():
    import importlib.util

    spec = importlib.util.spec_from_file_location("ef_acceptance_demo", DEMO_PATH)
    assert spec is not None and spec.loader is not None
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)
    return demo


@pytest.fixture(scope="class")
def _demo_summary(tmp_path_factory: pytest.TempPathFactory) -> dict:
    """Run the acceptance demo pipeline once; shared across all TestDemoRuns tests."""
    return _load_demo().run(output_dir=tmp_path_factory.mktemp("demo_out"))


class TestDemoRuns:
    """Drive examples/acceptance_demo/demo.py end to end against the bundled diabetes dataset."""

    def test_demo_produces_report(self, _demo_summary: dict) -> None:
        assert _demo_summary["report_path"].exists()
        text = _demo_summary["report_path"].read_text(encoding="utf-8")
        assert len(text) > 0
        assert "<html" in text.lower()

    def test_demo_metrics_present(self, _demo_summary: dict) -> None:
        assert 0.0 < _demo_summary["r2"] < 1.0
        assert _demo_summary["mae"] > 0
        assert _demo_summary["n_test"] > 0

    def test_demo_describe_nonempty(self, _demo_summary: dict) -> None:
        assert _demo_summary["describe_rows"] > 0
