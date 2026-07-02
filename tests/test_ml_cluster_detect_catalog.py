"""
Golden + equivalence tests for the Epic 8 Story 6 cluster_detect estimator catalog.

Three things this file proves, per Story 6's own checklist and the Story 9 harness pattern:

1. Golden-code quality: for a representative estimator per family, the whole-graph
   ``compile_to_code`` output (LoadSample -> ClusterDetect) is syntactically valid Python and
   passes ``ruff check`` (mirrors ``tests/test_ml_supervised_catalog.py``'s idiom).
2. ADR-0002 equivalence at scale: for EVERY estimator registered with archetype="cluster_detect"
   (the entire clustering/mixture/outlier allow-list, computed dynamically so this test grows
   automatically as the allow-list widens), ``execute()`` and running the code ``codegen()``
   emits produce the same fitted-model metadata and the same "cluster" column.
3. The labels_-only estimators (DBSCAN, AgglomerativeClustering, SpectralClustering) correctly
   produce labels via ``ml.cluster_detect`` (same-frame fit+label), but correctly REJECT --
   rather than silently misbehave -- when a later ``ml.apply_estimator`` "predict" call is made
   against a DIFFERENT frame, since sklearn gives those estimators no reusable predictor.

Test data note: naive small/ambiguous datasets can make clustering algorithms (esp. KMeans-
family) genuinely nondeterministic run-to-run even with a fixed ``random_state`` -- ties near a
decision boundary can flip on floating-point/thread-scheduling noise. All fixtures here use
well-separated blobs specifically to avoid that trap (verified by construction, not by luck).
"""

from __future__ import annotations

import ast
import subprocess
import sys

import pandas as pd
import pytest

from emergentflow.codegen.compiler import compile_to_code
from emergentflow.ir.common import Direction
from emergentflow.ir.edge import Edge, PortRef
from emergentflow.ir.graph import Graph
from emergentflow.ml.registry import get_estimator_spec, known_estimator_keys
from emergentflow.nodes.examples import ApplyEstimator, ClusterDetect, LoadSample


def _out_port(node, name):
    return next(p for p in node.ports if p.direction == Direction.OUT and p.name == name)


def _in_port(node, name):
    return next(p for p in node.ports if p.direction == Direction.IN and p.name == name)


def _cluster_detect_archetype_keys() -> list[str]:
    return sorted(
        k for k in known_estimator_keys() if get_estimator_spec(k).archetype == "cluster_detect"
    )


def _run_codegen(definition, node, scope):
    """exec a node's preview fragment in *scope* and return the updated scope."""
    frag = definition.preview(node)
    exec(frag.render(), scope)  # noqa: S102 -- test-only, on our own emitted code
    return scope


IRIS_FEATURES = [
    "sepal length (cm)",
    "sepal width (cm)",
    "petal length (cm)",
    "petal width (cm)",
]


def _blob_df() -> pd.DataFrame:
    """30 rows: two well-separated 15-point blobs (near (0,0) and near (100,100)).

    Deliberately far apart (a 100-unit gap vs. ~1-unit intra-blob spacing) so every curated
    cluster_detect estimator converges to the SAME partition regardless of run-to-run
    floating-point/threading tie-breaking noise -- verified directly: naive nearby-point data
    made raw ``KMeans(random_state=0, n_init=5).fit(X)`` alone flip between two different
    partitions across repeated calls in the same process.
    """
    n_per = 15
    x1 = [float(i) for i in range(n_per)] + [float(i) + 100.0 for i in range(n_per)]
    x2 = [float(i) for i in range(n_per)] + [float(i) + 100.0 for i in range(n_per)]
    return pd.DataFrame({"x1": x1, "x2": x2})


_FEATURES = ["x1", "x2"]

#: Per-key param overrides so every curated cluster_detect estimator fits this 30-row,
#: 2-blob dataset sensibly (e.g. matching n_clusters/n_components to the actual 2 blobs;
#: DBSCAN's curated default eps=0.5 is far too tight for this data's ~1.4-unit intra-blob
#: spacing; LocalOutlierFactor's curated default n_neighbors=20 exceeds this dataset's size).
#: The catalog's own curated defaults (used by real graphs) are untouched -- these overrides
#: only apply to this test's synthetic sample.
_KEY_OVERRIDES: dict[str, dict] = {
    "KMeans": {"n_clusters": 2, "n_init": 5},
    "MiniBatchKMeans": {"n_clusters": 2, "batch_size": 10},
    "DBSCAN": {"eps": 5.0, "min_samples": 2},
    "AgglomerativeClustering": {"n_clusters": 2},
    "SpectralClustering": {"n_clusters": 2},
    "Birch": {"n_clusters": 2, "threshold": 0.5},
    "GaussianMixture": {"n_components": 2},
    "BayesianGaussianMixture": {"n_components": 2},
    "LocalOutlierFactor": {"n_neighbors": 5},
}


def _params_for(estimator_key: str) -> dict:
    return _KEY_OVERRIDES.get(estimator_key, {})


