"""
Epic 8 Story 9 -- cross-archetype ADR-0002 equivalence matrix, keyed on the inspectable
summary (``ef.ml.summarize``) rather than ad hoc per-field comparisons.

Stories 4/5/6 each shipped their own scoped equivalence test (one per archetype, comparing raw
predict()/transform() arrays and specific FittedModel/FittedTransformer attributes -- see
tests/test_ml_supervised_catalog.py, tests/test_ml_fit_transform_catalog.py,
tests/test_ml_cluster_detect_catalog.py). This file is the Story 9 harness proper: ONE matrix
over every registered estimator across all three catalog archetypes (fit, fit_transform,
cluster_detect), asserting ``execute(ir)`` and running ``compile_to_code(ir)`` on a fixed sample
frame produce the SAME structural summary via ``ef.ml.summarize()`` -- so opaque estimator
internals are never compared directly, only the same JSON-native surface the result-payload
contract exposes.

Fixed seeds + fixed sample datasets (module-level constants below) make the matrix
deterministic, mirroring the per-archetype files' own fixtures.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd
import pytest

from emergentflow.ml import summarize
from emergentflow.ml.registry import get_estimator_spec, keys_for_archetype
from emergentflow.nodes.examples import ClusterDetect, FitEstimator, FitTransform


def _run_codegen(definition, node, scope):
    """exec a node's preview fragment in *scope* and return the updated scope."""
    frag = definition.preview(node)
    exec(frag.render(), scope)  # noqa: S102 -- test-only, on our own emitted code
    return scope


def _assert_summaries_equivalent(a: Any, b: Any, path: str = "summary") -> None:
    """Deep, float-tolerant equality between two ``ef.ml.summarize()`` outputs.

    Two independent fits of the SAME estimator/kwargs/data can produce bit-different floats
    (e.g. ``inertia``) purely from floating-point summation-order noise, even though the
    underlying cluster assignment is identical -- an exact ``==`` on the summary dicts is too
    strict and flakes in practice (observed with ``MiniBatchKMeans``). Mirrors the tolerant
    comparison ``tests/test_codegen_equivalence.py`` already uses for the same reason.
    """
    if isinstance(a, dict):
        assert isinstance(b, dict), f"type mismatch at {path}: dict vs {type(b).__name__}"
        assert a.keys() == b.keys(), f"key mismatch at {path}: {sorted(a)} vs {sorted(b)}"
        for key in a:
            _assert_summaries_equivalent(a[key], b[key], f"{path}.{key}")
    elif isinstance(a, list):
        assert isinstance(b, list), f"type mismatch at {path}: list vs {type(b).__name__}"
        assert len(a) == len(b), f"length mismatch at {path}"
        for i, (av, bv) in enumerate(zip(a, b, strict=True)):
            _assert_summaries_equivalent(av, bv, f"{path}[{i}]")
    elif isinstance(a, bool) or isinstance(b, bool):
        assert type(a) is type(b) and a == b, f"bool mismatch at {path}: {a!r} != {b!r}"
    elif isinstance(a, (int, float)) or isinstance(b, (int, float)):
        assert isinstance(a, (int, float)) and isinstance(b, (int, float)), (
            f"numeric/type mismatch at {path}: {a!r} != {b!r}"
        )
        assert math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-9), (
            f"float mismatch at {path}: {a!r} != {b!r}"
        )
    else:
        assert a == b, f"mismatch at {path}: {a!r} != {b!r}"


# ---------------------------------------------------------------------------
# Fixed sample datasets (mirrors the per-archetype story test files' own fixtures).
# ---------------------------------------------------------------------------


def _classification_df() -> pd.DataFrame:
    x1 = [float(i) for i in range(20)] + [float(i) for i in range(20)]
    x2 = [float(i % 5) for i in range(40)]
    label = ["low" if i % 2 == 0 else "high" for i in range(40)]
    return pd.DataFrame({"x1": x1, "x2": x2, "label": label})


def _regression_df() -> pd.DataFrame:
    x1 = [float(i) for i in range(30)]
    x2 = [float(i % 5) for i in range(30)]
    y = [2 * a + 3 * b + 1.0 for a, b in zip(x1, x2, strict=True)]
    return pd.DataFrame({"x1": x1, "x2": x2, "y": y})


def _fit_transform_df() -> pd.DataFrame:
    n = 30
    x1 = [float(i % 10) + 1.0 for i in range(n)]
    x2 = [float((i * 2) % 7) + 1.0 for i in range(n)]
    x3 = [float((i * 3) % 5) + 1.0 for i in range(n)]
    cat = [["a", "b", "c"][i % 3] for i in range(n)]
    y = [i % 2 for i in range(n)]
    return pd.DataFrame({"x1": x1, "x2": x2, "x3": x3, "cat": cat, "y": y})


_FIT_TRANSFORM_NUMERIC_FEATURES = ["x1", "x2", "x3"]

