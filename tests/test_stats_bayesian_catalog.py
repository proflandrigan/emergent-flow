"""
Golden + equivalence tests for the Epic 12 Story 7 Bayesian catalog entry (BayesianGLM, via
bambi/PyMC, summarized with ArviZ).

Guarded with ``pytest.importorskip`` (torch-style optional-dependency discipline, Story 1's hard
boundary) so the repo's default CI lane -- where ``[bayes]`` is not installed -- skips this file
cleanly instead of failing on import. A separate, ``[bayes]``-installed CI lane (or manual/local
run, as here) is what actually exercises these tests.

Mirrors ``tests/test_stats_mixedlm_catalog.py``'s two-part shape:

1. Golden-code quality: a representative BayesianGLM graph (LoadSample -> FitBayesianModel)
   compiles to syntactically valid, ruff-clean Python (parse/lint only, never executed in this
   part).
2. ADR-0002 equivalence: for a plain Bayesian GLM AND a Bayesian hierarchical spec (random
   intercept via the same ``random_effects``/``groups`` vocabulary as MixedLM), ``execute()`` and
   running the code ``codegen()`` emits produce the SAME posterior-summary coefficient frame and
   fit_stats, given a fixed ``seed``/``draws``/``tune``/``chains`` (docs/stats-viz-design.md
   Decision 5's determinism requirement).
"""

from __future__ import annotations

import ast
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("bambi")
pytest.importorskip("pymc")
pytest.importorskip("arviz")

from emergentflow.codegen.compiler import compile_to_code  # noqa: E402
from emergentflow.ir.common import Direction  # noqa: E402
from emergentflow.ir.edge import Edge, PortRef  # noqa: E402
from emergentflow.ir.graph import Graph  # noqa: E402
from emergentflow.nodes.examples import FitBayesianModel, LoadSample  # noqa: E402

_MCMC_KWARGS = {"seed": 0, "draws": 50, "tune": 50, "chains": 2}


def _out_port(node, name):
    return next(p for p in node.ports if p.direction == Direction.OUT and p.name == name)


def _in_port(node, name):
    return next(p for p in node.ports if p.direction == Direction.IN and p.name == name)


def _run_codegen(definition, node, scope):
    frag = definition.preview(node)
    exec(frag.render(), scope)  # noqa: S102 -- test-only, on our own emitted code
    return scope


# ---------------------------------------------------------------------------
# 1. Golden-code quality: one representative BayesianGLM graph.
# ---------------------------------------------------------------------------


def _build_load_fit_graph() -> Graph:
    load = LoadSample().instantiate(name="diabetes", label="Load Sample")
    fit = FitBayesianModel().instantiate(
        target="target",
        fixed_effects=["age"],
        label="Fit BayesianGLM",
        **_MCMC_KWARGS,
    )
    edge = Edge(
        source=PortRef(node_id=load.id, port_id=_out_port(load, "frame").id),
        target=PortRef(node_id=fit.id, port_id=_in_port(fit, "frame").id),
    )
    return Graph(nodes={load.id: load, fit.id: fit}, edges={edge.id: edge})


def test_bayesian_codegen_is_parseable() -> None:
    code = compile_to_code(_build_load_fit_graph())
    ast.parse(code)


def test_bayesian_codegen_is_ruff_clean() -> None:
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
# 2. ADR-0002 equivalence: plain Bayesian GLM AND Bayesian hierarchical.
# ---------------------------------------------------------------------------


def _plain_df(seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = 60
    x = rng.normal(size=n)
    y = 2.0 * x + 1.0 + rng.normal(scale=0.3, size=n)
    return pd.DataFrame({"x": x, "y": y})


def _grouped_df(seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for g in range(6):
        intercept = g * 5.0
        for _ in range(20):
            x = rng.normal()
            y = intercept + 2.0 * x + rng.normal(scale=0.3)
            rows.append({"x": x, "y": y, "grp": f"g{g}"})
    return pd.DataFrame(rows)


@pytest.mark.equivalence
@pytest.mark.parametrize(
    ("df_builder", "base_kwargs"),
    [
        pytest.param(
            _plain_df,
            {"target": "y", "fixed_effects": ["x"]},
            id="plain_glm",
        ),
        pytest.param(
            _grouped_df,
            {
                "target": "y",
                "fixed_effects": ["x"],
                "groups": "grp",
            },
            id="hierarchical",
        ),
    ],
)
def test_bayesian_equivalence_matrix(df_builder, base_kwargs: dict) -> None:
    """ADR 0002: execute == running the emitted code, for BayesianGLM (plain and hierarchical)."""
    df = df_builder()
    fit_kwargs = {**base_kwargs, **_MCMC_KWARGS}

    defn = FitBayesianModel()
    node = defn.instantiate(**fit_kwargs)
    executed_model = defn.execute(node, inputs={"frame": df.copy()})["model"]
    scope = _run_codegen(defn, node, {"frame": df.copy()})
    codegen_model = scope["model"]

    pd.testing.assert_frame_equal(executed_model.coefficients, codegen_model.coefficients)
    assert executed_model.fit_stats == codegen_model.fit_stats
    assert executed_model.model == codegen_model.model == "BayesianGLM"
    assert "x" in set(executed_model.coefficients["term"])
