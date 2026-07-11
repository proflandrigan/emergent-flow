"""
Golden + equivalence tests for the Epic 12 Story 4 regression/GLM catalog (OLS/WLS/GLS/GLM).

Mirrors ``tests/test_ml_supervised_catalog.py``'s two-part shape:

1. Golden-code quality: for a representative spec (an OLS graph, a logistic-GLM graph), the
   whole-graph ``compile_to_code`` output (LoadSample -> FitLinearRegression/FitGLM) is
   syntactically valid Python and passes ``ruff check``.
2. ADR-0002 equivalence: for each of OLS/WLS/GLS (via ``FitLinearRegression``) and GLM (via
   ``FitGLM``), ``execute()`` and running the code ``codegen()`` emits produce the same fitted
   coefficient frame and fit_stats.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from typing import Any

import numpy as np
import pandas as pd
import pytest

from emergentflow.codegen.compiler import compile_to_code
from emergentflow.ir.common import Direction
from emergentflow.ir.edge import Edge, PortRef
from emergentflow.ir.graph import Graph
from emergentflow.nodes.examples import FitGLM, FitLinearRegression, LoadSample


def _out_port(node, name):
    return next(p for p in node.ports if p.direction == Direction.OUT and p.name == name)


def _in_port(node, name):
    return next(p for p in node.ports if p.direction == Direction.IN and p.name == name)


def _run_codegen(definition, node, scope):
    """exec a node's preview fragment in *scope* and return the updated scope."""
    frag = definition.preview(node)
    exec(frag.render(), scope)  # noqa: S102 -- test-only, on our own emitted code
    return scope


# ---------------------------------------------------------------------------
# 1. Golden-code quality: OLS graph + logistic-GLM graph.
# ---------------------------------------------------------------------------


def _build_load_fit_graph(dataset: str, node_cls, fit_kwargs: dict[str, Any]) -> Graph:
    load = LoadSample().instantiate(name=dataset, label="Load Sample")
    fit = node_cls().instantiate(label="Fit Model", **fit_kwargs)
    edge = Edge(
        source=PortRef(node_id=load.id, port_id=_out_port(load, "frame").id),
        target=PortRef(node_id=fit.id, port_id=_in_port(fit, "frame").id),
    )
    return Graph(nodes={load.id: load, fit.id: fit}, edges={edge.id: edge})


_GOLDEN_GRAPHS = {
    "ols": (
        "diabetes",
        FitLinearRegression,
        {"estimator": "OLS", "target": "target", "fixed_effects": ["age", "bmi"]},
    ),
    # Logistic-GLM representative: parse/lint only, never executed here (iris's "target" is a
    # 3-class label, not a valid binomial outcome -- fine for a syntax/lint-only golden check).
    "glm_logistic": (
        "iris",
        FitGLM,
        {
            "target": "target",
            "fixed_effects": ["sepal length (cm)"],
            "family": "binomial",
        },
    ),
}


@pytest.mark.parametrize("case", sorted(_GOLDEN_GRAPHS))
def test_regression_catalog_codegen_is_parseable(case: str) -> None:
    dataset, node_cls, fit_kwargs = _GOLDEN_GRAPHS[case]
    code = compile_to_code(_build_load_fit_graph(dataset, node_cls, fit_kwargs))
    ast.parse(code)


@pytest.mark.parametrize("case", sorted(_GOLDEN_GRAPHS))
def test_regression_catalog_codegen_is_ruff_clean(case: str) -> None:
    dataset, node_cls, fit_kwargs = _GOLDEN_GRAPHS[case]
    code = compile_to_code(_build_load_fit_graph(dataset, node_cls, fit_kwargs))
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "-"],
        input=code,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# 2. ADR-0002 equivalence: OLS/WLS/GLS (via FitLinearRegression) + GLM (via FitGLM).
# ---------------------------------------------------------------------------

_EQUIVALENCE_MODEL_KEYS = ["OLS", "WLS", "GLS", "GLM"]
# Hardcoded, NOT dynamically pulled from the registry, because the fit_model archetype also
# holds MixedLM/GAM/BayesianGLM entries whose different structured-spec shapes (groups/
# random_effects, smooth_terms) belong to their own dedicated nodes/tests, not this file.


def _equivalence_fixture(model_key: str) -> tuple[pd.DataFrame, Any, dict[str, Any]]:
    """Return (df, node_cls, fit_kwargs) for *model_key*, fixed seed for determinism."""
    rng = np.random.default_rng(0)
    n = 60
    x1 = rng.normal(size=n)
    x2 = rng.normal(size=n)
    y = 2.0 * x1 + 3.0 * x2 + 1.0 + rng.normal(scale=0.1, size=n)
    w = np.abs(rng.normal(size=n)) + 0.1
    df = pd.DataFrame({"x1": x1, "x2": x2, "y": y, "w": w})

    if model_key in ("OLS", "GLS"):
        return (
            df,
            FitLinearRegression,
            {"estimator": model_key, "target": "y", "fixed_effects": ["x1", "x2"]},
        )
    if model_key == "WLS":
        return (
            df,
            FitLinearRegression,
            {
                "estimator": "WLS",
                "target": "y",
                "fixed_effects": ["x1", "x2"],
                "weights": "w",
            },
        )
    if model_key == "GLM":
        p = 1.0 / (1.0 + np.exp(-(2.0 * x1)))
        label = (rng.random(n) < p).astype(float)
        df = df.assign(label=label)
        return (
            df,
            FitGLM,
            {"target": "label", "fixed_effects": ["x1"], "family": "binomial"},
        )
    raise ValueError(model_key)  # pragma: no cover - exhaustive above


@pytest.mark.equivalence
@pytest.mark.parametrize("model_key", _EQUIVALENCE_MODEL_KEYS)
def test_fit_model_equivalence_matrix(model_key: str) -> None:
    """ADR 0002: execute == running the emitted code, for OLS/WLS/GLS/GLM."""
    df, node_cls, fit_kwargs = _equivalence_fixture(model_key)

    defn = node_cls()
    node = defn.instantiate(**fit_kwargs)
    executed_model = defn.execute(node, inputs={"frame": df.copy()})["model"]
    scope = _run_codegen(defn, node, {"frame": df.copy()})
    codegen_model = scope["model"]

    pd.testing.assert_frame_equal(executed_model.coefficients, codegen_model.coefficients)
    assert executed_model.fit_stats == codegen_model.fit_stats
    assert executed_model.model == codegen_model.model == model_key