# ---------------------------------------------------------------------------
# 1. Golden-code quality: one representative estimator per family.
# ---------------------------------------------------------------------------

_REPRESENTATIVE_ESTIMATORS = [
    "KMeans",  # clustering (seed)
    "GaussianMixture",  # mixture (seed)
    "IsolationForest",  # outlier/novelty
]


def _build_cluster_detect_graph(estimator_key: str) -> Graph:
    params = {"n_clusters": 3} if estimator_key == "KMeans" else {}
    if estimator_key == "GaussianMixture":
        params = {"n_components": 3}
    load = LoadSample().instantiate(name="iris", label="Load Sample")
    node = ClusterDetect().instantiate(
        estimator=estimator_key, features=IRIS_FEATURES, params=params, label="Cluster Detect"
    )
    edge = Edge(
        source=PortRef(node_id=load.id, port_id=_out_port(load, "frame").id),
        target=PortRef(node_id=node.id, port_id=_in_port(node, "frame").id),
    )
    return Graph(nodes={load.id: load, node.id: node}, edges={edge.id: edge})


@pytest.mark.parametrize("estimator_key", _REPRESENTATIVE_ESTIMATORS)
def test_cluster_detect_catalog_codegen_is_parseable(estimator_key: str) -> None:
    """Generated code for a representative cluster_detect estimator parses (importable)."""
    code = compile_to_code(_build_cluster_detect_graph(estimator_key))
    ast.parse(code)  # raises SyntaxError on failure


@pytest.mark.parametrize("estimator_key", _REPRESENTATIVE_ESTIMATORS)
def test_cluster_detect_catalog_codegen_is_ruff_clean(estimator_key: str) -> None:
    """Generated code for a representative cluster_detect estimator passes ``ruff check``."""
    code = compile_to_code(_build_cluster_detect_graph(estimator_key))
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "-"],
        input=code,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# 2. ADR-0002 equivalence matrix: every "cluster_detect"-archetype estimator in the allow-list.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("estimator_key", _cluster_detect_archetype_keys())
def test_cluster_detect_equivalence_matrix(estimator_key: str) -> None:
    """ADR 0002: execute == running the emitted code, for every cluster_detect estimator."""
    params = _params_for(estimator_key)
    df = _blob_df()

    defn = ClusterDetect()
    node = defn.instantiate(estimator=estimator_key, features=_FEATURES, params=params)
    executed = defn.execute(node, inputs={"frame": df.copy()})
    executed_model, executed_result = executed["model"], executed["result"]

    scope = _run_codegen(defn, node, {"frame": df.copy()})
    codegen_model, codegen_result = scope["model"], scope["result"]

    assert executed_model.estimator_type == codegen_model.estimator_type
    assert executed_model.task == codegen_model.task
    assert executed_model.feature_names == codegen_model.feature_names
    assert "cluster" in executed_result.columns
    assert executed_result["cluster"].tolist() == codegen_result["cluster"].tolist()


# ---------------------------------------------------------------------------
# 3. labels_-only estimators: same-frame labeling works, cross-frame predict is rejected.
# ---------------------------------------------------------------------------

_LABELS_ONLY_ESTIMATORS = ["DBSCAN", "AgglomerativeClustering", "SpectralClustering"]


@pytest.mark.parametrize("estimator_key", _LABELS_ONLY_ESTIMATORS)
def test_labels_only_estimator_labels_the_fit_frame(estimator_key: str) -> None:
    """A labels_-only estimator (no sklearn .predict) still produces a 'cluster' column via
    ml.cluster_detect, since that node labels the SAME frame it fits on using .labels_."""
    df = _blob_df()
    params = _params_for(estimator_key)
    defn = ClusterDetect()
    node = defn.instantiate(estimator=estimator_key, features=_FEATURES, params=params)
    out = defn.execute(node, inputs={"frame": df})
    assert "cluster" in out["result"].columns
    assert not hasattr(out["model"].estimator, "predict")


@pytest.mark.parametrize("estimator_key", _LABELS_ONLY_ESTIMATORS)
def test_labels_only_estimator_rejects_predict_on_new_data(estimator_key: str) -> None:
    """ml.apply_estimator must REJECT predicting a labels_-only model's on a DIFFERENT frame
    (not silently replay stale training-time labels) -- the archetype's "disabled, not a
    runtime surprise" requirement for estimators with no reusable predictor."""
    df = _blob_df()
    params = _params_for(estimator_key)
    fit_defn = ClusterDetect()
    fit_node = fit_defn.instantiate(estimator=estimator_key, features=_FEATURES, params=params)
    fitted = fit_defn.execute(fit_node, inputs={"frame": df})
    model = fitted["model"]

    new_df = df.copy()
    apply_defn = ApplyEstimator()
    apply_node = apply_defn.instantiate(op="predict")
    with pytest.raises(ValueError, match="does not support predict"):
        apply_defn.execute(apply_node, inputs={"model": model, "frame": new_df})
