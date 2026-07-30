"""
Golden + equivalence tests for the Epic 8 Story 6 outlier_detect estimator catalog.

Mirrors ``tests/test_ml_cluster_detect_catalog.py`` for the new ``outlier_detect`` archetype.
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
from emergentflow.ml import fit_and_detect
from emergentflow.ml.registry import get_estimator_spec, known_estimator_keys
from emergentflow.nodes.examples import ApplyEstimator, LoadSample, OutlierDetect


def _out_port(node, name):
    return next(p for p in node.ports if p.direction == Direction.OUT and p.name == name)


def _in_port(node, name):
    return next(p for p in node.ports if p.direction == Direction.IN and p.name == name)


def _outlier_detect_archetype_keys() -> list[str]:
    return sorted(
        k for k in known_estimator_keys() if get_estimator_spec(k).archetype == "outlier_detect"
    )


def _run_codegen(definition, node, scope):
    """exec a node's preview fragment in *scope* and return the updated scope."""
    frag = definition.preview(node)
    exec(frag.render(), scope)  # noqa: S102 -- test-only, on our own emitted code
    return scope


def _blob_df() -> pd.DataFrame:
    """30 rows: two well-separated 15-point blobs plus one obvious outlier."""
    n_per = 15
    x1 = [float(i) for i in range(n_per)] + [float(i) + 100.0 for i in range(n_per)] + [500.0]
    x2 = [float(i) for i in range(n_per)] + [float(i) + 100.0 for i in range(n_per)] + [500.0]
    return pd.DataFrame({"x1": x1, "x2": x2})


_FEATURES = ["x1", "x2"]

#: Per-key param overrides for the small synthetic dataset.
_KEY_OVERRIDES: dict[str, dict] = {
    "LocalOutlierFactor": {"n_neighbors": 5},
}


def _params_for(estimator_key: str) -> dict:
    return _KEY_OVERRIDES.get(estimator_key, {})


# ---------------------------------------------------------------------------
# 1. Golden-code quality.
# ---------------------------------------------------------------------------


def _build_outlier_detect_graph(estimator_key: str) -> Graph:
    params = {"random_state": 0}
    load = LoadSample().instantiate(name="iris", label="Load Sample")
    node = OutlierDetect().instantiate(
        estimator=estimator_key, features=_FEATURES, params=params, label="Outlier Detect"
    )
    edge = Edge(
        source=PortRef(node_id=load.id, port_id=_out_port(load, "frame").id),
        target=PortRef(node_id=node.id, port_id=_in_port(node, "frame").id),
    )
    return Graph(nodes={load.id: load, node.id: node}, edges={edge.id: edge})


@pytest.mark.parametrize("estimator_key", ["IsolationForest"])
def test_outlier_detect_catalog_codegen_is_parseable(estimator_key: str) -> None:
    """Generated code for a representative outlier_detect estimator parses (importable)."""
    code = compile_to_code(_build_outlier_detect_graph(estimator_key))
    ast.parse(code)  # raises SyntaxError on failure


@pytest.mark.parametrize("estimator_key", ["IsolationForest"])
def test_outlier_detect_catalog_codegen_is_ruff_clean(estimator_key: str) -> None:
    """Generated code for a representative outlier_detect estimator passes ``ruff check``."""
    code = compile_to_code(_build_outlier_detect_graph(estimator_key))
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "-"],
        input=code,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# 2. ADR-0002 equivalence matrix: every outlier_detect estimator.
# ---------------------------------------------------------------------------


@pytest.mark.equivalence
@pytest.mark.parametrize("estimator_key", _outlier_detect_archetype_keys())
def test_outlier_detect_equivalence_matrix(estimator_key: str) -> None:
    """ADR 0002: execute == running the emitted code, for every outlier_detect estimator."""
    params = _params_for(estimator_key)
    df = _blob_df()

    defn = OutlierDetect()
    node = defn.instantiate(estimator=estimator_key, features=_FEATURES, params=params)
    executed = defn.execute(node, inputs={"frame": df.copy()})
    executed_model, executed_result = executed["model"], executed["result"]

    scope = _run_codegen(defn, node, {"frame": df.copy()})
    codegen_model, codegen_result = scope["model"], scope["result"]

    assert executed_model.estimator_type == codegen_model.estimator_type
    assert executed_model.task == codegen_model.task == "outlier_detection"
    assert executed_model.feature_names == codegen_model.feature_names
    assert "outlier" in executed_result.columns
    assert executed_result["outlier"].tolist() == codegen_result["outlier"].tolist()


# ---------------------------------------------------------------------------
# 3. fit_and_detect archetype validation.
# ---------------------------------------------------------------------------


def test_fit_and_detect_rejects_cluster_detect_estimator_up_front() -> None:
    """A cluster_detect estimator must be rejected with a clear archetype error."""
    df = _blob_df()
    with pytest.raises(ValueError, match="not an outlier_detect-archetype estimator"):
        fit_and_detect(df, estimator="KMeans", features=_FEATURES)


def test_fit_and_detect_labels_frame() -> None:
    """fit_and_detect returns a model and a frame with an 'outlier' column."""
    df = _blob_df()
    model, result = fit_and_detect(df, estimator="IsolationForest", features=_FEATURES)
    assert model.task == "outlier_detection"
    assert "outlier" in result.columns
    assert set(result["outlier"].unique()).issubset({-1, 1})


# ---------------------------------------------------------------------------
# 4. Cross-frame predict works for novelty-enabled estimators.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "estimator_key",
    ["IsolationForest", "OneClassSVM", "EllipticEnvelope"],
)
def test_outlier_detect_model_predicts_on_new_data(estimator_key: str) -> None:
    """Novelty-enabled outlier detectors support prediction on a different frame."""
    df = _blob_df()
    params = _params_for(estimator_key)
    fit_defn = OutlierDetect()
    fit_node = fit_defn.instantiate(estimator=estimator_key, features=_FEATURES, params=params)
    fitted = fit_defn.execute(fit_node, inputs={"frame": df})
    model = fitted["model"]

    new_df = df.copy()
    apply_defn = ApplyEstimator()
    apply_node = apply_defn.instantiate(op="predict")
    result = apply_defn.execute(apply_node, inputs={"model": model, "frame": new_df})["result"]
    assert "prediction" in result.columns
    assert set(result["prediction"].unique()).issubset({-1, 1})
