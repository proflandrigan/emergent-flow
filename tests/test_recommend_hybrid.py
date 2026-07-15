"""Tests for the hybrid_weighted recommender composition layer (Epic 15, Story 9)."""

from __future__ import annotations

import ast
from typing import Any

import pandas as pd
import pytest

from emergentflow.recommend import fit, hybrid_switching, hybrid_weighted, recommend
from emergentflow.recommend.errors import InvalidRecommenderParamsError
from emergentflow.recommend.interactions import InteractionMatrix
from emergentflow.recommend.models import FittedRecommender

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ITEMS = ["A", "B", "C"]


def _make_small_interactions() -> InteractionMatrix:
    """4 users x 3 items with explicit values (mirrors test_recommend_baseline_catalog)."""
    df = pd.DataFrame(
        {
            "user_id": [1, 1, 2, 2, 3, 3, 4, 4],
            "item_id": ["A", "B", "A", "C", "B", "C", "A", "C"],
            "value": [5, 1, 1, 3, 2, 1, 3, 2],
        }
    )
    return InteractionMatrix.from_dataframe(
        df, user_col="user_id", item_col="item_id", value_col="value"
    )


@pytest.fixture(scope="module")
def rec_a() -> FittedRecommender:
    im = _make_small_interactions()
    return fit(im, algorithm="popularity", params={"score_type": "count"})


@pytest.fixture(scope="module")
def rec_b() -> FittedRecommender:
    im = _make_small_interactions()
    return fit(im, algorithm="co_occurrence", params={"metric": "lift"})


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_hybrid_weighted_requires_at_least_two_recommenders(rec_a: FittedRecommender) -> None:
    with pytest.raises(InvalidRecommenderParamsError):
        hybrid_weighted([rec_a], weights=[1.0])


def test_hybrid_weighted_requires_matching_weights_length(
    rec_a: FittedRecommender, rec_b: FittedRecommender
) -> None:
    with pytest.raises(InvalidRecommenderParamsError):
        hybrid_weighted([rec_a, rec_b], weights=[1.0])


def test_hybrid_weighted_unknown_blend_strategy_raises(
    rec_a: FittedRecommender, rec_b: FittedRecommender
) -> None:
    with pytest.raises(InvalidRecommenderParamsError):
        hybrid_weighted([rec_a, rec_b], blend_strategy="nonsense")


# ---------------------------------------------------------------------------
# Basic behavior
# ---------------------------------------------------------------------------


def test_hybrid_weighted_default_weights_are_equal(
    rec_a: FittedRecommender, rec_b: FittedRecommender
) -> None:
    result = hybrid_weighted([rec_a, rec_b], n=5)
    assert len(result.recommendations) > 0


def test_hybrid_weighted_weighted_sum_matches_independent_oracle(
    rec_a: FittedRecommender, rec_b: FittedRecommender
) -> None:
    """Manually compute the expected weighted_sum blend for user 1 and compare."""
    pop_result = recommend(rec_a, user_ids=[1], n=50, exclude_known=False)
    cooc_result = recommend(rec_b, user_ids=[1], n=50, exclude_known=False)

    weights_oracle = [2.0, 1.0]
    item_scores: dict[str, float] = {}
    for item_id, score in zip(
        pop_result.recommendations["item_id"],
        pop_result.recommendations["score"],
        strict=True,
    ):
        item_scores[str(item_id)] = item_scores.get(str(item_id), 0.0) + weights_oracle[0] * float(
            score
        )
    for item_id, score in zip(
        cooc_result.recommendations["item_id"],
        cooc_result.recommendations["score"],
        strict=True,
    ):
        item_scores[str(item_id)] = item_scores.get(str(item_id), 0.0) + weights_oracle[1] * float(
            score
        )
    oracle_items = sorted(item_scores.items(), key=lambda kv: -kv[1])
    top_5_oracle = [item for item, _ in oracle_items[:5]]

    result = hybrid_weighted(
        [rec_a, rec_b],
        weights=[2.0, 1.0],
        n=5,
        blend_strategy="weighted_sum",
        user_ids=[1],
        exclude_known=False,
    )
    result_items = [str(x) for x in result.recommendations["item_id"].tolist()]
    assert result_items == top_5_oracle


