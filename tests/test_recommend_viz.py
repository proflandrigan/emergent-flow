"""
Tests for the Epic 15 recommender-aware viz functions in ``emergentflow.viz`` (Story Group E).

Story 14.9 adds ``plot_precision_recall_curve``; three follow-up tasks will extend this file
with metric-comparison, coverage-vs-accuracy, and popularity-distribution tests. Keep each
function's tests in its own clearly commented section.
"""

from __future__ import annotations

import pandas as pd

from emergentflow.nodes.examples.viz_plot_coverage_vs_accuracy import VizPlotCoverageVsAccuracy
from emergentflow.nodes.examples.viz_plot_metric_comparison import VizPlotMetricComparison
from emergentflow.nodes.examples.viz_plot_popularity_distribution import (
    VizPlotPopularityDistribution,
)
from emergentflow.nodes.examples.viz_plot_precision_recall_curve import (
    VizPlotPrecisionRecallCurve,
)
from emergentflow.recommend import compare, fit
from emergentflow.recommend.interactions import InteractionMatrix
from emergentflow.viz import (
    VizError,
    plot_coverage_vs_accuracy,
    plot_metric_comparison,
    plot_popularity_distribution,
    plot_precision_recall_curve,
)
from emergentflow.viz.models import PlotSpec

# ===================================================================
# Shared fixtures
# ===================================================================


def _make_train_interactions() -> InteractionMatrix:
    """4 users x 4 items, popularity counts: A=3, B=2, C=2, D=1."""
    df = pd.DataFrame(
        {
            "user_id": [1, 1, 2, 2, 3, 3, 4, 4],
            "item_id": ["A", "B", "A", "C", "A", "D", "B", "C"],
            "value": [1, 1, 1, 1, 1, 1, 1, 1],
        }
    )
    return InteractionMatrix.from_dataframe(
        df, user_col="user_id", item_col="item_id", value_col="value"
    )


def _make_test_interactions() -> InteractionMatrix:
    """3 users, one held-out interaction each: User 1->C, User 2->D, User 3->B."""
    df = pd.DataFrame(
        {
            "user_id": [1, 2, 3],
            "item_id": ["C", "D", "B"],
            "value": [1, 1, 1],
        }
    )
    return InteractionMatrix.from_dataframe(
        df, user_col="user_id", item_col="item_id", value_col="value"
    )


def _run_codegen(definition, node, scope):
    """exec a node's preview fragment in *scope* and return the updated scope."""
    frag = definition.preview(node)
    exec(frag.render(), scope)
    return scope


# ===================================================================
# plot_precision_recall_curve (Story 14.9)
# ===================================================================


def test_plot_precision_recall_curve_returns_plot_spec():
    train = _make_train_interactions()
    recommender = fit(train, algorithm="popularity", params={})
    test_interactions = _make_test_interactions()

    result = plot_precision_recall_curve(recommender, test_interactions, k_max=5)

    assert isinstance(result, PlotSpec)
    assert result.chart == "recommend_precision_recall_curve"
    assert isinstance(result.spec, dict)
    assert result.spec
    assert "data" in result.spec


def test_plot_precision_recall_curve_rejects_non_positive_k_max():
    train = _make_train_interactions()
    recommender = fit(train, algorithm="popularity", params={})
    test_interactions = _make_test_interactions()

    try:
        plot_precision_recall_curve(recommender, test_interactions, k_max=0)
    except VizError:
        pass
    else:
        raise AssertionError("expected VizError for k_max=0")


def test_viz_plot_precision_recall_curve_node_codegen_and_execute_are_equivalent():
    train = _make_train_interactions()
    recommender = fit(train, algorithm="popularity", params={})
    test_interactions = _make_test_interactions()

    definition = VizPlotPrecisionRecallCurve()
    node = definition.instantiate(k_max=5)

    exec_result = definition.execute(
        node, {"recommender": recommender, "test_interactions": test_interactions}
    )

    scope = {"recommender": recommender, "test_interactions": test_interactions}
    _run_codegen(definition, node, scope)
    codegen_result = scope["plot"]

    assert isinstance(exec_result["plot"], PlotSpec)
    assert isinstance(codegen_result, PlotSpec)
    assert exec_result["plot"].chart == codegen_result.chart
    assert exec_result["plot"].spec == codegen_result.spec


