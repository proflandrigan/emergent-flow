"""
Tests for ef.recommend.evaluate and the ranking-metric helpers in
emergentflow.recommend.metrics (Epic 15, Story 12.1).

Structure mirrors tests/test_recommend_baseline_catalog.py: small hand-verified
fixtures, direct spec.fitter/spec.recommend_fn calls for the algorithm under
test, and the same import conventions.
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from emergentflow.recommend import compare, evaluate
from emergentflow.recommend.errors import InvalidRecommenderParamsError
from emergentflow.recommend.interactions import InteractionMatrix
from emergentflow.recommend.metrics import (
    _average_precision_at_k,
    _hit,
    _ndcg_at_k,
    _precision_at_k,
    _recall_at_k,
)
from emergentflow.recommend.models import EvalResult
from emergentflow.recommend.registry import get_recommender_spec

# ===================================================================
# Fixtures
# ===================================================================

# 4 users x 4 items with uniform values.
# Popularity (count): A=3, B=2, C=2, D=1
ITEMS = ["A", "B", "C", "D"]


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


def _make_fitted_popularity() -> tuple:
    """Fit a popularity recommender on the train set and return it plus the train IM."""
    train = _make_train_interactions()
    spec = get_recommender_spec("popularity")
    recommender = spec.fitter(train, None, {"score_type": "count"})
    return recommender, train


# ===================================================================
# Metric helper unit tests
# ===================================================================


class TestPrecisionAtK:
    def test_all_relevant(self):
        assert _precision_at_k(["A", "B", "C"], {"A", "B", "C"}, 3) == 1.0

    def test_half_relevant(self):
        assert _precision_at_k(["A", "B", "C", "D"], {"A", "B"}, 4) == 0.5

    def test_none_relevant(self):
        assert _precision_at_k(["A", "B"], {"C"}, 2) == 0.0

    def test_k_zero_returns_zero(self):
        assert _precision_at_k(["A", "B"], {"A"}, 0) == 0.0

    def test_k_negative_returns_zero(self):
        assert _precision_at_k(["A", "B"], {"A"}, -1) == 0.0

    def test_empty_recommended(self):
        assert _precision_at_k([], {"A"}, 10) == 0.0


class TestRecallAtK:
    def test_all_relevant_recalled(self):
        assert _recall_at_k(["A", "B"], {"A", "B"}, 2) == 1.0

    def test_half_relevant_recalled(self):
        assert _recall_at_k(["A", "B"], {"A", "C"}, 2) == 0.5

    def test_no_relevant_recalled(self):
        assert _recall_at_k(["A", "B"], {"C"}, 2) == 0.0

    def test_empty_relevant_returns_zero(self):
        assert _recall_at_k(["A", "B"], set(), 2) == 0.0

    def test_k_zero_returns_zero(self):
        assert _recall_at_k(["A"], {"A"}, 0) == 0.0

    def test_k_larger_than_recommended(self):
        # len(recommended) < k, so only the available items are evaluated
        assert _recall_at_k(["A"], {"A", "B"}, 5) == 0.5


class TestNdcgAtK:
    def test_perfect_ordering(self):
        # DCG = 1/log2(2) + 1/log2(3) = 1 + 0.6309 = 1.6309
        # IDCG = same = 1.6309
        # NDCG = 1.0
        result = _ndcg_at_k(["A", "B"], {"A", "B"}, 2)
        assert result == pytest.approx(1.0)

    def test_partial_ordering(self):
        # recommended = [A, B], relevant = {A}
        # DCG = 1/log2(2) + 0 = 1.0
        # IDCG = 1/log2(2) = 1.0  (only 1 relevant item, ideal is it first)
        # NDCG = 1.0 / 1.0 = 1.0
        result = _ndcg_at_k(["A", "B"], {"A"}, 2)
        assert result == pytest.approx(1.0)

    def test_wrong_order_penalized(self):
        # recommended = [B, A], relevant = {A}
        # DCG = 0/log2(2) + 1/log2(3) = 0.6309
        # IDCG = 1/log2(2) + 0 = 1.0  (only 1 relevant, ideal is it first)
        # NDCG = 0.6309 / 1.0 = 0.6309
        result = _ndcg_at_k(["B", "A"], {"A"}, 2)
        assert result == pytest.approx(1.0 / math.log2(3))

    def test_no_relevant_returns_zero(self):
        assert _ndcg_at_k(["A", "B"], {"C"}, 2) == 0.0

    def test_k_zero_returns_zero(self):
        assert _ndcg_at_k(["A"], {"A"}, 0) == 0.0

    def test_empty_relevant_returns_zero(self):
        assert _ndcg_at_k(["A", "B"], set(), 2) == 0.0


class TestHit:
    def test_hit(self):
        assert _hit(["A", "B"], {"A"}, 2) == 1.0

    def test_no_hit(self):
        assert _hit(["A", "B"], {"C"}, 2) == 0.0

    def test_hit_at_position_2(self):
        assert _hit(["A", "B", "C"], {"C"}, 10) == 1.0

    def test_k_zero_returns_zero(self):
        assert _hit(["A"], {"A"}, 0) == 0.0

    def test_empty_relevant_returns_zero(self):
        assert _hit(["A", "B"], set(), 2) == 0.0


class TestAveragePrecisionAtK:
    def test_all_relevant_in_order(self):
        # recommended = [A, B, C], relevant = {A, B}, k=3, denom=min(3,2)=2
        # i=1: A relevant, P@1 = 1/1 = 1.0
        # i=2: B relevant, P@2 = 2/2 = 1.0
        # i=3: C not relevant
        # AP = (1.0 + 1.0) / 2 = 1.0
        result = _average_precision_at_k(["A", "B", "C"], {"A", "B"}, 3)
        assert result == pytest.approx(1.0)

    def test_one_relevant_at_rank_2(self):
        # recommended = [A, B], relevant = {B}, k=2, denom=min(2,1)=1
        # i=1: A not relevant
        # i=2: B relevant, P@2 = 1/2 = 0.5
        # AP = 0.5 / 1 = 0.5
        result = _average_precision_at_k(["A", "B"], {"B"}, 2)
        assert result == pytest.approx(0.5)

    def test_multiple_relevant_interleaved(self):
        # recommended = [A, B, C, D], relevant = {B, D}, k=4, denom=min(4,2)=2
        # i=1: A not relevant
        # i=2: B relevant, P@2 = 1/2 = 0.5
        # i=3: C not relevant
        # i=4: D relevant, P@4 = 2/4 = 0.5
        # AP = (0.5 + 0.5) / 2 = 0.5
        result = _average_precision_at_k(["A", "B", "C", "D"], {"B", "D"}, 4)
        assert result == pytest.approx(0.5)

    def test_no_relevant_returns_zero(self):
        assert _average_precision_at_k(["A", "B"], {"C"}, 2) == 0.0

    def test_k_zero_returns_zero(self):
        assert _average_precision_at_k(["A"], {"A"}, 0) == 0.0

    def test_empty_relevant_returns_zero(self):
        assert _average_precision_at_k(["A", "B"], set(), 2) == 0.0


# ===================================================================
# evaluate() integration tests
# ===================================================================


def test_evaluate_returns_eval_result():
    recommender, _ = _make_fitted_popularity()
    test = _make_test_interactions()
    result = evaluate(recommender, test, k=2)
    assert isinstance(result, EvalResult)
    assert result.algorithm == "popularity"
    assert result.k == 2
    assert isinstance(result.per_user, pd.DataFrame)
    assert isinstance(result.aggregate, dict)


def test_evaluate_metrics_by_hand():
    """Verify evaluate() output matches hand-computed values.

    Training (popularity count): A=3, B=2, C=2, D=1
    Items sorted by descending popularity: A(index=0,score=3), B(1,2), C(2,2), D(3,1)

    Top-2 recommendations with exclude_known=True:
      User 1 (known: A,B): [C, D]
      User 2 (known: A,C): [B, D]
      User 3 (known: A,D): [B, C]

    Relevant (held-out) per user: U1={C}, U2={D}, U3={B}

    User 1: recommended=[C,D], relevant={C}
      P@2=1/2=0.5, R@2=1/1=1.0, NDCG@2=1/1+0=1.0, Hit=1.0
      AP@2: P@rank1=1/1=1.0 (C at i=1 -- relevant), denom=min(2,1)=1 -> 1.0

    User 2: recommended=[B,D], relevant={D}
      P@2=1/2=0.5, R@2=1/1=1.0, NDCG@2=0/1+1/log2(3)=0.6309, Hit=1.0
      AP@2: P@rank2=1/2=0.5 (D at i=2 -- relevant), denom=min(2,1)=1 -> 0.5

    User 3: recommended=[B,C], relevant={B}
      P@2=1/2=0.5, R@2=1/1=1.0, NDCG@2=1/1+0=1.0, Hit=1.0
      AP@2: P@rank1=1/1=1.0 (B at i=1 -- relevant), denom=min(2,1)=1 -> 1.0

    Aggregates:
      mean_precision_at_k = (0.5+0.5+0.5)/3 = 0.5
      mean_recall_at_k = (1+1+1)/3 = 1.0
      mean_ndcg_at_k = (1.0+1/log2(3)+1.0)/3 = 2.6309.../3 ~ 0.8770
      hit_rate = (1+1+1)/3 = 1.0
      map_at_k = (1.0+0.5+1.0)/3 = 2.5/3 ~ 0.8333
    """
    recommender, _ = _make_fitted_popularity()
    test = _make_test_interactions()
    result = evaluate(recommender, test, k=2)

    # Aggregate checks
    assert result.aggregate["mean_precision_at_k"] == pytest.approx(0.5)
    assert result.aggregate["mean_recall_at_k"] == pytest.approx(1.0)
    user2_ndcg = 1.0 / math.log2(3)
    assert result.aggregate["mean_ndcg_at_k"] == pytest.approx((1.0 + user2_ndcg + 1.0) / 3)
    assert result.aggregate["hit_rate"] == pytest.approx(1.0)
    assert result.aggregate["map_at_k"] == pytest.approx(2.5 / 3)

    # Per-user checks
    pu = result.per_user.set_index("user_id")
    assert pu.loc[1, "precision_at_k"] == pytest.approx(0.5)
    assert pu.loc[1, "recall_at_k"] == pytest.approx(1.0)
    assert pu.loc[1, "ndcg_at_k"] == pytest.approx(1.0)
    assert pu.loc[1, "hit"] == pytest.approx(1.0)
    assert pu.loc[1, "average_precision"] == pytest.approx(1.0)

    assert pu.loc[2, "precision_at_k"] == pytest.approx(0.5)
    assert pu.loc[2, "recall_at_k"] == pytest.approx(1.0)
    assert pu.loc[2, "ndcg_at_k"] == pytest.approx(user2_ndcg)
    assert pu.loc[2, "hit"] == pytest.approx(1.0)
    assert pu.loc[2, "average_precision"] == pytest.approx(0.5)

    assert pu.loc[3, "precision_at_k"] == pytest.approx(0.5)
    assert pu.loc[3, "recall_at_k"] == pytest.approx(1.0)
    assert pu.loc[3, "ndcg_at_k"] == pytest.approx(1.0)
    assert pu.loc[3, "hit"] == pytest.approx(1.0)
    assert pu.loc[3, "average_precision"] == pytest.approx(1.0)


def test_evaluate_subset_metrics():
    """metrics=['precision_at_k'] returns per_user with only user_id + precision_at_k."""
    recommender, _ = _make_fitted_popularity()
    test = _make_test_interactions()
    result = evaluate(recommender, test, k=2, metrics=["precision_at_k"])

    assert list(result.per_user.columns) == ["user_id", "precision_at_k"]
    assert list(result.aggregate.keys()) == ["mean_precision_at_k"]


def test_evaluate_unknown_metric():
    """An unknown metric name raises InvalidRecommenderParamsError."""
    recommender, _ = _make_fitted_popularity()
    test = _make_test_interactions()
    with pytest.raises(InvalidRecommenderParamsError):
        evaluate(recommender, test, k=2, metrics=["unknown_metric"])


def test_evaluate_k_zero():
    """k=0 raises InvalidRecommenderParamsError."""
    recommender, _ = _make_fitted_popularity()
    test = _make_test_interactions()
    with pytest.raises(InvalidRecommenderParamsError):
        evaluate(recommender, test, k=0)


def test_evaluate_empty_test_set():
    """Empty test interactions produce 0.0 aggregates, not NaN."""
    recommender, _ = _make_fitted_popularity()
    empty_test = InteractionMatrix.from_dataframe(
        pd.DataFrame(columns=["user_id", "item_id", "value"]),
        user_col="user_id",
        item_col="item_id",
        value_col="value",
    )
    result = evaluate(recommender, empty_test, k=2)

    assert len(result.per_user) == 0
    assert list(result.per_user.columns) == ["user_id"]
    assert result.aggregate["mean_precision_at_k"] == 0.0
    assert result.aggregate["mean_recall_at_k"] == 0.0
    assert result.aggregate["mean_ndcg_at_k"] == 0.0
    assert result.aggregate["hit_rate"] == 0.0
    assert result.aggregate["map_at_k"] == 0.0
    assert result.aggregate["coverage"] == 0.0
    assert result.aggregate["diversity"] == 0.0
    assert result.aggregate["novelty"] == 0.0


# ===================================================================
# System-level metric tests (coverage, diversity, novelty)
# ===================================================================


def test_system_coverage():
    """Coverage: fraction of catalog items appearing in any user's top-k.

    Existing fixtures produce:
      User 1: [C, D]  (exclude A,B from popular items)
      User 2: [B, D]  (exclude A,C)
      User 3: [B, C]  (exclude A,D)

    recommended_union = {B, C, D}, test_interactions.n_items = 3
    coverage = 3 / 3 = 1.0
    """
    recommender, _ = _make_fitted_popularity()
    test = _make_test_interactions()
    result = evaluate(recommender, test, k=2, metrics=["coverage"])

    # Only coverage should be in aggregate; per_user has only user_id
    assert list(result.aggregate.keys()) == ["coverage"]
    assert list(result.per_user.columns) == ["user_id"]
    assert result.aggregate["coverage"] == 1.0


def test_system_diversity():
    """Diversity = 1 - mean pairwise cosine similarity of users' top-k sets.

    Existing fixtures produce top-2 sets:
      User 1: {C, D}
      User 2: {B, D}
      User 3: {B, C}

    Pairwise cosine similarities (binary sets):
      ({C,D}, {B,D}): |intersection|/|D| = 1/2 -> |{D}|=1, denom=2, sim=0.5
      ({C,D}, {B,C}): |{C}|=1,  denom=2, sim=0.5
      ({B,D}, {B,C}): |{B}|=1,  denom=2, sim=0.5
    mean_sim = (0.5+0.5+0.5)/3 = 0.5
    diversity = 1 - 0.5 = 0.5
    """
    recommender, _ = _make_fitted_popularity()
    test = _make_test_interactions()
    result = evaluate(recommender, test, k=2, metrics=["diversity"])

    assert list(result.aggregate.keys()) == ["diversity"]
    assert result.aggregate["diversity"] == pytest.approx(0.5)


def test_system_novelty():
    """Novelty = mean -log2(popularity) over all (user, recommended item) pairs.

    Existing fixtures: test_interactions has 3 users (1,2,3) and 3 items (B,C,D).
    Each item appears once in the test matrix, so each has popularity 1/3.

    All recommended items: B(2x), C(2x), D(2x) — each -log2(1/3) = log2(3)
    novelty = (6 * log2(3)) / 6 = log2(3)
    """
    recommender, _ = _make_fitted_popularity()
    test = _make_test_interactions()
    result = evaluate(recommender, test, k=2, metrics=["novelty"])

    assert list(result.aggregate.keys()) == ["novelty"]
    expected = math.log2(3)
    assert result.aggregate["novelty"] == pytest.approx(expected)


def _make_single_user_test_interactions() -> InteractionMatrix:
    """1 user with one held-out interaction: User 1 -> C."""
    df = pd.DataFrame(
        {
            "user_id": [1],
            "item_id": ["C"],
            "value": [1],
        }
    )
    return InteractionMatrix.from_dataframe(
        df, user_col="user_id", item_col="item_id", value_col="value"
    )


def test_system_single_user_degenerate():
    """A single-user test set -> diversity is 0.0 (fewer than 2 users)."""
    recommender, _ = _make_fitted_popularity()
    test = _make_single_user_test_interactions()
    result = evaluate(recommender, test, k=2)

    assert "diversity" in result.aggregate
    assert result.aggregate["diversity"] == 0.0
    # Coverage and novelty are still meaningful for 1 user
    assert "coverage" in result.aggregate
    assert "novelty" in result.aggregate


def test_evaluate_all_eight_metrics_accepted():
    """All 8 metric names accepted; metrics=None returns all 8 aggregate keys."""
    recommender, _ = _make_fitted_popularity()
    test = _make_test_interactions()

    # Explicit list of all 8
    result = evaluate(
        recommender,
        test,
        k=2,
        metrics=[
            "precision_at_k",
            "recall_at_k",
            "ndcg_at_k",
            "map_at_k",
            "hit_rate",
            "coverage",
            "diversity",
            "novelty",
        ],
    )
    expected_aggregate_keys = {
        "mean_precision_at_k",
        "mean_recall_at_k",
        "mean_ndcg_at_k",
        "hit_rate",
        "map_at_k",
        "coverage",
        "diversity",
        "novelty",
    }
    assert set(result.aggregate.keys()) == expected_aggregate_keys
    # per_user columns unchanged — only the 5 ranking-metric columns
    expected_per_user_cols = {
        "user_id",
        "precision_at_k",
        "recall_at_k",
        "ndcg_at_k",
        "hit",
        "average_precision",
    }
    assert set(result.per_user.columns) == expected_per_user_cols

    # Default (metrics=None) also returns all 8
    result_default = evaluate(recommender, test, k=2)
    assert set(result_default.aggregate.keys()) == expected_aggregate_keys


# ===================================================================
# compare() integration tests
# ===================================================================


def _make_fitted_random() -> tuple:
    """Fit a random recommender on the train set and return it plus the train IM."""
    train = _make_train_interactions()
    spec = get_recommender_spec("random")
    recommender = spec.fitter(train, None, {"seed": 0})
    return recommender, train


ALL_EIGHT_METRIC_COLS = {
    "mean_precision_at_k",
    "mean_recall_at_k",
    "mean_ndcg_at_k",
    "hit_rate",
    "map_at_k",
    "coverage",
    "diversity",
    "novelty",
}
EXPECTED_COMPARE_COLS = {"algorithm", "is_baseline"} | ALL_EIGHT_METRIC_COLS


def test_compare_with_popularity_in_list_no_auto_baseline():
    """When one recommender is 'popularity', compare returns exactly len(recommenders) rows
    and is_baseline is False for all."""
    pop_rec, _ = _make_fitted_popularity()
    rand_rec, _ = _make_fitted_random()
    test = _make_test_interactions()

    result = compare(test, recommenders=[pop_rec, rand_rec], k=2)

    assert len(result) == 2
    assert set(result.columns) == EXPECTED_COMPARE_COLS
    assert not result["is_baseline"].any()
    assert result["mean_ndcg_at_k"].is_monotonic_decreasing


def test_compare_without_popularity_adds_auto_baseline():
    """When no recommender is 'popularity', compare adds an auto-baseline popularity row
    and marks it is_baseline=True."""
    rand_rec, _ = _make_fitted_random()
    cooc_spec = get_recommender_spec("co_occurrence")
    train = _make_train_interactions()
    cooc_rec = cooc_spec.fitter(train, None, {})
    test = _make_test_interactions()

    result = compare(test, recommenders=[rand_rec, cooc_rec], k=2)

    assert len(result) == 3
    assert set(result.columns) == EXPECTED_COMPARE_COLS
    # Exactly one row has is_baseline=True (the auto-added popularity)
    assert result["is_baseline"].sum() == 1
    # The auto-baseline row has algorithm "popularity"
    assert "popularity" in result["algorithm"].values
    baseline_row = result[result["is_baseline"]]
    assert baseline_row["algorithm"].iloc[0] == "popularity"
    # Non-baseline rows all have is_baseline=False
    assert not result[~result["is_baseline"]]["is_baseline"].any()
    assert result["mean_ndcg_at_k"].is_monotonic_decreasing


def test_compare_empty_recommenders_raises():
    """compare with empty recommenders list raises InvalidRecommenderParamsError."""
    test = _make_test_interactions()
    with pytest.raises(InvalidRecommenderParamsError):
        compare(test, recommenders=[], k=2)


# ===================================================================
# Determinism tests
# ===================================================================


def test_evaluate_is_deterministic():
    """evaluate() produces identical aggregate and per_user results on repeated calls."""
    recommender, _ = _make_fitted_popularity()
    test = _make_test_interactions()

    result_a = evaluate(recommender, test, k=2)
    result_b = evaluate(recommender, test, k=2)

    assert result_a.aggregate == result_b.aggregate
    pd.testing.assert_frame_equal(result_a.per_user, result_b.per_user)


def test_compare_is_deterministic():
    """compare() produces an identical DataFrame on repeated calls."""
    pop_rec, _ = _make_fitted_popularity()
    rand_rec, _ = _make_fitted_random()
    test = _make_test_interactions()

    result_a = compare(test, recommenders=[pop_rec, rand_rec], k=2)
    result_b = compare(test, recommenders=[pop_rec, rand_rec], k=2)

    pd.testing.assert_frame_equal(result_a, result_b)
