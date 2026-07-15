"""
Epic 15 Story 13 -- golden tests on GENERATED CODE (not execute()/codegen-fragment equivalence,
which tests/test_recommend_equivalence_matrix.py already covers) for one representative,
real, hand-wired Graph per recommend-family archetype (baseline/content/collaborative/deep):
readable (ruff-format output, verified via ruff-clean), ruff-clean, and importable (the compiled
module loads without error and its main() actually runs end-to-end). Mirrors the existing
tests/test_recommend_interactions.py golden-graph pattern, extended one step further (fit ->
recommend) and to one graph per family rather than just prepare_interactions.
"""

from __future__ import annotations

import ast
import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from emergentflow.codegen.compiler import compile_to_code
from emergentflow.ir.common import Direction
from emergentflow.ir.edge import Edge, PortRef
from emergentflow.ir.graph import Graph
from emergentflow.nodes.examples import (
    CustomCode,
    LoadSample,
    PrepareInteractions,
    Recommend,
    RecommendFit,
)

_ITEM_FEATURES_DEDUP_CODE = """\
def transform(value):
    return value.groupby("sepal width (cm)", as_index=False).mean()
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


def _build_fit_recommend_graph(
    *, algorithm: str, params: dict, with_item_features: bool = False
) -> Graph:
    """load_sample(iris) -> prepare_interactions -> recommend.fit(algorithm) -> recommend.recommend.

    When *with_item_features* is True, the SAME load_sample output also fans out into
    RecommendFit's optional item_features port (ordinary DAG branching, not Cardinality.MANY).

    For content-family algorithms (feature_knn) the item_features port needs unique
    item IDs, which the raw iris dataset cannot provide.  Use
    ``content_item_features`` instead to insert a CustomCode deduplication step.
    """
    load = LoadSample().instantiate(name="iris", label="Load Sample")
    prepare = PrepareInteractions().instantiate(
        label="Prepare Interactions",
        user_col="sepal length (cm)",
        item_col="sepal width (cm)",
    )
    fit = RecommendFit().instantiate(label="Fit Recommender", algorithm=algorithm, params=params)
    recommend = Recommend().instantiate(label="Recommend", n=5)

    nodes = {n.id: n for n in (load, prepare, fit, recommend)}
    edges = [
        _edge(load, "frame", prepare, "frame"),
        _edge(prepare, "interactions", fit, "interactions"),
        _edge(fit, "recommender", recommend, "recommender"),
    ]
    if with_item_features:
        edges.append(_edge(load, "frame", fit, "item_features"))
    return Graph(nodes=nodes, edges={e.id: e for e in edges})


def _build_content_fit_recommend_graph(*, algorithm: str, params: dict) -> Graph:
    """Like _build_fit_recommend_graph but inserts a CustomCode node that
    deduplicates the item_features DataFrame so content-family fitters
    (feature_knn) receive unique item IDs -- required by _align_item_features.

    load_sample(iris) -> prepare_interactions -> recommend.fit(algorithm) -> recommend.recommend
                     |> custom_code (groupby+mean dedup) -> recommend.fit.item_features
    """
    load = LoadSample().instantiate(name="iris", label="Load Sample")
    prepare = PrepareInteractions().instantiate(
        label="Prepare Interactions",
        user_col="sepal length (cm)",
        item_col="sepal width (cm)",
    )
    dedup = CustomCode().instantiate(
        label="Deduplicate Item Features",
        code=_ITEM_FEATURES_DEDUP_CODE,
    )
    fit = RecommendFit().instantiate(label="Fit Recommender", algorithm=algorithm, params=params)
    recommend = Recommend().instantiate(label="Recommend", n=5)

    nodes = {n.id: n for n in (load, prepare, dedup, fit, recommend)}
    edges = [
        _edge(load, "frame", prepare, "frame"),
        _edge(load, "frame", dedup, "value"),
        _edge(dedup, "result", fit, "item_features"),
        _edge(prepare, "interactions", fit, "interactions"),
        _edge(fit, "recommender", recommend, "recommender"),
    ]
    return Graph(nodes=nodes, edges={e.id: e for e in edges})


def _assert_ruff_clean(code: str) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "-"],
        input=code,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _assert_importable_and_runs(code: str) -> None:
    """Write the compiled module to a temp .py file, import it, and call its main() -- proves
    the generated code is not just syntactically valid but actually runs end-to-end."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        module_path = Path(tmp_dir) / "generated_module.py"
        module_path.write_text(code, encoding="utf-8")
        spec = importlib.util.spec_from_file_location("generated_module", module_path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # import-time execution only (module-level code)
        results = module.main()
        assert isinstance(results, dict)
        assert results  # at least one output var


# ---------------------------------------------------------------------------
# One representative graph per family
# ---------------------------------------------------------------------------


def _baseline_graph() -> Graph:
    return _build_fit_recommend_graph(algorithm="popularity", params={})


def _content_graph() -> Graph:
    return _build_content_fit_recommend_graph(
        algorithm="feature_knn",
        params={
            "item_id_col": "sepal width (cm)",
            "feature_cols": ["petal length (cm)", "petal width (cm)"],
            "algorithm": "brute",
        },
    )


def _collaborative_graph() -> Graph:
    return _build_fit_recommend_graph(algorithm="user_knn_cf", params={"k": 2})


def _deep_graph() -> Graph:
    return _build_fit_recommend_graph(
        algorithm="ncf",
        params={
            "embedding_dim": 4,
            "mlp_layers": [4],
            "epochs": 1,
            "batch_size": 8,
            "seed": 0,
        },
    )


@pytest.mark.parametrize(
    "build_graph",
    [_baseline_graph, _content_graph, _collaborative_graph],
    ids=["baseline", "content", "collaborative"],
)
def test_recommend_golden_generated_code(build_graph) -> None:
    code = compile_to_code(build_graph())
    ast.parse(code)
    _assert_ruff_clean(code)
    _assert_importable_and_runs(code)


def test_recommend_golden_generated_code_deep() -> None:
    """Separate test (not folded into the parametrize above) so it can importorskip torch."""
    pytest.importorskip("torch")
    code = compile_to_code(_deep_graph())
    ast.parse(code)
    _assert_ruff_clean(code)
    _assert_importable_and_runs(code)
