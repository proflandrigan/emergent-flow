"""
Bridge tests: Epic 8 outputs (a PCA-transformed frame, a cluster-labeled frame) composed
directly into the Epic 12 Story 8 ``viz.plot`` scatter chart -- no new node types needed, since
both outputs are plain DataFrames Story 8's generic archetype already accepts. Proves the
"return the payload, let the UI render it" loop Epic 8 deferred (Story 9's PCA-scatter /
cluster-scatter bullets) by chaining EXISTING nodes into a real two-node graph and
round-tripping it through both ADR-0002 paths.

The third Story 9 "bridge" item, scatter-matrix / pair plot, needs no bridge test here -- it's
just the ``scatter_matrix`` chart key, already fully covered by ``tests/test_viz_catalog.py``.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from typing import Any

import pytest

from emergentflow.codegen.compiler import compile_to_code
from emergentflow.codegen.executor import execute as graph_execute
from emergentflow.ir.common import Direction
from emergentflow.ir.edge import Edge, PortRef
from emergentflow.ir.graph import Graph
from emergentflow.nodes.examples import ClusterDetect, FitTransform, LoadSample, VizPlot
from emergentflow.viz import PlotSpec


def _out_port(node, name):
    return next(p for p in node.ports if p.direction == Direction.OUT and p.name == name)


def _in_port(node, name):
    return next(p for p in node.ports if p.direction == Direction.IN and p.name == name)


def _assert_parseable_and_ruff_clean(code: str) -> None:
    ast.parse(code)
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "-"],
        input=code,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _run_compiled(graph: Graph) -> dict[str, Any]:
    """Compile *graph*, exec the module, call its main(), return the leaf-var result dict."""
    code = compile_to_code(graph)
    scope: dict[str, Any] = {}
    exec(code, scope)  # noqa: S102 -- test-only, on our own emitted code
    return scope["main"]()


_IRIS_FEATURES = [
    "sepal length (cm)",
    "sepal width (cm)",
    "petal length (cm)",
    "petal width (cm)",
]


def _build_pca_scatter_graph() -> Graph:
    load = LoadSample().instantiate(name="iris", label="Load Sample")
    pca = FitTransform().instantiate(
        estimator="PCA",
        target=None,
        features=_IRIS_FEATURES,
        params={"n_components": 2},
        label="Fit Transform",
    )
    plot = VizPlot().instantiate(
        chart="scatter",
        encoding={"x": "component_0", "y": "component_1", "color": "target"},
        label="Plot",
    )
    load_to_pca = Edge(
        source=PortRef(node_id=load.id, port_id=_out_port(load, "frame").id),
        target=PortRef(node_id=pca.id, port_id=_in_port(pca, "frame").id),
    )
    pca_to_plot = Edge(
        source=PortRef(node_id=pca.id, port_id=_out_port(pca, "result").id),
        target=PortRef(node_id=plot.id, port_id=_in_port(plot, "frame").id),
    )
    return Graph(
        nodes={load.id: load, pca.id: pca, plot.id: plot},
        edges={load_to_pca.id: load_to_pca, pca_to_plot.id: pca_to_plot},
    )


def _build_cluster_scatter_graph() -> Graph:
    load = LoadSample().instantiate(name="iris", label="Load Sample")
    cluster = ClusterDetect().instantiate(
        estimator="KMeans",
        features=_IRIS_FEATURES,
        params={"n_clusters": 3, "random_state": 0, "n_init": 10},
        label="Cluster Detect",
    )
    plot = VizPlot().instantiate(
        chart="scatter",
        encoding={"x": "sepal length (cm)", "y": "petal length (cm)", "color": "cluster"},
        label="Plot",
    )
    load_to_cluster = Edge(
        source=PortRef(node_id=load.id, port_id=_out_port(load, "frame").id),
        target=PortRef(node_id=cluster.id, port_id=_in_port(cluster, "frame").id),
    )
    cluster_to_plot = Edge(
        source=PortRef(node_id=cluster.id, port_id=_out_port(cluster, "result").id),
        target=PortRef(node_id=plot.id, port_id=_in_port(plot, "frame").id),
    )
    return Graph(
        nodes={load.id: load, cluster.id: cluster, plot.id: plot},
        edges={load_to_cluster.id: load_to_cluster, cluster_to_plot.id: cluster_to_plot},
    )


def test_pca_scatter_bridge_codegen_is_parseable_and_ruff_clean() -> None:
    _assert_parseable_and_ruff_clean(compile_to_code(_build_pca_scatter_graph()))


def test_cluster_scatter_bridge_codegen_is_parseable_and_ruff_clean() -> None:
    _assert_parseable_and_ruff_clean(compile_to_code(_build_cluster_scatter_graph()))


@pytest.mark.equivalence
def test_pca_scatter_bridge_equivalence() -> None:
    graph = _build_pca_scatter_graph()
    results = graph_execute(graph)
    executed_plot = next(out["plot"] for out in results.values() if "plot" in out)
    compiled_result = _run_compiled(graph)
    codegen_plot = next(v for v in compiled_result.values() if isinstance(v, PlotSpec))
    assert executed_plot.spec == codegen_plot.spec


@pytest.mark.equivalence
def test_cluster_scatter_bridge_equivalence() -> None:
    graph = _build_cluster_scatter_graph()
    results = graph_execute(graph)
    executed_plot = next(out["plot"] for out in results.values() if "plot" in out)
    compiled_result = _run_compiled(graph)
    codegen_plot = next(v for v in compiled_result.values() if isinstance(v, PlotSpec))
    assert executed_plot.spec == codegen_plot.spec
