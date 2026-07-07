"""
Golden + equivalence tests for the Epic 12 Story 5 MixedLM (hierarchical/mixed-effects) catalog
entry.

Mirrors ``tests/test_stats_regression_catalog.py``'s two-part shape:

1. Golden-code quality: a representative MixedLM graph (LoadSample-free -- built directly from a
   grouped DataFrame fixture via a synthetic in-graph frame is not available, so this uses the
   same LoadSample -> FitModel graph shape on a real sample dataset, treated as a fixed grouping
   column) compiles to syntactically valid, ruff-clean Python.
2. ADR-0002 equivalence: for MixedLM with random-intercept-only AND random-intercept+slope specs,
   ``execute()`` and running the code ``codegen()`` emits produce the same fixed-effect +
   variance-component coefficient frame and fit_stats, on a fixed-seed, well-separated grouped
   fixture (the mixed-model analog of Epic 8's "ambiguous synthetic data makes KMeans
   nondeterministic" lesson -- see docs/stats-viz-design.md's Notes/Risks).
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


def _grouped_df(seed: int = 0) -> pd.DataFrame:
    """A well-separated, fixed-seed grouped fixture: 6 groups x 10 obs, varying slopes across
    groups so both random-intercept-only and random-intercept+slope MixedLM specs converge
    deterministically."""
    rng = np.random.default_rng(seed)
    rows = []
    for g in range(6):
        intercept = g * 4.0
        slope = 2.0 + rng.normal(scale=1.0)
        for _ in range(10):
            x = rng.normal()
            y = intercept + slope * x + rng.normal(scale=0.5)
            rows.append({"x": x, "y": y, "grp": f"g{g}"})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 1. Golden-code quality: one representative MixedLM graph.
# ---------------------------------------------------------------------------


def _build_load_fit_graph() -> Graph:
    # Golden test only needs syntactically-valid, ruff-clean generated code -- it is never
    # executed here (parse/lint only), so any loadable sample + a plausible grouping column
    # (the sample's own "target" column, reused as a coarse "group" for this parse/lint-only
    # check) is fine.
    load = LoadSample().instantiate(name="wine", label="Load Sample")
    fit = FitModel().instantiate(
        model="MixedLM",
        target="alcohol",
        fixed_effects=["magnesium"],
        random_effects=["magnesium"],
        groups="target",
        label="Fit MixedLM",
    )
    edge = Edge(
        source=PortRef(node_id=load.id, port_id=_out_port(load, "frame").id),
        target=PortRef(node_id=fit.id, port_id=_in_port(fit, "frame").id),
    )
    return Graph(nodes={load.id: load, fit.id: fit}, edges={edge.id: edge})


def test_mixedlm_codegen_is_parseable() -> None:
    code = compile_to_code(_build_load_fit_graph())
    ast.parse(code)


def test_mixedlm_codegen_is_ruff_clean() -> None:
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
# 2. ADR-0002 equivalence: random-intercept-only AND random-intercept+slope.
# ---------------------------------------------------------------------------


@pytest.mark.equivalence
@pytest.mark.parametrize(
    "fit_kwargs",
    [
        pytest.param(
            {"model": "MixedLM", "target": "y", "fixed_effects": ["x"], "groups": "grp"},
            id="random_intercept_only",
        ),
        pytest.param(
            {
                "model": "MixedLM",
                "target": "y",
                "fixed_effects": ["x"],
                "random_effects": ["x"],
                "groups": "grp",
            },
            id="random_intercept_and_slope",
        ),
    ],
)
def test_mixedlm_equivalence_matrix(fit_kwargs: dict) -> None:
    """ADR 0002: execute == running the emitted code, for MixedLM (both RE structures)."""
    df = _grouped_df()

    defn = FitModel()
    node = defn.instantiate(**fit_kwargs)
    executed_model = defn.execute(node, inputs={"frame": df.copy()})["model"]
    scope = _run_codegen(defn, node, {"frame": df.copy()})
    codegen_model = scope["model"]

    pd.testing.assert_frame_equal(executed_model.coefficients, codegen_model.coefficients)
    assert executed_model.fit_stats == codegen_model.fit_stats
    assert executed_model.model == codegen_model.model == "MixedLM"
    assert "Residual Var" in set(executed_model.coefficients["term"])
    assert executed_model.fit_stats["converged"] is True