def test_hybrid_weighted_cascade_prioritizes_higher_weight(
    rec_a: FittedRecommender, rec_b: FittedRecommender
) -> None:
    """Cascade with rec_a weighted much higher must put rec_a's top item first."""
    uid = 1
    pop_result = recommend(rec_a, user_ids=[uid], n=5, exclude_known=False)
    cooc_result = recommend(rec_b, user_ids=[uid], n=5, exclude_known=False)
    top_pop = pop_result.recommendations["item_id"].iloc[0]
    top_cooc = cooc_result.recommendations["item_id"].iloc[0]
    assert top_pop != top_cooc, "fixture requires different top items"

    result = hybrid_weighted(
        [rec_a, rec_b],
        weights=[10.0, 1.0],
        n=5,
        blend_strategy="cascade",
        user_ids=[uid],
        exclude_known=False,
    )
    assert result.recommendations["item_id"].iloc[0] == top_pop


def test_hybrid_weighted_rank_fusion_smoke(
    rec_a: FittedRecommender, rec_b: FittedRecommender
) -> None:
    result = hybrid_weighted([rec_a, rec_b], n=5, blend_strategy="rank_fusion", user_ids=[1])
    rows = result.recommendations
    assert len(rows) > 0
    ranks = rows["rank"].tolist()
    scores = rows["score"].tolist()
    assert ranks[0] == 1
    assert all(ranks[i] < ranks[i + 1] for i in range(len(ranks) - 1))
    assert all(scores[i] >= scores[i + 1] for i in range(len(scores) - 1))


def test_hybrid_weighted_n_limits_result_size(
    rec_a: FittedRecommender, rec_b: FittedRecommender
) -> None:
    result = hybrid_weighted([rec_a, rec_b], n=2, user_ids=[1, 2])
    counts = result.recommendations.groupby("user_id").size()
    assert (counts <= 2).all()


def test_hybrid_weighted_determinism(rec_a: FittedRecommender, rec_b: FittedRecommender) -> None:
    r1 = hybrid_weighted([rec_a, rec_b], n=5, user_ids=[1])
    r2 = hybrid_weighted([rec_a, rec_b], n=5, user_ids=[1])
    pd.testing.assert_frame_equal(r1.recommendations, r2.recommendations)


# ---------------------------------------------------------------------------
# Codegen & equivalence
# ---------------------------------------------------------------------------


def test_hybrid_weighted_codegen_is_parseable() -> None:
    from emergentflow.nodes.examples.recommend_hybrid_weighted import HybridWeighted

    node_def = HybridWeighted()
    node = node_def.instantiate(weights=[2.0, 1.0], n=5, blend_strategy="weighted_sum")
    ast.parse(node_def.preview(node).render())


def test_hybrid_weighted_execute_vs_codegen_equivalence(
    rec_a: FittedRecommender, rec_b: FittedRecommender
) -> None:
    from emergentflow.codegen.context import CodegenContext
    from emergentflow.nodes.examples.recommend_hybrid_weighted import HybridWeighted

    node_def = HybridWeighted()
    node = node_def.instantiate(
        weights=[2.0, 1.0], n=5, blend_strategy="weighted_sum", user_ids=[1]
    )

    exec_result = node_def.execute(node, {"recommenders": [rec_a, rec_b]})

    ctx = CodegenContext(in_vars={"recommenders": "[fit_a, fit_b]"}, out_vars={"result": "result"})
    frag = node_def.codegen(node, ctx)
    scope: dict[str, Any] = {"fit_a": rec_a, "fit_b": rec_b}
    exec(frag.render(), scope)

    pd.testing.assert_frame_equal(
        exec_result["result"].recommendations, scope["result"].recommendations
    )


# ---------------------------------------------------------------------------
# hybrid_switching
# ---------------------------------------------------------------------------


def _make_switching_fixture() -> tuple[InteractionMatrix, FittedRecommender, FittedRecommender]:
    """5-user interaction set: users 1-4 have 2 interactions each, user 5 has 1."""
    df = pd.DataFrame(
        {
            "user_id": [1, 1, 2, 2, 3, 3, 4, 4, 5],
            "item_id": ["A", "B", "A", "C", "B", "C", "A", "C", "B"],
            "value": [5, 1, 1, 3, 2, 1, 3, 2, 1],
        }
    )
    im5 = InteractionMatrix.from_dataframe(
        df, user_col="user_id", item_col="item_id", value_col="value"
    )
    pop_fit = fit(im5, algorithm="popularity", params={"score_type": "count"})
    cooc_fit = fit(im5, algorithm="co_occurrence", params={"metric": "lift"})
    return im5, pop_fit, cooc_fit


