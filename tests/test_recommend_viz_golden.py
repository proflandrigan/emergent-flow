"""
Epic 15 Story 14 -- golden + equivalence tests for the four recommender-aware viz nodes
(Story Group E), the last bullet of Story 14: "Golden + equivalence via the Story 13 harness on
fixtures that produce fitted recommenders first (so the plot node's input is a real
EvalResult/DataFrame, not a stub)."

``tests/test_recommend_viz.py`` already covers per-node codegen/execute equivalence for each of
the four viz nodes (``VizPlotPrecisionRecallCurve``, ``VizPlotMetricComparison``,
``VizPlotCoverageVsAccuracy``, ``VizPlotPopularityDistribution``) using real fitted
recommenders. This file adds the piece that was still missing: one real, hand-wired
multi-node ``Graph`` that wires all four viz nodes together downstream of real
``RecommendFit``/``RecommendCompare`` nodes, mirroring the golden-graph pattern in
``tests/test_recommend_golden_generated_code.py`` (Story 13.8) -- verified ``ast.parse``-clean,
``ruff``-clean, and importable/runnable -- plus an execute()-vs-compiled-code equivalence check
on that same graph's four ``PlotSpec`` outputs, mirroring the Story 13.6 cross-registry
equivalence harness's "keyed on the inspectable output" approach.
"""

from __future__ import annotations

import ast
import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from emergentflow.codegen.compiler import compile_to_code
from emergentflow.codegen.executor import execute
from emergentflow.ir.common import Direction
from emergentflow.ir.edge import Edge, PortRef
from emergentflow.ir.graph import Graph
from emergentflow.nodes.examples import (
    LoadSample,
    PrepareInteractions,
    RecommendCompare,
    RecommendFit,
)
from emergentflow.nodes.examples.viz_plot_coverage_vs_accuracy import VizPlotCoverageVsAccuracy
from emergentflow.nodes.examples.viz_plot_metric_comparison import VizPlotMetricComparison
from emergentflow.nodes.examples.viz_plot_popularity_distribution import (
    VizPlotPopularityDistribution,
)
from emergentflow.nodes.examples.viz_plot_precision_recall_curve import (
    VizPlotPrecisionRecallCurve,
)
from emergentflow.viz.models import PlotSpec


def _out_port(node, name):
    return next(p for p in node.ports if p.direction == Direction.OUT and p.name == name)


def _in_port(node, name):
    return next(p for p in node.ports if p.direction == Direction.IN and p.name == name)


def _edge(source_node, source_port, target_node, target_port) -> Edge:
    return Edge(
        source=PortRef(node_id=source_node.id, port_id=_out_port(source_node, source_port).id),
        target=PortRef(node_id=target_node.id, port_id=_in_port(target_node, target_port).id),
    )


