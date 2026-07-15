"""
tests/test_recommend_acceptance_demo.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Builds the Epic 15 Story 15 acceptance-demo IR graph -- a content-based recommender pipeline
(``load_sample -> prepare_interactions -> popularity baseline -> TF-IDF content-based ->
evaluate both -> comparison bar chart``) -- writes it to
examples/recommender_acceptance_demo/, re-loads and validates it, and proves ADR-0002
equivalence end to end.

Mirrors tests/test_sklearn_acceptance_demo.py's builder/fixture/drift-guard pattern (module
docstring, ``write_pipeline`` helper, drift guard before the fixture class) and reuses its
whole-graph ``assert_equivalent`` harness from tests/test_codegen_equivalence.py. Node
construction uses this epic's ``SomeNodeDefinition().instantiate(**kwargs)`` idiom (see
tests/test_recommend_viz_golden.py's ``_out_port``/``_in_port``/``_edge`` helpers) rather than
the sklearn demo's raw ``Node()`` construction, since it is more robust for nodes with many
ports/params.

``data.load_sample``'s bundled datasets (iris/wine/diabetes) are all-numeric with no free-text
column, so a ``script.custom_code`` node sits between ``load_sample`` and the TF-IDF fitter's
``item_features`` port: it deduplicates iris rows by the item column (``groupby(...).mean()``,
mirroring how tests/test_recommend_golden_generated_code.py -- Story 13.8 -- solved the same
"raw iris has duplicate values in every column" problem for ``tfidf_similarity``'s
``item_id_col`` uniqueness requirement) and synthesizes a short "description" text column from
the (now-unique, averaged) ``target`` class value, giving TF-IDF real per-item text to
vectorize.
"""

from __future__ import annotations

import pathlib

import pytest

from emergentflow.ir.common import Direction
from emergentflow.ir.edge import Edge, PortRef
from emergentflow.ir.graph import Graph
from emergentflow.ir.node import Node
from emergentflow.nodes.examples import (
    CustomCode,
    LoadSample,
    PrepareInteractions,
    RecommendCompare,
    RecommendFit,
    RecommendTemporalSplit,
)
from emergentflow.nodes.examples.recommend_evaluate import RecommendEvaluate
from emergentflow.nodes.examples.recommend_recommend import Recommend
from emergentflow.nodes.examples.viz_plot_metric_comparison import VizPlotMetricComparison
from emergentflow.nodes.examples.viz_plot_precision_recall_curve import (
    VizPlotPrecisionRecallCurve,
)
from tests.test_codegen_equivalence import assert_equivalent

REPO_ROOT = pathlib.Path(__file__).parent.parent
EXAMPLES_DIR = REPO_ROOT / "examples"
DEMO_DIR = EXAMPLES_DIR / "recommender_acceptance_demo"

_ITEM_FEATURES_CODE = """\
def transform(value):
    grouped = value.groupby("sepal width (cm)", as_index=False)[["target"]].mean()
    grouped["description"] = (
        grouped["target"]
        .round()
        .astype(int)
        .map({0: "small delicate petals", 1: "medium balanced petals", 2: "large showy petals"})
    )
    return grouped[["sepal width (cm)", "description"]]
"""

_TIMESTAMP_CODE = """\
def transform(value):
    value = value.reset_index(drop=True).copy()
    value["timestamp"] = value.index
    return value
"""


def _out_port(node, name):
    return next(p for p in node.ports if p.direction == Direction.OUT and p.name == name)


def _in_port(node, name):
    return next(p for p in node.ports if p.direction == Direction.IN and p.name == name)


def _edge(source_node, source_port, target_node, target_port) -> Edge:
    return Edge(
        source=PortRef(node_id=source_node.id, port_id=_out_port(source_node, source_port).id),
        target=PortRef(node_id=target_node.id, port_id=_in_port(target_node, target_port).id),
    )


