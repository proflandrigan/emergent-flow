"""
Golden + equivalence tests for the Epic 12 Story 11 EDA catalog: ``EdaProfile``,
``Missingness``, ``DistributionSummary``, ``GroupByAggregate``, and ``AutoEda``.

Mirrors ``tests/test_stats_regression_catalog.py``'s two-part shape (golden code quality +
ADR-0002 equivalence), applied per EDA node rather than per fit_model archetype key, since these
nodes are transform/fan-out nodes -- not the fit_model archetype -- and so don't belong in the
Story-10 model matrix.
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
from emergentflow.nodes.examples import (
    AutoEda,
    DistributionSummary,
    EdaProfile,
    GroupByAggregate,
    LoadSample,
    Missingness,
)


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
# 1. Golden-code quality: LoadSample(iris) -> <EDA node>, one representative graph each.
# ---------------------------------------------------------------------------


def _build_load_eda_graph(node_cls, node_kwargs: dict[str, Any]) -> Graph:
    load = LoadSample().instantiate(name="iris", label="Load Sample")
    node = node_cls().instantiate(label="EDA Node", **node_kwargs)
    edge = Edge(
        source=PortRef(node_id=load.id, port_id=_out_port(load, "frame").id),
        target=PortRef(node_id=node.id, port_id=_in_port(node, "frame").id),
    )
    return Graph(nodes={load.id: load, node.id: node}, edges={edge.id: edge})


_GOLDEN_GRAPHS = {
    "eda_profile": (EdaProfile, {}),
    "missingness": (Missingness, {}),
    "distribution_summary": (DistributionSummary, {}),
    "group_by_aggregate": (GroupByAggregate, {"by": ["target"], "agg": "mean"}),
    "group_by_aggregate_multi": (GroupByAggregate, {"by": ["target"], "aggs": ["mean", "std"]}),
    "auto_eda": (AutoEda, {}),
}


@pytest.mark.parametrize("case", sorted(_GOLDEN_GRAPHS))
def test_eda_catalog_codegen_is_parseable(case: str) -> None:
    node_cls, node_kwargs = _GOLDEN_GRAPHS[case]
    code = compile_to_code(_build_load_eda_graph(node_cls, node_kwargs))
    ast.parse(code)


@pytest.mark.parametrize("case", sorted(_GOLDEN_GRAPHS))
def test_eda_catalog_codegen_is_ruff_clean(case: str) -> None:
    node_cls, node_kwargs = _GOLDEN_GRAPHS[case]
    code = compile_to_code(_build_load_eda_graph(node_cls, node_kwargs))
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "-"],
        input=code,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# 2. ADR-0002 equivalence: execute() vs running the emitted code, per EDA node, on a fixed
#    seeded synthetic frame (two numeric columns, a categorical group column, and a column
#    with nulls so missingness is non-trivial).
# ---------------------------------------------------------------------------


def _fixed_eda_frame() -> pd.DataFrame:
    rng = np.random.default_rng(0)
    n = 20
    a = rng.normal(size=n)
    b = 2.0 * a + rng.normal(scale=0.1, size=n)
    grp = ["g1", "g2"] * (n // 2)
    c = rng.normal(size=n)
    c[::5] = np.nan  # some nulls, so missingness is non-trivial
    return pd.DataFrame({"a": a, "b": b, "grp": grp, "c": c})


@pytest.mark.equivalence
def test_eda_profile_equivalence() -> None:
    df = _fixed_eda_frame()
    defn = EdaProfile()
    node = defn.instantiate(label="Profile")
    executed = defn.execute(node, inputs={"frame": df.copy()})
    scope = _run_codegen(defn, node, {"frame": df.copy()})
    pd.testing.assert_frame_equal(executed["summary"], scope["summary"])


@pytest.mark.equivalence
def test_missingness_equivalence() -> None:
    df = _fixed_eda_frame()
    defn = Missingness()
    node = defn.instantiate(label="Missingness")
    executed = defn.execute(node, inputs={"frame": df.copy()})
    scope = _run_codegen(defn, node, {"frame": df.copy()})
    pd.testing.assert_frame_equal(executed["summary"], scope["summary"])


@pytest.mark.equivalence
def test_distribution_summary_equivalence() -> None:
    df = _fixed_eda_frame()
    defn = DistributionSummary()
    node = defn.instantiate(label="Distribution Summary")
    executed = defn.execute(node, inputs={"frame": df.copy()})
    scope = _run_codegen(defn, node, {"frame": df.copy()})
    pd.testing.assert_frame_equal(executed["summary"], scope["summary"])


@pytest.mark.equivalence
def test_group_by_aggregate_equivalence() -> None:
    df = _fixed_eda_frame()
    defn = GroupByAggregate()
    node = defn.instantiate(by=["grp"], agg="mean", label="Group By Aggregate")
    executed = defn.execute(node, inputs={"frame": df.copy()})
    scope = _run_codegen(defn, node, {"frame": df.copy()})
    pd.testing.assert_frame_equal(executed["summary"], scope["summary"])


@pytest.mark.equivalence
def test_group_by_aggregate_multi_stat_equivalence() -> None:
    df = _fixed_eda_frame()
    defn = GroupByAggregate()
    node = defn.instantiate(by=["grp"], aggs=["mean", "std"], label="Group By Aggregate Multi")
    executed = defn.execute(node, inputs={"frame": df.copy()})
    scope = _run_codegen(defn, node, {"frame": df.copy()})
    pd.testing.assert_frame_equal(executed["summary"], scope["summary"])


@pytest.mark.equivalence
def test_auto_eda_equivalence() -> None:
    df = _fixed_eda_frame()
    defn = AutoEda()
    node = defn.instantiate(label="Auto EDA")
    executed = defn.execute(node, inputs={"frame": df.copy()})
    scope = _run_codegen(defn, node, {"frame": df.copy()})

    pd.testing.assert_frame_equal(executed["profile"], scope["profile"])
    pd.testing.assert_frame_equal(executed["missingness"], scope["missingness"])
    pd.testing.assert_frame_equal(executed["correlation"], scope["correlation"])
    pd.testing.assert_frame_equal(executed["frame"], df)

    assert executed["distribution_plot"].spec == scope["distribution_plot"].spec
    assert executed["correlation_heatmap"].spec == scope["correlation_heatmap"].spec
    assert executed["missingness_plot"].spec == scope["missingness_plot"].spec