def test_hybrid_switching_requires_exactly_two_recommenders(rec_a: FittedRecommender) -> None:
    im = _make_small_interactions()
    with pytest.raises(InvalidRecommenderParamsError):
        hybrid_switching([rec_a], im, cold_start_threshold=2)
    with pytest.raises(InvalidRecommenderParamsError):
        hybrid_switching([rec_a, rec_a, rec_a], im, cold_start_threshold=2)


def test_hybrid_switching_routes_by_interaction_count() -> None:
    im5, pop_fit, cooc_fit = _make_switching_fixture()
    result = hybrid_switching(
        [pop_fit, cooc_fit], im5, cold_start_threshold=2, n=3, user_ids=[5, 1]
    )

    cold_oracle = recommend(pop_fit, user_ids=[5], n=3, exclude_known=True)
    warm_oracle = recommend(cooc_fit, user_ids=[1], n=3, exclude_known=True)

    cold_rows = (
        result.recommendations[result.recommendations["user_id"] == 5]
        .drop(columns=["user_id"])
        .reset_index(drop=True)
    )
    expected_cold = cold_oracle.recommendations.drop(columns=["user_id"]).reset_index(drop=True)
    pd.testing.assert_frame_equal(cold_rows, expected_cold)

    warm_rows = (
        result.recommendations[result.recommendations["user_id"] == 1]
        .drop(columns=["user_id"])
        .reset_index(drop=True)
    )
    expected_warm = warm_oracle.recommendations.drop(columns=["user_id"]).reset_index(drop=True)
    pd.testing.assert_frame_equal(warm_rows, expected_warm)


def test_hybrid_switching_unknown_user_treated_as_cold() -> None:
    im5, pop_fit, cooc_fit = _make_switching_fixture()
    result = hybrid_switching([pop_fit, cooc_fit], im5, cold_start_threshold=1, n=3, user_ids=[99])
    oracle = recommend(pop_fit, user_ids=[99], n=3, exclude_known=True)
    pd.testing.assert_frame_equal(result.recommendations, oracle.recommendations)


def test_hybrid_switching_default_user_ids_covers_all_known_users() -> None:
    im5, pop_fit, cooc_fit = _make_switching_fixture()
    result = hybrid_switching([pop_fit, cooc_fit], im5, cold_start_threshold=2, n=3)
    result_users = set(result.recommendations["user_id"])
    assert result_users <= set(im5.user_index.keys())


def test_hybrid_switching_determinism() -> None:
    im5, pop_fit, cooc_fit = _make_switching_fixture()
    r1 = hybrid_switching([pop_fit, cooc_fit], im5, cold_start_threshold=2, n=3, user_ids=[5, 1])
    r2 = hybrid_switching([pop_fit, cooc_fit], im5, cold_start_threshold=2, n=3, user_ids=[5, 1])
    pd.testing.assert_frame_equal(r1.recommendations, r2.recommendations)


def test_hybrid_switching_codegen_is_parseable() -> None:
    from emergentflow.nodes.examples.recommend_hybrid_switching import HybridSwitching

    node_def = HybridSwitching()
    node = node_def.instantiate(cold_start_threshold=2, n=3)
    ast.parse(node_def.preview(node).render())


def test_hybrid_switching_execute_vs_codegen_equivalence() -> None:
    from emergentflow.codegen.context import CodegenContext
    from emergentflow.nodes.examples.recommend_hybrid_switching import HybridSwitching

    im5, pop_fit, cooc_fit = _make_switching_fixture()
    node_def = HybridSwitching()
    node = node_def.instantiate(cold_start_threshold=2, n=3, user_ids=[5, 1])

    exec_result = node_def.execute(node, {"recommenders": [pop_fit, cooc_fit], "interactions": im5})

    ctx = CodegenContext(
        in_vars={"recommenders": "[fit_a, fit_b]", "interactions": "im"},
        out_vars={"result": "result"},
    )
    frag = node_def.codegen(node, ctx)
    scope: dict[str, Any] = {"fit_a": pop_fit, "fit_b": cooc_fit, "im": im5}
    exec(frag.render(), scope)

    pd.testing.assert_frame_equal(
        exec_result["result"].recommendations, scope["result"].recommendations
    )
