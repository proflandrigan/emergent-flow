"""
tests/test_sklearn_acceptance_demo.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Builds the Epic 8 Story 10 acceptance-demo IR graphs -- a supervised pipeline (scale ->
select-k-best -> gradient-boosting -> evaluate, composed as one ml.pipeline step chain) and an
unsupervised pipeline (scale -> cluster -> summarize, plus a Transformer-bearing edge into a
companion ml.transform node) -- writes them to examples/sklearn_acceptance_demo/, re-loads and
validates them, and proves ADR-0002 equivalence end to end.

Mirrors tests/test_acceptance_demo.py's builder/fixture/round-trip pattern and reuses its
whole-graph ``assert_equivalent`` harness from tests/test_codegen_equivalence.py.

These supersede the Epic 6 demo-sized ``ef.ml`` slice (train_regressor/predict/evaluate) as the
"classical ML the app can do today" reference -- see docs/classical-ml-acceptance-demo.md.
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
DEMO_DIR = EXAMPLES_DIR / "sklearn_acceptance_demo"

IRIS_FEATURES = [
    "sepal length (cm)",
    "sepal width (cm)",
    "petal length (cm)",
    "petal width (cm)",
]


# ---------------------------------------------------------------------------
# Builder (a): supervised -- load_sample -> drop_missing -> ml.pipeline([StandardScaler,
# SelectKBest, GradientBoostingClassifier]) --(model)--> evaluate
# ---------------------------------------------------------------------------


def build_supervised_demo() -> Graph:
    """scale -> select-k-best -> gradient-boosting -> evaluate, composed as one ml.pipeline
    step chain (see the module docstring for why this can't be 3 separate DataFrame-chained
    nodes)."""
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
            Port(id="p-drop-in", name="frame", direction=Direction.IN, data_type="DataFrame"),
            Port(id="p-drop-out", name="frame", direction=Direction.OUT, data_type="DataFrame"),
        ],
        position=Position(x=200.0, y=0.0),
    )

    node_pipeline = Node(
        id="n-pipeline",
        type="ml.pipeline",
        label="Scale + Select + Classify",
        paradigm=Paradigm.FUNCTIONAL,
        params=[
            Param(
                name="steps",
                type_token="list[dict[str, any]]",
                value=[
                    {"estimator": "StandardScaler", "params": {}},
                    {"estimator": "SelectKBest", "params": {"k": 2}},
                    {
                        "estimator": "GradientBoostingClassifier",
                        "params": {"n_estimators": 50, "random_state": 0},
                    },
                ],
            ),
            Param(name="target", type_token="str", value="target"),
            Param(name="features", type_token="list[str]", value=IRIS_FEATURES),
        ],
        ports=[
            Port(id="p-pipeline-in", name="frame", direction=Direction.IN, data_type="DataFrame"),
            Port(id="p-pipeline-model", name="model", direction=Direction.OUT, data_type="Model"),
        ],
        position=Position(x=400.0, y=0.0),
    )

    node_eval = Node(
        id="n-eval",
        type="ml.evaluate",
        label="Evaluate",
        paradigm=Paradigm.FUNCTIONAL,
        params=[],
        ports=[
            Port(id="p-eval-model", name="model", direction=Direction.IN, data_type="Model"),
            Port(id="p-eval-frame", name="frame", direction=Direction.IN, data_type="DataFrame"),
            Port(
                id="p-eval-result",
                name="result",
                direction=Direction.OUT,
                data_type="EvaluationResult",
            ),
        ],
        position=Position(x=600.0, y=0.0),
    )

    edge_load_drop = Edge(
        id="e-load-drop",
        source=PortRef(node_id="n-load", port_id="p-load-frame"),
        target=PortRef(node_id="n-drop", port_id="p-drop-in"),
    )
    edge_drop_pipeline = Edge(
        id="e-drop-pipeline",
        source=PortRef(node_id="n-drop", port_id="p-drop-out"),
        target=PortRef(node_id="n-pipeline", port_id="p-pipeline-in"),
    )
    edge_pipeline_eval_model = Edge(
        id="e-pipeline-eval-model",
        source=PortRef(node_id="n-pipeline", port_id="p-pipeline-model"),
        target=PortRef(node_id="n-eval", port_id="p-eval-model"),
    )
    edge_drop_eval_frame = Edge(
        id="e-drop-eval-frame",
        source=PortRef(node_id="n-drop", port_id="p-drop-out"),
        target=PortRef(node_id="n-eval", port_id="p-eval-frame"),
    )

    return Graph(
        paradigm=Paradigm.FUNCTIONAL,
        name="Sklearn Acceptance Demo -- Supervised",
        nodes={n.id: n for n in (node_load, node_drop, node_pipeline, node_eval)},
        edges={
            e.id: e
            for e in (
                edge_load_drop,
                edge_drop_pipeline,
                edge_pipeline_eval_model,
                edge_drop_eval_frame,
            )
        },
    )


# ---------------------------------------------------------------------------
# Builder (b): unsupervised -- load_sample -> ml.fit_transform(StandardScaler) ->
# ml.cluster_detect(KMeans) --(model)--> ml.summarize, plus a Transformer-bearing edge into a
# companion ml.transform node applied to the same load frame.
# ---------------------------------------------------------------------------


def build_unsupervised_demo() -> Graph:
    """scale -> cluster -> summarize, plus a Transformer-bearing edge (see the module
    docstring for why PCA isn't chained in as a second fit_transform step here)."""
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

    node_scale = Node(
        id="n-scale",
        type="ml.fit_transform",
        label="Scale",
        paradigm=Paradigm.FUNCTIONAL,
        params=[
            Param(name="estimator", type_token="str", value="StandardScaler"),
            Param(name="target", type_token="str", value=None),
            Param(name="features", type_token="list[str]", value=IRIS_FEATURES),
            Param(name="params", type_token="dict[str, any]", value={}),
        ],
        ports=[
            Port(id="p-scale-in", name="frame", direction=Direction.IN, data_type="DataFrame"),
            Port(
                id="p-scale-transformer",
                name="transformer",
                direction=Direction.OUT,
                data_type="Transformer",
            ),
            Port(
                id="p-scale-result", name="result", direction=Direction.OUT, data_type="DataFrame"
            ),
        ],
        position=Position(x=200.0, y=0.0),
    )

    node_cluster = Node(
        id="n-cluster",
        type="ml.cluster_detect",
        label="Cluster",
        paradigm=Paradigm.FUNCTIONAL,
        params=[
            Param(name="estimator", type_token="str", value="KMeans"),
            Param(
                name="features",
                type_token="list[str]",
                value=["component_0", "component_1", "component_2", "component_3"],
            ),
            Param(
                name="params",
                type_token="dict[str, any]",
                value={"n_clusters": 3, "n_init": 5},
            ),
        ],
        ports=[
            Port(id="p-cluster-in", name="frame", direction=Direction.IN, data_type="DataFrame"),
            Port(id="p-cluster-model", name="model", direction=Direction.OUT, data_type="Model"),
            Port(
                id="p-cluster-result",
                name="result",
                direction=Direction.OUT,
                data_type="DataFrame",
            ),
        ],
        position=Position(x=400.0, y=0.0),
    )

    node_summarize = Node(
        id="n-summarize",
        type="ml.summarize",
        label="Summarize",
        paradigm=Paradigm.FUNCTIONAL,
        params=[],
        ports=[
            Port(id="p-summarize-model", name="model", direction=Direction.IN, data_type="Model"),
            Port(
                id="p-summarize-summary",
                name="summary",
                direction=Direction.OUT,
                data_type="ModelSummary",
            ),
        ],
        position=Position(x=600.0, y=0.0),
    )

    node_transform = Node(
        id="n-transform",
        type="ml.transform",
        label="Transform New Data",
        paradigm=Paradigm.FUNCTIONAL,
        params=[Param(name="op", type_token="str", value="transform")],
        ports=[
            Port(
                id="p-transform-transformer",
                name="transformer",
                direction=Direction.IN,
                data_type="Transformer",
            ),
            Port(
                id="p-transform-frame",
                name="frame",
                direction=Direction.IN,
                data_type="DataFrame",
            ),
            Port(
                id="p-transform-result",
                name="result",
                direction=Direction.OUT,
                data_type="DataFrame",
            ),
        ],
        position=Position(x=400.0, y=200.0),
    )

    edge_load_scale = Edge(
        id="e-load-scale",
        source=PortRef(node_id="n-load", port_id="p-load-frame"),
        target=PortRef(node_id="n-scale", port_id="p-scale-in"),
    )
    edge_scale_cluster = Edge(
        id="e-scale-cluster",
        source=PortRef(node_id="n-scale", port_id="p-scale-result"),
        target=PortRef(node_id="n-cluster", port_id="p-cluster-in"),
    )
    edge_cluster_summarize = Edge(
        id="e-cluster-summarize",
        source=PortRef(node_id="n-cluster", port_id="p-cluster-model"),
        target=PortRef(node_id="n-summarize", port_id="p-summarize-model"),
    )
    edge_scale_transform = Edge(
        id="e-scale-transform",
        source=PortRef(node_id="n-scale", port_id="p-scale-transformer"),
        target=PortRef(node_id="n-transform", port_id="p-transform-transformer"),
    )
    edge_load_transform_frame = Edge(
        id="e-load-transform-frame",
        source=PortRef(node_id="n-load", port_id="p-load-frame"),
        target=PortRef(node_id="n-transform", port_id="p-transform-frame"),
    )

    return Graph(
        paradigm=Paradigm.FUNCTIONAL,
        name="Sklearn Acceptance Demo -- Unsupervised",
        nodes={
            n.id: n for n in (node_load, node_scale, node_cluster, node_summarize, node_transform)
        },
        edges={
            e.id: e
            for e in (
                edge_load_scale,
                edge_scale_cluster,
                edge_cluster_summarize,
                edge_scale_transform,
                edge_load_transform_frame,
            )
        },
    )


# ---------------------------------------------------------------------------
# Fixture helpers: write JSON to examples/sklearn_acceptance_demo/
# ---------------------------------------------------------------------------


def write_pipeline(graph: Graph, filename: str) -> pathlib.Path:
    """Dump *graph* as pretty JSON to examples/sklearn_acceptance_demo/<filename>."""
    DEMO_DIR.mkdir(exist_ok=True)
    path = DEMO_DIR / filename
    path.write_text(graph.model_dump_json(indent=2), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Drift guards: committed JSON must match what the builders generate. These run BEFORE the
# fixture classes below (pytest runs top-to-bottom in file-definition order), so they read the
# committed file before the autouse fixtures regenerate it.
# ---------------------------------------------------------------------------


def test_committed_supervised_json_is_current() -> None:
    committed = Graph.model_validate_json(
        (DEMO_DIR / "supervised_pipeline.json").read_text(encoding="utf-8")
    )
    assert committed == build_supervised_demo(), (
        "examples/sklearn_acceptance_demo/supervised_pipeline.json is stale; run "
        "'pytest tests/test_sklearn_acceptance_demo.py::TestSupervisedDemo' to regenerate it"
    )


def test_committed_unsupervised_json_is_current() -> None:
    committed = Graph.model_validate_json(
        (DEMO_DIR / "unsupervised_pipeline.json").read_text(encoding="utf-8")
    )
    assert committed == build_unsupervised_demo(), (
        "examples/sklearn_acceptance_demo/unsupervised_pipeline.json is stale; run "
        "'pytest tests/test_sklearn_acceptance_demo.py::TestUnsupervisedDemo' to regenerate it"
    )


# ---------------------------------------------------------------------------
# Tests (a): supervised demo
# ---------------------------------------------------------------------------


class TestSupervisedDemo:
    @pytest.fixture(autouse=True)
    def write_json(self) -> None:
        write_pipeline(build_supervised_demo(), "supervised_pipeline.json")

    def test_loads_and_validates(self) -> None:
        raw = (DEMO_DIR / "supervised_pipeline.json").read_text(encoding="utf-8")
        Graph.model_validate_json(raw)

    def test_node_and_edge_counts(self) -> None:
        graph = build_supervised_demo()
        assert len(graph.nodes) == 4
        assert len(graph.edges) == 4

    def test_node_types(self) -> None:
        graph = build_supervised_demo()
        node_types = {node.type for node in graph.nodes.values()}
        assert node_types == {
            "data.load_sample",
            "clean.drop_missing",
            "ml.pipeline",
            "ml.evaluate",
        }

    @pytest.mark.equivalence
    def test_equivalence(self) -> None:
        """ADR-0002: execute() == running the emitted code for the full supervised demo."""
        assert_equivalent(build_supervised_demo())


# ---------------------------------------------------------------------------
# Tests (b): unsupervised demo
# ---------------------------------------------------------------------------


class TestUnsupervisedDemo:
    @pytest.fixture(autouse=True)
    def write_json(self) -> None:
        write_pipeline(build_unsupervised_demo(), "unsupervised_pipeline.json")

    def test_loads_and_validates(self) -> None:
        raw = (DEMO_DIR / "unsupervised_pipeline.json").read_text(encoding="utf-8")
        Graph.model_validate_json(raw)

    def test_node_and_edge_counts(self) -> None:
        graph = build_unsupervised_demo()
        assert len(graph.nodes) == 5
        assert len(graph.edges) == 5

    def test_node_types(self) -> None:
        graph = build_unsupervised_demo()
        node_types = {node.type for node in graph.nodes.values()}
        assert node_types == {
            "data.load_sample",
            "ml.fit_transform",
            "ml.cluster_detect",
            "ml.summarize",
            "ml.transform",
        }

    def test_has_transformer_edge(self) -> None:
        graph = build_unsupervised_demo()
        scale_node = graph.nodes["n-scale"]
        transformer_port = next(p for p in scale_node.ports if p.id == "p-scale-transformer")
        assert transformer_port.data_type == "Transformer"
        edge = next(
            (
                e
                for e in graph.edges.values()
                if e.source.node_id == "n-scale"
                and e.source.port_id == "p-scale-transformer"
                and e.target.node_id == "n-transform"
            ),
            None,
        )
        assert edge is not None

    @pytest.mark.equivalence
    def test_equivalence(self) -> None:
        """ADR-0002: execute() == running the emitted code for the full unsupervised demo."""
        assert_equivalent(build_unsupervised_demo())