#: Per-key overrides so every curated fit_transform-archetype estimator fits this 30-row
#: dataset sensibly -- mirrors tests/test_ml_fit_transform_catalog.py's own overrides.
_FIT_TRANSFORM_OVERRIDES: dict[str, dict] = {
    "OneHotEncoder": {"features": ["cat"]},
    "OrdinalEncoder": {"features": ["cat"]},
    "SelectKBest": {
        "features": _FIT_TRANSFORM_NUMERIC_FEATURES,
        "target": "y",
        "params": {"k": 2},
    },
    "TSNE": {"features": _FIT_TRANSFORM_NUMERIC_FEATURES, "params": {"perplexity": 5}},
}


def _fit_transform_args_for(estimator_key: str) -> dict:
    overrides = _FIT_TRANSFORM_OVERRIDES.get(estimator_key, {})
    return {
        "features": overrides.get("features", _FIT_TRANSFORM_NUMERIC_FEATURES),
        "target": overrides.get("target"),
        "params": overrides.get("params", {}),
    }


def _blob_df() -> pd.DataFrame:
    """Two well-separated 15-point blobs -- see the "Test data note" in
    tests/test_ml_cluster_detect_catalog.py for why well-separated blobs (not nearby points)
    are required for run-to-run determinism."""
    n_per = 15
    x1 = [float(i) for i in range(n_per)] + [float(i) + 100.0 for i in range(n_per)]
    x2 = [float(i) for i in range(n_per)] + [float(i) + 100.0 for i in range(n_per)]
    return pd.DataFrame({"x1": x1, "x2": x2})


_CLUSTER_DETECT_FEATURES = ["x1", "x2"]

#: Per-key overrides -- mirrors tests/test_ml_cluster_detect_catalog.py's own overrides.
_CLUSTER_DETECT_OVERRIDES: dict[str, dict] = {
    "KMeans": {"n_clusters": 2, "n_init": 5},
    "MiniBatchKMeans": {"n_clusters": 2, "batch_size": 30, "random_state": 0},
    "DBSCAN": {"eps": 5.0, "min_samples": 2},
    "AgglomerativeClustering": {"n_clusters": 2},
    "SpectralClustering": {"n_clusters": 2},
    "Birch": {"n_clusters": 2, "threshold": 0.5},
    "GaussianMixture": {"n_components": 2},
    "BayesianGaussianMixture": {"n_components": 2},
    "LocalOutlierFactor": {"n_neighbors": 5},
}


def _cluster_detect_params_for(estimator_key: str) -> dict:
    return _CLUSTER_DETECT_OVERRIDES.get(estimator_key, {})


# ---------------------------------------------------------------------------
# The matrix: one equivalence assertion per estimator, keyed on ef.ml.summarize().
# ---------------------------------------------------------------------------


@pytest.mark.equivalence
@pytest.mark.parametrize("estimator_key", keys_for_archetype("fit"))
def test_fit_archetype_summary_equivalence(estimator_key: str) -> None:
    """ADR-0002: execute() and codegen produce the same ef.ml.summarize() for every
    fit-archetype estimator."""
    spec = get_estimator_spec(estimator_key)
    target = "label" if spec.task == "classification" else "y"
    df = _classification_df() if spec.task == "classification" else _regression_df()

    defn = FitEstimator()
    node = defn.instantiate(estimator=estimator_key, target=target)
    executed_model = defn.execute(node, inputs={"frame": df.copy()})["model"]
    scope = _run_codegen(defn, node, {"frame": df.copy()})
    codegen_model = scope["model"]

    _assert_summaries_equivalent(summarize(executed_model), summarize(codegen_model))


@pytest.mark.equivalence
@pytest.mark.parametrize("estimator_key", keys_for_archetype("fit_transform"))
def test_fit_transform_archetype_summary_equivalence(estimator_key: str) -> None:
    """ADR-0002: execute() and codegen produce the same ef.ml.summarize() for every
    fit_transform-archetype estimator."""
    args = _fit_transform_args_for(estimator_key)
    df = _fit_transform_df()

    defn = FitTransform()
    node = defn.instantiate(
        estimator=estimator_key,
        target=args["target"],
        features=args["features"],
        params=args["params"],
    )
    executed_transformer = defn.execute(node, inputs={"frame": df.copy()})["transformer"]
    scope = _run_codegen(defn, node, {"frame": df.copy()})
    codegen_transformer = scope["transformer"]

    _assert_summaries_equivalent(summarize(executed_transformer), summarize(codegen_transformer))


@pytest.mark.equivalence
@pytest.mark.parametrize("estimator_key", keys_for_archetype("cluster_detect"))
def test_cluster_detect_archetype_summary_equivalence(estimator_key: str) -> None:
    """ADR-0002: execute() and codegen produce the same ef.ml.summarize() for every
    cluster_detect-archetype estimator."""
    params = _cluster_detect_params_for(estimator_key)
    df = _blob_df()

    defn = ClusterDetect()
    node = defn.instantiate(
        estimator=estimator_key, features=_CLUSTER_DETECT_FEATURES, params=params
    )
    executed_model = defn.execute(node, inputs={"frame": df.copy()})["model"]
    scope = _run_codegen(defn, node, {"frame": df.copy()})
    codegen_model = scope["model"]

    _assert_summaries_equivalent(summarize(executed_model), summarize(codegen_model))
