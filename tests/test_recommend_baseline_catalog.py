"""
Golden + equivalence tests for the Epic 15 Story 4 baseline catalog (random, popularity,
popularity_segmented, co_occurrence).

Structure mirrors ``tests/test_stats_regression_catalog.py``:

1. Per-algorithm fit/recommend/similar_items tests on small hand-verified fixtures.
2. Determinism and exclude_known correctness.
3. ADR-0002 equivalence (execute == codegen) for the ``popularity`` algorithm via the
   three existing ``RecommendFit``/``Recommend`` node types.
"""

from __future__ import annotations

import ast
from typing import Any

import pandas as pd

from emergentflow.nodes.examples.recommend_fit import RecommendFit
from emergentflow.nodes.examples.recommend_recommend import Recommend
from emergentflow.recommend import registry as _reg
from emergentflow.recommend.interactions import InteractionMatrix
from emergentflow.recommend.models import FittedRecommender, RecommendationResult

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ITEMS = ["A", "B", "C"]


def _make_small_interactions() -> InteractionMatrix:
    """4 users x 3 items with explicit values, producing unique popularity scores."""
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


def _make_co_occurrence_fixture() -> InteractionMatrix:
    """Extended fixture for co_occurrence tests (more users, clear co-occurrence
    patterns, A-C co-occurs more often than A-B to break tie)."""
    df = pd.DataFrame(
        {
            "user_id": [1, 1, 2, 2, 2, 3, 3, 4, 4, 5, 6, 6],
            "item_id": ["A", "B", "A", "B", "C", "B", "C", "A", "C", "A", "A", "C"],
            "value": 1,
        }
    )
    return InteractionMatrix.from_dataframe(df, user_col="user_id", item_col="item_id")


def _make_larger_interactions() -> InteractionMatrix:
    """Slightly larger 6-user x 4-item fixture for random tests with more variety."""
    df = pd.DataFrame(
        {
            "user_id": [1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6],
            "item_id": ["A", "B", "A", "C", "B", "D", "C", "D", "A", "C", "D"],
            "value": 1,
        }
    )
    return InteractionMatrix.from_dataframe(df, user_col="user_id", item_col="item_id")


def _run_codegen(definition, node, scope):
    """exec a node's preview fragment in *scope* and return the updated scope."""
    frag = definition.preview(node)
    exec(frag.render(), scope)
    return scope


# ---------------------------------------------------------------------------
# random
# ---------------------------------------------------------------------------


def test_random_fit_returns_fitted_recommender():
    im = _make_larger_interactions()
    result = _reg.get_recommender_spec("random").fitter(im, None, {})
    assert isinstance(result, FittedRecommender)
    assert result.algorithm == "random"
    assert result.algorithm_family == "baseline"
    assert "n_interactions" in result.fit_stats
    assert "sparsity" in result.fit_stats


def test_random_recommend_determinism():
    im = _make_larger_interactions()
    spec = _reg.get_recommender_spec("random")

    f1 = spec.fitter(im, None, {"seed": 42})
    r1 = spec.recommend_fn(f1, [1, 2], 3, exclude_known=True)

    f2 = spec.fitter(im, None, {"seed": 42})
    r2 = spec.recommend_fn(f2, [1, 2], 3, exclude_known=True)

    pd.testing.assert_frame_equal(r1.recommendations, r2.recommendations)


def test_random_recommend_exclude_known():
    im = _make_small_interactions()
    spec = _reg.get_recommender_spec("random")

    fitted = spec.fitter(im, None, {"seed": 0})
    result = spec.recommend_fn(fitted, [1], 10, exclude_known=True)
    item_ids = result.recommendations["item_id"].tolist()

    assert "A" not in item_ids
    assert "B" not in item_ids


def test_random_default_seed():
    """Default seed of 0 produces deterministic output."""
    im = _make_larger_interactions()
    spec = _reg.get_recommender_spec("random")

    f1 = spec.fitter(im, None, {})
    r1 = spec.recommend_fn(f1, [1, 2], 3, exclude_known=False)

    f2 = spec.fitter(im, None, {})
    r2 = spec.recommend_fn(f2, [1, 2], 3, exclude_known=False)

    pd.testing.assert_frame_equal(r1.recommendations, r2.recommendations)


def test_random_cold_start():
    """Random recommender handles unknown users."""
    im = _make_small_interactions()
    spec = _reg.get_recommender_spec("random")
    fitted = spec.fitter(im, None, {"seed": 0})
    result = spec.recommend_fn(fitted, [99], 3, exclude_known=False)
    assert len(result.recommendations) == 3


# ---------------------------------------------------------------------------
# popularity (global)
# ---------------------------------------------------------------------------


def test_popularity_fit_returns_fitted_recommender():
    im = _make_small_interactions()
    spec = _reg.get_recommender_spec("popularity")

    fitted = spec.fitter(im, None, {})
    assert isinstance(fitted, FittedRecommender)
    assert fitted.algorithm == "popularity"
    assert fitted.algorithm_family == "baseline"
    assert fitted.fit_stats["n_items_scored"] == 3  # all items have interactions