# ===================================================================
# plot_metric_comparison (Story 14.10)
# ===================================================================


def _make_comparison() -> pd.DataFrame:
    train = _make_train_interactions()
    test_interactions = _make_test_interactions()
    rec_a = fit(train, algorithm="popularity", params={})
    rec_b = fit(train, algorithm="random", params={"seed": 0})
    return compare(test_interactions, recommenders=[rec_a, rec_b], k=5)


def test_plot_metric_comparison_returns_plot_spec():
    comparison = _make_comparison()

    result = plot_metric_comparison(comparison)

    metric_columns = [c for c in comparison.columns if c not in ("algorithm", "is_baseline")]
    assert isinstance(result, PlotSpec)
    assert result.chart == "recommend_metric_comparison"
    assert isinstance(result.spec, dict)
    assert result.spec
    assert "data" in result.spec
    assert len(result.spec["data"]) == len(metric_columns)


def test_plot_metric_comparison_with_explicit_metrics_subset():
    comparison = _make_comparison()

    result = plot_metric_comparison(comparison, metrics=["mean_ndcg_at_k"])

    assert len(result.spec["data"]) == 1


def test_plot_metric_comparison_rejects_missing_algorithm_column():
    comparison = _make_comparison().drop(columns=["algorithm"])

    try:
        plot_metric_comparison(comparison)
    except VizError:
        pass
    else:
        raise AssertionError("expected VizError for a missing 'algorithm' column")


def test_plot_metric_comparison_rejects_unknown_metric():
    comparison = _make_comparison()

    try:
        plot_metric_comparison(comparison, metrics=["not_a_real_metric"])
    except VizError:
        pass
    else:
        raise AssertionError("expected VizError for an unknown metric column")


def test_viz_plot_metric_comparison_node_codegen_and_execute_are_equivalent():
    comparison = _make_comparison()

    definition = VizPlotMetricComparison()
    node = definition.instantiate()

    exec_result = definition.execute(node, {"comparison": comparison})

    scope = {"comparison": comparison}
    _run_codegen(definition, node, scope)
    codegen_result = scope["plot"]

    assert isinstance(exec_result["plot"], PlotSpec)
    assert isinstance(codegen_result, PlotSpec)
    assert exec_result["plot"].chart == codegen_result.chart
    assert exec_result["plot"].spec == codegen_result.spec


# ===================================================================
# plot_coverage_vs_accuracy (Story 14.11)
# ===================================================================


def test_plot_coverage_vs_accuracy_returns_plot_spec():
    comparison = _make_comparison()

    result = plot_coverage_vs_accuracy(comparison)

    assert isinstance(result, PlotSpec)
    assert result.chart == "recommend_coverage_vs_accuracy"
    assert isinstance(result.spec, dict)
    assert result.spec
    assert "data" in result.spec
    assert len(result.spec["data"]) == 1
    trace = result.spec["data"][0]
    assert len(trace["x"]) == len(trace["y"]) == len(comparison)


def test_plot_coverage_vs_accuracy_with_explicit_accuracy_metric():
    comparison = _make_comparison()

    result = plot_coverage_vs_accuracy(comparison, accuracy_metric="mean_precision_at_k")

    assert isinstance(result, PlotSpec)
    assert result.chart == "recommend_coverage_vs_accuracy"


def test_plot_coverage_vs_accuracy_rejects_missing_coverage_column():
    comparison = _make_comparison().drop(columns=["coverage"])

    try:
        plot_coverage_vs_accuracy(comparison)
    except VizError:
        pass
    else:
        raise AssertionError("expected VizError for a missing 'coverage' column")


