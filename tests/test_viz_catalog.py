"""
Golden + equivalence tests for the Epic 12 Story 8 chart catalog (``viz.plot`` archetype node).

Mirrors ``tests/test_stats_regression_catalog.py``'s two-part shape:

1. Golden-code quality: for a representative encoding per curated chart kind, the whole-graph
   ``compile_to_code`` output (LoadSample -> VizPlot) is syntactically valid Python and passes
   ``ruff check``.
2. ADR-0002 equivalence: for every curated chart kind (computed dynamically from
   ``known_chart_keys()``, not hardcoded, since Story 8's chart registry is the allow-list of
   record), ``execute()`` and running the code ``codegen()`` emits produce the identical
   ``PlotSpec`` on a fixed, seeded synthetic frame.
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
from emergentflow.nodes.examples import LoadSample, VizPlot
from emergentflow.viz.registry import known_chart_keys


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
# Per-chart-kind fixture: encoding/options valid against the fixed synthetic frame built by
# _fixture_frame(). Every key in known_chart_keys() MUST have an entry here --
# test_every_known_chart_has_a_fixture enforces that, so a future catalog addition fails loudly
# here instead of silently losing coverage.
# ---------------------------------------------------------------------------

_CHART_FIXTURES: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {
    "scatter": ({"x": "a", "y": "b"}, {}),
    "line": ({"x": "a", "y": "b"}, {}),
    "bar": ({"x": "cat", "y": "a"}, {}),
    "histogram": ({"x": "a"}, {"nbins": 10}),
    "box": ({"x": "cat", "y": "a"}, {}),
    "violin": ({"x": "cat", "y": "a"}, {}),
    "strip": ({"x": "cat", "y": "a"}, {}),
    "ecdf": ({"x": "a"}, {}),
    "density_heatmap": ({"x": "a", "y": "b"}, {}),
    "density_contour": ({"x": "a", "y": "b"}, {}),
    "scatter_matrix": ({"dimensions": ["a", "b", "c"]}, {}),
}


def _fixture_frame() -> pd.DataFrame:
    """A fixed, seeded synthetic frame with every column every fixture encoding needs."""
    rng = np.random.default_rng(0)
    n = 30
    a = rng.normal(size=n)
    b = 2.0 * a + rng.normal(scale=0.1, size=n)
    c = rng.normal(size=n)
    cat = ["g1" if i % 2 == 0 else "g2" for i in range(n)]
    return pd.DataFrame({"a": a, "b": b, "c": c, "cat": cat})


def test_every_known_chart_has_a_fixture():
    assert set(_CHART_FIXTURES) == set(known_chart_keys())


# ---------------------------------------------------------------------------
# 1. Golden-code quality: one representative graph per chart kind.
# ---------------------------------------------------------------------------


def _build_load_plot_graph(chart: str, encoding: dict[str, Any], options: dict[str, Any]) -> Graph:
    load = LoadSample().instantiate(name="diabetes", label="Load Sample")
    node = VizPlot().instantiate(chart=chart, encoding=encoding, options=options, label="Plot")
    edge = Edge(
        source=PortRef(node_id=load.id, port_id=_out_port(load, "frame").id),
        target=PortRef(node_id=node.id, port_id=_in_port(node, "frame").id),
    )
    return Graph(nodes={load.id: load, node.id: node}, edges={edge.id: edge})


@pytest.mark.parametrize("chart_key", sorted(known_chart_keys()))
def test_viz_catalog_codegen_is_parseable(chart_key: str) -> None:
    encoding, options = _CHART_FIXTURES[chart_key]
    code = compile_to_code(_build_load_plot_graph(chart_key, encoding, options))
    ast.parse(code)


@pytest.mark.parametrize("chart_key", sorted(known_chart_keys()))
def test_viz_catalog_codegen_is_ruff_clean(chart_key: str) -> None:
    encoding, options = _CHART_FIXTURES[chart_key]
    code = compile_to_code(_build_load_plot_graph(chart_key, encoding, options))
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "-"],
        input=code,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# 2. ADR-0002 equivalence: execute() vs running the emitted code, per chart kind.
# ---------------------------------------------------------------------------


@pytest.mark.equivalence
@pytest.mark.parametrize("chart_key", sorted(known_chart_keys()))
def test_viz_plot_equivalence_matrix(chart_key: str) -> None:
    """ADR 0002: execute == running the emitted code, for every curated chart kind."""
    encoding, options = _CHART_FIXTURES[chart_key]
    df = _fixture_frame()

    defn = VizPlot()
    node = defn.instantiate(chart=chart_key, encoding=encoding, options=options)
    executed_plot = defn.execute(node, inputs={"frame": df.copy()})["plot"]
    scope = _run_codegen(defn, node, {"frame": df.copy()})
    codegen_plot = scope["plot"]

    assert executed_plot.chart == codegen_plot.chart == chart_key
    assert executed_plot.spec == codegen_plot.spec