def test_popularity_recommend_global_same_for_every_user():
    """Global popularity returns the same top-N items (with the same scores)
    for every user (before per-user exclude_known filtering)."""
    im = _make_small_interactions()
    spec = _reg.get_recommender_spec("popularity")
    fitted = spec.fitter(im, None, {"score_type": "count"})

    r1 = spec.recommend_fn(fitted, [1], 3, exclude_known=False)
    r2 = spec.recommend_fn(fitted, [2], 3, exclude_known=False)

    # Expected ranking: A(sum=9), C(sum=6), B(sum=3)
    expected_order = ["A", "C", "B"]
    assert r1.recommendations["item_id"].tolist() == expected_order
    assert r2.recommendations["item_id"].tolist() == expected_order


def test_popularity_exclude_known():
    im = _make_small_interactions()
    spec = _reg.get_recommender_spec("popularity")
    fitted = spec.fitter(im, None, {"score_type": "count"})

    result = spec.recommend_fn(fitted, [1], 5, exclude_known=True)
    returned_ids = result.recommendations["item_id"].tolist()
    assert "A" not in returned_ids
    assert "B" not in returned_ids
    assert returned_ids == ["C"]


def test_popularity_determinism():
    im = _make_small_interactions()
    spec = _reg.get_recommender_spec("popularity")

    f1 = spec.fitter(im, None, {})
    f2 = spec.fitter(im, None, {})
    r1 = spec.recommend_fn(f1, None, 3, exclude_known=True)
    r2 = spec.recommend_fn(f2, None, 3, exclude_known=True)

    pd.testing.assert_frame_equal(r1.recommendations, r2.recommendations)


def test_popularity_mean_rating_score_type():
    im = _make_small_interactions()
    spec = _reg.get_recommender_spec("popularity")
    fitted = spec.fitter(im, None, {"score_type": "mean_rating"})

    result = spec.recommend_fn(fitted, [4], 3, exclude_known=False)
    # mean_rating: A=9/3=3.0, C=6/3=2.0, B=3/2=1.5
    expected_order = ["A", "C", "B"]
    assert result.recommendations["item_id"].tolist() == expected_order


def test_popularity_cold_start_user():
    """Unknown user gets the global top-N."""
    im = _make_small_interactions()
    spec = _reg.get_recommender_spec("popularity")
    fitted = spec.fitter(im, None, {})
    result = spec.recommend_fn(fitted, [99], 3, exclude_known=False)
    assert len(result.recommendations) == 3


# ---------------------------------------------------------------------------
# popularity_segmented
# ---------------------------------------------------------------------------


def test_popularity_segmented_fit_returns_fitted_recommender():
    im = _make_small_interactions()
    spec = _reg.get_recommender_spec("popularity_segmented")

    fitted = spec.fitter(
        im,
        None,
        {
            "segment_col": "region",
            "user_segments": {1: "east", 2: "west", 3: "east", 4: "west"},
        },
    )
    assert isinstance(fitted, FittedRecommender)
    assert fitted.algorithm == "popularity_segmented"
    assert fitted.algorithm_family == "baseline"
    assert fitted.fit_stats["n_segments"] == 2


def test_popularity_segmented_different_segments_different_lists():
    """Users in different segments get different top-N rankings."""
    im = _make_small_interactions()
    spec = _reg.get_recommender_spec("popularity_segmented")

    # East: users 1, 3 — interactions: 1(A,B), 3(B,C)
    #   East sub-matrix: A(5), B(1+2=3), C(1) — sum: A=5, B=3, C=1
    # West: users 2, 4 — interactions: 2(A,C), 4(A,C)
    #   West sub-matrix: A(1+3=4), C(3+2=5) — sum: A=4, C=5, B=0

    fitted = spec.fitter(
        im,
        None,
        {
            "segment_col": "region",
            "user_segments": {1: "east", 2: "west", 3: "east", 4: "west"},
        },
    )

    east_result = spec.recommend_fn(fitted, [1], 3, exclude_known=False)
    west_result = spec.recommend_fn(fitted, [2], 3, exclude_known=False)

    # East top: A(5), B(3), C(1)
    assert east_result.recommendations["item_id"].tolist() == ["A", "B", "C"]
    # West top: C(5), A(4), B(0) — but B has score 0, still appears
    assert west_result.recommendations["item_id"].tolist() == ["C", "A", "B"]


def test_popularity_segmented_cold_start_fallback():
    """A user absent from user_segments falls back to global ranking."""
    im = _make_small_interactions()
    spec = _reg.get_recommender_spec("popularity_segmented")

    fitted = spec.fitter(
        im,
        None,
        {
            "segment_col": "region",
            "user_segments": {1: "east", 2: "west"},
        },
    )
    # user 3 is missing from user_segments — should get global ranking
    result = spec.recommend_fn(fitted, [3], 3, exclude_known=False)
    # Global: A(9), C(6), B(3)
    assert result.recommendations["item_id"].tolist() == ["A", "C", "B"]


