"""
Tests for the transform-family nodes (Scale Features, Encode Categorical,
Discretize, Generate Features).

Covers:
1. Node instantiation and metadata
2. Execute produces correct output types
3. Codegen is parseable and ruff-clean
4. ADR-0002 equivalence: execute output matches codegen output
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
from emergentflow.nodes.examples import (
    Discretize,
    EncodeCategorical,
    GenerateFeatures,
    LoadSample,
    ScaleFeatures,
)


def _out_port(node, name):
    return next(p for p in node.ports if p.direction == Direction.OUT and p.name == name)


def _in_port(node, name):
    return next(p for p in node.ports if p.direction == Direction.IN and p.name == name)


def _run_codegen(definition, node, scope):
    frag = definition.preview(node)
    exec(frag.render(), scope)  # noqa: S102
    return scope


def _test_df() -> pd.DataFrame:
    n = 30
    x1 = [float(i % 10) + 1.0 for i in range(n)]
    x2 = [float((i * 2) % 7) + 1.0 for i in range(n)]
    x3 = [float((i * 3) % 5) + 1.0 for i in range(n)]
    cat = [["a", "b", "c"][i % 3] for i in range(n)]
    y = [i % 2 for i in range(n)]
    return pd.DataFrame({"x1": x1, "x2": x2, "x3": x3, "cat": cat, "y": y})


_NUMERIC_FEATURES = ["x1", "x2", "x3"]


# ---------------------------------------------------------------------------
# 1. Node metadata
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cls, expected_type, expected_family",
    [
        (ScaleFeatures, "transform.scale_features", "transform"),
        (EncodeCategorical, "transform.encode_categorical", "transform"),
        (Discretize, "transform.discretize", "transform"),
        (GenerateFeatures, "transform.generate_features", "transform"),
    ],
)
def test_transform_node_metadata(cls, expected_type, expected_family):
    defn = cls()
    assert defn.type == expected_type
    assert defn.family == expected_family


# ---------------------------------------------------------------------------
# 2. Scale Features equivalence
# ---------------------------------------------------------------------------


_SCALER_KEYS = [
    "MaxAbsScaler",
    "MinMaxScaler",
    "Normalizer",
    "PowerTransformer",
    "RobustScaler",
    "StandardScaler",
]


@pytest.mark.equivalence
@pytest.mark.parametrize("estimator_key", _SCALER_KEYS)
def test_scale_features_equivalence(estimator_key: str) -> None:
    df = _test_df()
    defn = ScaleFeatures()
    node = defn.instantiate(estimator=estimator_key, features=_NUMERIC_FEATURES)

    executed = defn.execute(node, inputs={"frame": df.copy()})
    assert "transformer" in executed
    assert "result" in executed

    scope = _run_codegen(defn, node, {"frame": df.copy()})

    assert executed["transformer"].estimator_type == scope["transformer"].estimator_type
    assert executed["transformer"].feature_names == scope["transformer"].feature_names

    component_cols = [c for c in executed["result"].columns if c.startswith("component_")]
    assert component_cols
    for col in component_cols:
        assert executed["result"][col].tolist() == pytest.approx(scope["result"][col].tolist())


# ---------------------------------------------------------------------------
# 3. Encode Categorical equivalence
# ---------------------------------------------------------------------------


_ENCODER_CONFIGS = [
    ("OneHotEncoder", {"features": ["cat"], "target": None}),
    ("OrdinalEncoder", {"features": ["cat"], "target": None}),
    ("TargetEncoder", {"features": ["cat"], "target": "y"}),
]


@pytest.mark.equivalence
@pytest.mark.parametrize("estimator_key, overrides", _ENCODER_CONFIGS)
def test_encode_categorical_equivalence(estimator_key: str, overrides: dict) -> None:
    df = _test_df()
    defn = EncodeCategorical()
    node = defn.instantiate(
        estimator=estimator_key,
        features=overrides["features"],
        target=overrides["target"],
    )

    executed = defn.execute(node, inputs={"frame": df.copy()})
    assert "transformer" in executed
    assert "result" in executed

    scope = _run_codegen(defn, node, {"frame": df.copy()})

    assert executed["transformer"].estimator_type == scope["transformer"].estimator_type

    component_cols = [c for c in executed["result"].columns if c.startswith("component_")]
    assert component_cols
    for col in component_cols:
        assert executed["result"][col].tolist() == pytest.approx(
            scope["result"][col].tolist(), nan_ok=True
        )


# ---------------------------------------------------------------------------
# 4. Discretize equivalence
# ---------------------------------------------------------------------------


_DISCRETIZER_KEYS = ["Binarizer", "KBinsDiscretizer"]


@pytest.mark.equivalence
@pytest.mark.parametrize("estimator_key", _DISCRETIZER_KEYS)
def test_discretize_equivalence(estimator_key: str) -> None:
    df = _test_df()
    defn = Discretize()
    node = defn.instantiate(estimator=estimator_key, features=_NUMERIC_FEATURES)

    executed = defn.execute(node, inputs={"frame": df.copy()})
    assert "transformer" in executed
    assert "result" in executed

    scope = _run_codegen(defn, node, {"frame": df.copy()})

    assert executed["transformer"].estimator_type == scope["transformer"].estimator_type

    component_cols = [c for c in executed["result"].columns if c.startswith("component_")]
    assert component_cols
    for col in component_cols:
        assert executed["result"][col].tolist() == pytest.approx(scope["result"][col].tolist())


# ---------------------------------------------------------------------------
# 5. Generate Features equivalence
# ---------------------------------------------------------------------------


@pytest.mark.equivalence
def test_generate_features_equivalence() -> None:
    df = _test_df()
    defn = GenerateFeatures()
    node = defn.instantiate(estimator="PolynomialFeatures", features=_NUMERIC_FEATURES)

    executed = defn.execute(node, inputs={"frame": df.copy()})
    assert "transformer" in executed
    assert "result" in executed

    scope = _run_codegen(defn, node, {"frame": df.copy()})

    assert executed["transformer"].estimator_type == scope["transformer"].estimator_type

    component_cols = [c for c in executed["result"].columns if c.startswith("component_")]
    assert component_cols
    for col in component_cols:
        assert executed["result"][col].tolist() == pytest.approx(scope["result"][col].tolist())


# ---------------------------------------------------------------------------
# 6. Codegen quality: one representative node produces parseable, ruff-clean code
# ---------------------------------------------------------------------------


def _build_transform_graph(node_cls, estimator_key, **extra_params):
    load = LoadSample().instantiate(name="iris", label="Load Sample")
    transform_node = node_cls().instantiate(
        estimator=estimator_key, label=node_cls.label, **extra_params
    )
    edge = Edge(
        source=PortRef(node_id=load.id, port_id=_out_port(load, "frame").id),
        target=PortRef(node_id=transform_node.id, port_id=_in_port(transform_node, "frame").id),
    )
    return Graph(
        nodes={load.id: load, transform_node.id: transform_node},
        edges={edge.id: edge},
    )


_CODEGEN_CASES = [
    (ScaleFeatures, "StandardScaler", {}),
    (EncodeCategorical, "OrdinalEncoder", {}),
    (Discretize, "Binarizer", {}),
    (GenerateFeatures, "PolynomialFeatures", {}),
]


@pytest.mark.parametrize("node_cls, estimator_key, extra", _CODEGEN_CASES)
def test_transform_codegen_is_parseable(node_cls, estimator_key, extra):
    graph = _build_transform_graph(node_cls, estimator_key, **extra)
    code = compile_to_code(graph)
    ast.parse(code)


@pytest.mark.parametrize("node_cls, estimator_key, extra", _CODEGEN_CASES)
def test_transform_codegen_is_ruff_clean(node_cls, estimator_key, extra):
    graph = _build_transform_graph(node_cls, estimator_key, **extra)
    code = compile_to_code(graph)
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "-"],
        input=code,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