def _freeze_ids(node: Node, node_id: str) -> Node:
    """``instantiate()`` mints a fresh random uuid for ``node.id`` and every ``port.id`` on
    every call (see ``NodeDefinition.instantiate``) -- fine for a graph built and used once,
    but it means two independent calls to ``build_content_based_demo()`` are never equal to
    each other, which breaks the drift-guard test below (it compares a freshly-built graph
    against the one loaded from the committed JSON). Overwrite the minted ids with
    deterministic ones derived from *node_id* so the builder is reproducible across calls,
    while still getting the correct ports/params for free from the declared ``PortSpec``/
    ``ParamSpec`` lists via ``instantiate()``."""
    node.id = node_id
    for port in node.ports:
        port.id = f"{node_id}::{port.name}"
    return node


# ---------------------------------------------------------------------------
# Builder: load_sample -> prepare_interactions -> {fit_pop, fit_tfidf} -> compare ->
# plot_metric_comparison, plus a custom_code node synthesizing TF-IDF's item_features.
# ---------------------------------------------------------------------------


def build_content_based_demo() -> Graph:
    """load_sample(iris) -> prepare_interactions -> popularity baseline + TF-IDF
    content-based recommenders -> recommend.compare -> viz.plot_metric_comparison.

    A custom_code node dedupes the raw iris frame by item column and synthesizes a
    "description" text column (see module docstring) so tfidf_similarity has real
    per-item text to vectorize."""
    load = _freeze_ids(LoadSample().instantiate(name="iris", label="Load Sample"), "n-load")
    item_features = _freeze_ids(
        CustomCode().instantiate(code=_ITEM_FEATURES_CODE, label="Item Features"),
        "n-item-features",
    )
    prepare = _freeze_ids(
        PrepareInteractions().instantiate(
            label="Prepare Interactions",
            user_col="sepal length (cm)",
            item_col="sepal width (cm)",
        ),
        "n-prepare",
    )
    fit_pop = _freeze_ids(
        RecommendFit().instantiate(label="Fit Popularity", algorithm="popularity", params={}),
        "n-fit-pop",
    )
    fit_tfidf = _freeze_ids(
        RecommendFit().instantiate(
            label="Fit TF-IDF",
            algorithm="tfidf_similarity",
            params={"item_id_col": "sepal width (cm)", "text_col": "description"},
        ),
        "n-fit-tfidf",
    )
    compare = _freeze_ids(RecommendCompare().instantiate(label="Compare", k=5), "n-compare")
    metric_bar = _freeze_ids(
        VizPlotMetricComparison().instantiate(label="Metric Comparison"), "n-metric-bar"
    )

    nodes = {
        n.id: n for n in (load, item_features, prepare, fit_pop, fit_tfidf, compare, metric_bar)
    }
    edges = [
        _edge(load, "frame", prepare, "frame"),
        _edge(load, "frame", item_features, "value"),
        _edge(prepare, "interactions", fit_pop, "interactions"),
        _edge(prepare, "interactions", fit_tfidf, "interactions"),
        _edge(item_features, "result", fit_tfidf, "item_features"),
        _edge(fit_pop, "recommender", compare, "recommenders"),
        _edge(fit_tfidf, "recommender", compare, "recommenders"),
        _edge(prepare, "interactions", compare, "test_interactions"),
        _edge(compare, "result", metric_bar, "comparison"),
    ]
    # Edge ids are also randomly minted (Edge.id: Field(default_factory=new_id)); freeze them
    # to their fixed position in this deterministically-ordered list for the same reason
    # _freeze_ids exists above.
    for index, edge in enumerate(edges):
        edge.id = f"e-{index}"

    return Graph(
        name="Recommender Acceptance Demo -- Content-Based",
        nodes=nodes,
        edges={e.id: e for e in edges},
    )


# ---------------------------------------------------------------------------
# Fixture helper: write JSON to examples/recommender_acceptance_demo/
# ---------------------------------------------------------------------------


