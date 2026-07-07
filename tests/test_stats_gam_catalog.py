"""
Golden + equivalence tests for the Epic 12 Story 6 GAM catalog entry (statsmodels GLMGam).

Mirrors ``tests/test_stats_regression_catalog.py``'s two-part shape:

1. Golden-code quality: a representative GAM graph (LoadSample -> FitModel) compiles to
   syntactically valid, ruff-clean Python.
2. ADR-0002 equivalence: ``execute()`` and running the code ``codegen()`` emits produce the
   same coefficient frame and fit_stats for a GAM fit (linear term + one smooth term).
"""

from __future__ import annotations

import ast
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from emergentflow.codegen.compiler import compile_to_code
from emergentflow.ir.common import Direction
from emergentflow.ir.edge import Edge, PortRef
from emergentflow.ir.graph import Graph
from emergentflow.nodes.examples import FitModel, LoadSample


def _out_port(node, name):
    return next(p for p in node.ports if p.direction == Direction.OUT and p.name == name)


def _in_port(node, name):
    return next(p for p in node.ports if p.direction == Direction.IN and p.name == name)


def _run_codegen(definition, node, scope):
    frag = definition.preview(node)
    exec(frag.render(), scope)  # noqa: S102 -- test-only, on our own emitted code
    return scope


# ---------------------------------------------------------------------------
# 1. Golden-code quality.
# ---------------------------------------------------------------------------


def _build_load_fit_graph() -> Graph:
    load = LoadSample().instantiate(name="diabetes", label="Load Sample")
    fit = FitModel().instantiate(
        model="GAM",
        target="target",
        label="Fit GAM",
        spec_extra={
            "linear_terms": ["age"],
            "smooth_terms": [{"column": "bmi", "df": 6, "degree": 3}],
        },
    )
    edge = Edge(
        source=PortRef(node_id=load.id, port_id=_out_port(load, "frame").id),
        target=PortRef(node_id=fit.id, port_id=_in_port(fit, "frame").id),
    )
    return Graph(nodes={load.id: load, fit.id: fit}, edges={edge.id: edge})


def test_gam_codegen_is_parseable() -> None:
    code = compile_to_code(_build_load_fit_graph())
    ast.parse(code)


def test_gam_codegen_is_ruff_clean() -> None:
    code = compile_to_code(_build_load_fit_graph())
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "-"],
        input=code,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# 2. ADR-0002 equivalence.
# ---------------------------------------------------------------------------


def _gam_df(seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = 200
    x1 = rng.normal(size=n)
    x2 = rng.uniform(-3, 3, size=n)
    y = 1.0 + 2.0 * x1 + np.sin(x2) + rng.normal(scale=0.2, size=n)
    return pd.DataFrame({"x1": x1, "x2": x2, "y": y})


@pytest.mark.equivalence
def test_gam_equivalence() -> None:
    """ADR 0002: execute == running the emitted code, for GAM."""
    df = _gam_df()
    fit_kwargs = {
        "model": "GAM",
        "target": "y",
        "spec_extra": {
            "linear_terms": ["x1"],
            "smooth_terms": [{"column": "x2", "df": 6, "degree": 3}],
        },
    }

    defn = FitModel()
    node = defn.instantiate(**fit_kwargs)
    executed_model = defn.execute(node, inputs={"frame": df.copy()})["model"]
    scope = _run_codegen(defn, node, {"frame": df.copy()})
    codegen_model = scope["model"]

    pd.testing.assert_frame_equal(executed_model.coefficients, codegen_model.coefficients)
    assert executed_model.fit_stats == codegen_model.fit_stats
    assert executed_model.model == codegen_model.model == "GAM"
    assert "s(x2)" in set(executed_model.coefficients["term"])