def test_plot_coverage_vs_accuracy_rejects_unknown_accuracy_metric():
    comparison = _make_comparison()

    try:
        plot_coverage_vs_accuracy(comparison, accuracy_metric="not_a_real_metric")
    except VizError:
        pass
    else:
        raise AssertionError("expected VizError for an unknown accuracy_metric column")


def test_viz_plot_coverage_vs_accuracy_node_codegen_and_execute_are_equivalent():
    comparison = _make_comparison()

    definition = VizPlotCoverageVsAccuracy()
    node = definition.instantiate()

    exec_result = definition.execute(node, {"comparison": comparison})

    scope = {"comparison": comparison}
    _run_codegen(definition, node, scope)
    codegen_result = scope["plot"]

    assert isinstance(exec_result["plot"], PlotSpec)
    assert isinstance(codegen_result, PlotSpec)
    assert exec_result["plot"].chart == codegen_result.chart
    assert exec_result["plot"].spec == codegen_result.spec


# ===================================================================
# plot_popularity_distribution (Story 14.12)
# ===================================================================


def _make_distinct_popularity_interactions() -> InteractionMatrix:
    """4 users x 4 items, popularity counts: A=4, B=3, C=2, D=1 (all distinct, no ties)."""
    df = pd.DataFrame(
        {
            "user_id": [1, 2, 3, 4, 1, 2, 3, 1, 2, 1],
            "item_id": ["A", "A", "A", "A", "B", "B", "B", "C", "C", "D"],
            "value": [1] * 10,
        }
    )
    return InteractionMatrix.from_dataframe(
        df, user_col="user_id", item_col="item_id", value_col="value"
    )


def test_plot_popularity_distribution_returns_plot_spec():
    train = _make_train_interactions()
    recommender = fit(train, algorithm="popularity", params={})

    result = plot_popularity_distribution(recommender, train, n=3)

    assert isinstance(result, PlotSpec)
    assert result.chart == "recommend_popularity_distribution"
    assert isinstance(result.spec, dict)
    assert result.spec
    assert "data" in result.spec
    assert len(result.spec["data"]) == 1
    trace = result.spec["data"][0]
    assert len(trace["x"]) == len(trace["y"]) == train.n_items


def test_plot_popularity_distribution_rank_order_matches_popularity_by_hand():
    # By-hand popularity counts (see _make_distinct_popularity_interactions): A=4, B=3, C=2, D=1.
    # Ranking by descending count (rank 1 = most popular): A=1, B=2, C=3, D=4.
    interactions = _make_distinct_popularity_interactions()
    recommender = fit(interactions, algorithm="popularity", params={})

    result = plot_popularity_distribution(recommender, interactions, n=2)

    trace = result.spec["data"][0]
    assert trace["x"] == [1, 2, 3, 4]


def test_plot_popularity_distribution_rejects_non_positive_n():
    train = _make_train_interactions()
    recommender = fit(train, algorithm="popularity", params={})

    try:
        plot_popularity_distribution(recommender, train, n=0)
    except VizError:
        pass
    else:
        raise AssertionError("expected VizError for n=0")


def test_viz_plot_popularity_distribution_node_codegen_and_execute_are_equivalent():
    train = _make_train_interactions()
    recommender = fit(train, algorithm="popularity", params={})

    definition = VizPlotPopularityDistribution()
    node = definition.instantiate(n=3)

    exec_result = definition.execute(node, {"recommender": recommender, "interactions": train})

    scope = {"recommender": recommender, "interactions": train}
    _run_codegen(definition, node, scope)
    codegen_result = scope["plot"]

    assert isinstance(exec_result["plot"], PlotSpec)
    assert isinstance(codegen_result, PlotSpec)
    assert exec_result["plot"].chart == codegen_result.chart
    assert exec_result["plot"].spec == codegen_result.spec