def _assert_ruff_clean(code: str) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "-"],
        input=code,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _assert_importable_and_runs(code: str) -> None:
    """Write the compiled module to a temp .py file, import it, and call its main() -- proves
    the generated code is not just syntactically valid but actually runs end-to-end."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        module_path = Path(tmp_dir) / "generated_module.py"
        module_path.write_text(code, encoding="utf-8")
        spec = importlib.util.spec_from_file_location("generated_module", module_path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # import-time execution only (module-level code)
        results = module.main()
        assert isinstance(results, dict)
        assert results  # at least one output var


def _build_viz_graph() -> Graph:
    """load_sample(iris) -> prepare_interactions -> recommend.fit (popularity + random)
    -> recommend.compare -> {plot_metric_comparison, plot_coverage_vs_accuracy}

    The popularity-algorithm fit's recommender, plus the SAME prepare_interactions output, also
    fan out into plot_precision_recall_curve and plot_popularity_distribution.

    NOTE: prepare_interactions' single InteractionMatrix output is reused as both the fit-time
    training interactions AND the "held-out" test_interactions/interactions ports below (for
    recommend.compare, plot_precision_recall_curve, and plot_popularity_distribution). This is
    not a statistically rigorous train/test split -- it's fine here since this test proves the
    CODE compiles/runs and execute()/codegen agree, not model quality (mirrors Story 13.8's
    golden test, which similarly reuses one data source in more than one role).
    """
    load = LoadSample().instantiate(name="iris", label="Load Sample")
    prepare = PrepareInteractions().instantiate(
        label="Prepare Interactions",
        user_col="sepal length (cm)",
        item_col="sepal width (cm)",
    )
    fit_pop = RecommendFit().instantiate(label="Fit Popularity", algorithm="popularity", params={})
    fit_rand = RecommendFit().instantiate(
        label="Fit Random", algorithm="random", params={"seed": 0}
    )
    compare = RecommendCompare().instantiate(label="Compare", k=5)
    pr_curve = VizPlotPrecisionRecallCurve().instantiate(label="Precision-Recall Curve", k_max=5)
    metric_bar = VizPlotMetricComparison().instantiate(label="Metric Comparison")
    coverage_scatter = VizPlotCoverageVsAccuracy().instantiate(label="Coverage vs. Accuracy")
    popularity_hist = VizPlotPopularityDistribution().instantiate(
        label="Popularity Distribution", n=5
    )

    nodes = {
        n.id: n
        for n in (
            load,
            prepare,
            fit_pop,
            fit_rand,
            compare,
            pr_curve,
            metric_bar,
            coverage_scatter,
            popularity_hist,
        )
    }
    edges = [
        _edge(load, "frame", prepare, "frame"),
        _edge(prepare, "interactions", fit_pop, "interactions"),
        _edge(prepare, "interactions", fit_rand, "interactions"),
        _edge(fit_pop, "recommender", compare, "recommenders"),
        _edge(fit_rand, "recommender", compare, "recommenders"),
        _edge(prepare, "interactions", compare, "test_interactions"),
        _edge(compare, "result", metric_bar, "comparison"),
        _edge(compare, "result", coverage_scatter, "comparison"),
        _edge(fit_pop, "recommender", pr_curve, "recommender"),
        _edge(prepare, "interactions", pr_curve, "test_interactions"),
        _edge(fit_pop, "recommender", popularity_hist, "recommender"),
        _edge(prepare, "interactions", popularity_hist, "interactions"),
    ]
    return Graph(nodes=nodes, edges={e.id: e for e in edges})


@pytest.mark.equivalence
def test_recommend_viz_golden_generated_code() -> None:
    code = compile_to_code(_build_viz_graph())
    ast.parse(code)
    _assert_ruff_clean(code)
    _assert_importable_and_runs(code)


@pytest.mark.equivalence
def test_recommend_viz_execute_vs_codegen_equivalence() -> None:
    graph = _build_viz_graph()
    exec_results = execute(graph)

    code = compile_to_code(graph)
    with tempfile.TemporaryDirectory() as tmp_dir:
        module_path = Path(tmp_dir) / "generated_module.py"
        module_path.write_text(code, encoding="utf-8")
        spec = importlib.util.spec_from_file_location("generated_module", module_path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        codegen_results = module.main()

    # execute()'s return shape is {node_id: {out_port_name: value}} while the compiled module's
    # main() returns a flat {var_name: value} -- the two key spaces are unrelated (node ids vs.
    # naming.py-generated variable names), so match up the 4 PlotSpec outputs by VALUE TYPE
    # (PlotSpec instances) and then by each plot's own ``.chart`` key (a fixed, distinct string
    # per viz node in this graph), not by guessing exact auto-generated variable/node-id
    # strings -- mirroring the Story 13.6 cross-registry harness's "keyed on the inspectable
    # output" approach.
    exec_plots_by_chart = {
        v.chart: v
        for outputs in exec_results.values()
        for v in outputs.values()
        if isinstance(v, PlotSpec)
    }
    codegen_plots_by_chart = {
        v.chart: v for v in codegen_results.values() if isinstance(v, PlotSpec)
    }

    assert len(exec_plots_by_chart) == 4, (
        f"expected 4 PlotSpec outputs, got {list(exec_plots_by_chart)}"
    )
    assert exec_plots_by_chart.keys() == codegen_plots_by_chart.keys()

    for chart in exec_plots_by_chart:
        assert exec_plots_by_chart[chart].spec == codegen_plots_by_chart[chart].spec, chart