def test_popularity_segmented_no_segments_degrades_to_global():
    """Without user_segments, popularity_segmented behaves like global popularity."""
    im = _make_small_interactions()
    spec = _reg.get_recommender_spec("popularity_segmented")

    fitted = spec.fitter(im, None, {"segment_col": "dummy"})
    result = spec.recommend_fn(fitted, [1], 3, exclude_known=False)
    # Global: A(9), C(6), B(3)
    assert result.recommendations["item_id"].tolist() == ["A", "C", "B"]


# ---------------------------------------------------------------------------
# co_occurrence
# ---------------------------------------------------------------------------


def test_co_occurrence_fit_returns_fitted_recommender():
    im = _make_co_occurrence_fixture()
    spec = _reg.get_recommender_spec("co_occurrence")

    fitted = spec.fitter(im, None, {})
    assert isinstance(fitted, FittedRecommender)
    assert fitted.algorithm == "co_occurrence"
    assert fitted.algorithm_family == "baseline"
    assert "n_item_pairs_with_cooccurrence" in fitted.fit_stats


def test_co_occurrence_recommend():
    """co_occurrence recommends items similar to a user's known items."""
    im = _make_co_occurrence_fixture()
    spec = _reg.get_recommender_spec("co_occurrence")
    fitted = spec.fitter(im, None, {"metric": "lift"})

    # User 1 (known: A, B). From A: co-occurrence with C(lift=0.889).
    # From B: co-occurrence with C(lift=0.667).
    # Candidate C: 0.889 + 0.667 = 1.556
    result = spec.recommend_fn(fitted, [1], 3, exclude_known=True)
    returned_ids = result.recommendations["item_id"].tolist()
    assert "A" not in returned_ids
    assert "B" not in returned_ids
    assert returned_ids[0] == "C"


def test_co_occurrence_similar_items():
    """co_occurrence supports item-item similarity."""
    im = _make_co_occurrence_fixture()
    spec = _reg.get_recommender_spec("co_occurrence")
    fitted = spec.fitter(im, None, {"metric": "lift"})

    result = spec.similar_items_fn(fitted, ["A"], 2)
    assert isinstance(result, RecommendationResult)
    ids = result.recommendations["item_id"].tolist()
    scores = result.recommendations["score"].tolist()
    # A's similar items by lift: C (0.889), B (0.667)
    assert ids == ["C", "B"]
    assert scores[0] > scores[1]


def test_co_occurrence_exclude_known():
    im = _make_co_occurrence_fixture()
    spec = _reg.get_recommender_spec("co_occurrence")
    fitted = spec.fitter(im, None, {"metric": "lift"})

    result = spec.recommend_fn(fitted, [1], 3, exclude_known=True)
    returned_ids = result.recommendations["item_id"].tolist()
    assert "A" not in returned_ids
    assert "B" not in returned_ids


def test_co_occurrence_determinism():
    im = _make_co_occurrence_fixture()
    spec = _reg.get_recommender_spec("co_occurrence")

    f1 = spec.fitter(im, None, {})
    f2 = spec.fitter(im, None, {})
    r1 = spec.recommend_fn(f1, [1, 2], 3, exclude_known=True)
    r2 = spec.recommend_fn(f2, [1, 2], 3, exclude_known=True)

    pd.testing.assert_frame_equal(r1.recommendations, r2.recommendations)


def test_co_occurrence_cold_start():
    """co_occurrence returns nothing for unknown users."""
    im = _make_co_occurrence_fixture()
    spec = _reg.get_recommender_spec("co_occurrence")
    fitted = spec.fitter(im, None, {})
    result = spec.recommend_fn(fitted, [99], 3, exclude_known=True)
    assert len(result.recommendations) == 0


# ---------------------------------------------------------------------------
# 3. Golden-code quality: codegen is parseable for the popularity algorithm
# ---------------------------------------------------------------------------


def test_popularity_codegen_is_parseable():
    """Rendered codegen snippet for popularity must be syntactically valid Python."""
    fit_def = RecommendFit()
    fit_node = fit_def.instantiate(algorithm="popularity", params={"score_type": "count"})
    frag = fit_def.preview(fit_node)
    code = frag.render()
    ast.parse(code)


def test_popularity_equivalence_execute_vs_codegen():
    """ADR 0002: execute == running the emitted code, for popularity."""
    im = _make_small_interactions()
    fit_def = RecommendFit()
    fit_node = fit_def.instantiate(algorithm="popularity", params={"score_type": "count"})

    rec_def = Recommend()
    rec_node = rec_def.instantiate(user_ids=[1, 2, 3, 4], n=3, exclude_known=True)

    # execute path
    fit_result = fit_def.execute(fit_node, {"interactions": im})
    exec_result = rec_def.execute(rec_node, {"recommender": fit_result["recommender"]})

    # codegen path
    scope: dict[str, Any] = {"interactions": im, "item_features": None}
    _run_codegen(fit_def, fit_node, scope)
    _run_codegen(rec_def, rec_node, scope)
    codegen_result = scope["result"]

    pd.testing.assert_frame_equal(
        exec_result["result"].recommendations,
        codegen_result.recommendations,
    )