def write_pipeline(graph: Graph, filename: str) -> pathlib.Path:
    """Dump *graph* as pretty JSON to examples/recommender_acceptance_demo/<filename>."""
    DEMO_DIR.mkdir(exist_ok=True)
    path = DEMO_DIR / filename
    path.write_text(graph.model_dump_json(indent=2), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Drift guard: committed JSON must match what the builder generates. This runs BEFORE the
# fixture class below (pytest runs top-to-bottom in file-definition order), so it reads the
# committed file before the autouse fixture regenerates it.
# ---------------------------------------------------------------------------


def test_committed_content_based_json_is_current() -> None:
    committed = Graph.model_validate_json(
        (DEMO_DIR / "content_based_pipeline.json").read_text(encoding="utf-8")
    )
    assert committed == build_content_based_demo(), (
        "examples/recommender_acceptance_demo/content_based_pipeline.json is stale; run "
        "'pytest tests/test_recommend_acceptance_demo.py::TestContentBasedDemo' to regenerate it"
    )


# ---------------------------------------------------------------------------
# Tests: content-based demo
# ---------------------------------------------------------------------------


class TestContentBasedDemo:
    @pytest.fixture(autouse=True)
    def write_json(self) -> None:
        write_pipeline(build_content_based_demo(), "content_based_pipeline.json")

    def test_loads_and_validates(self) -> None:
        raw = (DEMO_DIR / "content_based_pipeline.json").read_text(encoding="utf-8")
        Graph.model_validate_json(raw)

    def test_node_and_edge_counts(self) -> None:
        graph = build_content_based_demo()
        assert len(graph.nodes) == 7
        assert len(graph.edges) == 9

    def test_node_types(self) -> None:
        graph = build_content_based_demo()
        node_types = {node.type for node in graph.nodes.values()}
        assert node_types == {
            "data.load_sample",
            "script.custom_code",
            "recommend.prepare_interactions",
            "recommend.fit",
            "recommend.compare",
            "viz.plot_metric_comparison",
        }

    @pytest.mark.equivalence
    def test_equivalence(self) -> None:
        """ADR-0002: execute() == running the emitted code for the full content-based demo."""
        assert_equivalent(build_content_based_demo())


# ---------------------------------------------------------------------------
# Builder: load_sample -> custom_code (synthesize timestamp) -> temporal_split ->
# {user-KNN CF, SVD CF} -> {evaluate, evaluate} + recommend + plot_precision_recall_curve.
# ---------------------------------------------------------------------------


def build_collaborative_demo() -> Graph:
    """load_sample(iris) -> custom_code (synthesize a timestamp column) ->
    recommend.temporal_split -> user-KNN CF + SVD CF collaborative filters, each evaluated
    against the held-out test split -- plus a top-N recommendation list from the KNN model
    and a precision-recall curve swept over the SVD model.

    ``load_sample``'s bundled datasets have no timestamp column, so a custom_code node
    synthesizes one from the row index (see module docstring / ``_TIMESTAMP_CODE``) before
    ``recommend.temporal_split`` can order each user's interactions by recency."""
    load = _freeze_ids(LoadSample().instantiate(name="iris", label="Load Sample"), "n-cf-load")
    add_timestamp = _freeze_ids(
        CustomCode().instantiate(code=_TIMESTAMP_CODE, label="Add Timestamp"),
        "n-cf-add-timestamp",
    )
    split = _freeze_ids(
        RecommendTemporalSplit().instantiate(
            label="Temporal Split",
            user_col="sepal length (cm)",
            item_col="sepal width (cm)",
            timestamp_col="timestamp",
            test_ratio=0.2,
        ),
        "n-cf-split",
    )
    fit_knn = _freeze_ids(
        RecommendFit().instantiate(
            label="Fit User-KNN CF", algorithm="user_knn_cf", params={"k": 2}
        ),
        "n-cf-fit-knn",
    )
    fit_svd = _freeze_ids(
        RecommendFit().instantiate(
            label="Fit SVD CF",
            algorithm="svd_cf",
            params={"n_components": 2, "seed": 0},
        ),
        "n-cf-fit-svd",
    )
    eval_knn = _freeze_ids(
        RecommendEvaluate().instantiate(label="Evaluate User-KNN CF", k=5), "n-cf-eval-knn"
    )
    eval_svd = _freeze_ids(
        RecommendEvaluate().instantiate(label="Evaluate SVD CF", k=5), "n-cf-eval-svd"
    )
    recommend_list = _freeze_ids(
        Recommend().instantiate(label="Recommendation List", n=5), "n-cf-recommend-list"
    )
    pr_curve = _freeze_ids(
        VizPlotPrecisionRecallCurve().instantiate(label="Precision-Recall Curve", k_max=5),
        "n-cf-pr-curve",
    )

    nodes = {
        n.id: n
        for n in (
            load,
            add_timestamp,
            split,
            fit_knn,
            fit_svd,
            eval_knn,
            eval_svd,
            recommend_list,
            pr_curve,
        )
    }
    edges = [
        _edge(load, "frame", add_timestamp, "value"),
        _edge(add_timestamp, "result", split, "frame"),
        _edge(split, "train", fit_knn, "interactions"),
        _edge(split, "train", fit_svd, "interactions"),
        _edge(split, "test", eval_knn, "test_interactions"),
        _edge(fit_knn, "recommender", eval_knn, "recommender"),
        _edge(split, "test", eval_svd, "test_interactions"),
        _edge(fit_svd, "recommender", eval_svd, "recommender"),
        _edge(fit_knn, "recommender", recommend_list, "recommender"),
        _edge(fit_svd, "recommender", pr_curve, "recommender"),
        _edge(split, "test", pr_curve, "test_interactions"),
    ]
    # Edge ids are also randomly minted (Edge.id: Field(default_factory=new_id)); freeze them
    # to their fixed position in this deterministically-ordered list for the same reason
    # _freeze_ids exists above.
    for index, edge in enumerate(edges):
        edge.id = f"e-cf-{index}"

    return Graph(
        name="Recommender Acceptance Demo -- Collaborative Filtering",
        nodes=nodes,
        edges={e.id: e for e in edges},
    )


# ---------------------------------------------------------------------------
# Drift guard: committed JSON must match what the builder generates. This runs BEFORE the
# fixture class below (pytest runs top-to-bottom in file-definition order), so it reads the
# committed file before the autouse fixture regenerates it.
# ---------------------------------------------------------------------------


def test_committed_collaborative_json_is_current() -> None:
    committed = Graph.model_validate_json(
        (DEMO_DIR / "collaborative_pipeline.json").read_text(encoding="utf-8")
    )
    assert committed == build_collaborative_demo(), (
        "examples/recommender_acceptance_demo/collaborative_pipeline.json is stale; run "
        "'pytest tests/test_recommend_acceptance_demo.py::TestCollaborativeDemo' to regenerate it"
    )


# ---------------------------------------------------------------------------
# Tests: collaborative-filtering demo
# ---------------------------------------------------------------------------


class TestCollaborativeDemo:
    @pytest.fixture(autouse=True)
    def write_json(self) -> None:
        write_pipeline(build_collaborative_demo(), "collaborative_pipeline.json")

    def test_loads_and_validates(self) -> None:
        raw = (DEMO_DIR / "collaborative_pipeline.json").read_text(encoding="utf-8")
        Graph.model_validate_json(raw)

    def test_node_and_edge_counts(self) -> None:
        graph = build_collaborative_demo()
        assert len(graph.nodes) == 9
        assert len(graph.edges) == 11

    def test_node_types(self) -> None:
        graph = build_collaborative_demo()
        node_types = {node.type for node in graph.nodes.values()}
        assert node_types == {
            "data.load_sample",
            "script.custom_code",
            "recommend.temporal_split",
            "recommend.fit",
            "recommend.evaluate",
            "recommend.recommend",
            "viz.plot_precision_recall_curve",
        }

    @pytest.mark.equivalence
    def test_equivalence(self) -> None:
        """ADR-0002: execute() == running the emitted code for the full collaborative demo."""
        assert_equivalent(build_collaborative_demo())
