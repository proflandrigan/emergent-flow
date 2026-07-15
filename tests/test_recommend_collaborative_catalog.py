"""
Tests for user_knn_cf (memory-based collaborative filtering, Story 7).
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
    """4 users x 3 items with explicit values (from the baseline test)."""
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


def _make_hand_verified_fixture() -> InteractionMatrix:
    """5 users x 3 items with explicit values for hand-computed recommendations.

    Users/items:
        User 10: X(5), Y(1)
        User 20: X(1), Z(3)
        User 30: Y(2), Z(1)
        User 40: X(3), Z(2)
        User 50: Y(4)
    """
    df = pd.DataFrame(
        {
            "user_id": [10, 10, 20, 20, 30, 30, 40, 40, 50],
            "item_id": ["X", "Y", "X", "Z", "Y", "Z", "X", "Z", "Y"],
            "value": [5, 1, 1, 3, 2, 1, 3, 2, 4],
        }
    )
    return InteractionMatrix.from_dataframe(
        df, user_col="user_id", item_col="item_id", value_col="value"
    )


def _make_min_common_fixture() -> InteractionMatrix:
    """6 users x 3 items where user 60 (only Z) has max 1 common item with any user.

    Extends _make_hand_verified_fixture with user 60 who only has Z(1).
    """
    df = pd.DataFrame(
        {
            "user_id": [10, 10, 20, 20, 30, 30, 40, 40, 50, 60],
            "item_id": ["X", "Y", "X", "Z", "Y", "Z", "X", "Z", "Y", "Z"],
            "value": [5, 1, 1, 3, 2, 1, 3, 2, 4, 1],
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


# ---------------------------------------------------------------------------
# user_knn_cf
# ---------------------------------------------------------------------------


def test_user_knn_cf_fit_returns_fitted_recommender():
    im = _make_small_interactions()
    spec = _reg.get_recommender_spec("user_knn_cf")
    result = spec.fitter(im, None, {"k": 2})
    assert isinstance(result, FittedRecommender)
    assert result.algorithm == "user_knn_cf"
    assert result.algorithm_family == "collaborative"
    assert "similarity_matrix_density" in result.fit_stats
    assert "mean_neighborhood_size" in result.fit_stats


def test_user_knn_cf_recommend_hand_verified():
    """
    User-based KNN with k=2, cosine similarity, exclude_known=True.

    Fixture: _make_hand_verified_fixture()
    Items: X(0), Y(1), Z(2)
    Users: 10, 20, 30, 40, 50

    User 10: X(5), Y(1)  ->  norm=sqrt(26)=5.099
    User 20: X(1), Z(3)  ->  norm=sqrt(10)=3.162
    User 30: Y(2), Z(1)  ->  norm=sqrt(5)=2.236
    User 40: X(3), Z(2)  ->  norm=sqrt(13)=3.606
    User 50: Y(4)        ->  norm=4.0

    Cosine similarities from user 10:
      10-40: 15/(5.099*3.606) = 0.816
      10-20:  5/(5.099*3.162) = 0.310
      10-50:  4/(5.099*4.0)   = 0.196
      10-30:  2/(5.099*2.236) = 0.175

    k=2 -> top neighbors: U40(0.816), U20(0.310)
    User 10's known items: X(idx=0), Y(idx=1)

    From U40 (items: X=3, Z=2): Z -> 0.816*2=1.632
    From U20 (items: X=1, Z=3): Z -> 0.310*3=0.930
    Z total = 2.562
    Expected: only item Z at rank 1.
    """
    im = _make_hand_verified_fixture()
    spec = _reg.get_recommender_spec("user_knn_cf")
    fitted = spec.fitter(im, None, {"k": 2})
    result = spec.recommend_fn(fitted, [10], 3, exclude_known=True)
    assert result.recommendations["item_id"].tolist() == ["Z"]
    assert float(result.recommendations["score"].iloc[0]) > 0


def test_user_knn_cf_min_common_items_filters_neighbors():
    """Setting min_common_items above a user's max overlap removes all neighbors.

    User 60 (only item Z) shares at most 1 item with any other user.
    With min_common_items=0: has neighbors (non-empty recommendation set).
    With min_common_items=2: no neighbors (empty recommendation set).
    """
    im = _make_min_common_fixture()
    spec = _reg.get_recommender_spec("user_knn_cf")

    r0 = spec.fitter(im, None, {"k": 3, "min_common_items": 0})
    res0 = spec.recommend_fn(r0, [60], 5, exclude_known=True)
    assert len(res0.recommendations) > 0

    r2 = spec.fitter(im, None, {"k": 3, "min_common_items": 2})
    res2 = spec.recommend_fn(r2, [60], 5, exclude_known=True)
    assert len(res2.recommendations) == 0


def test_user_knn_cf_exclude_known():
    """Items the target user has already interacted with never appear."""
    im = _make_small_interactions()
    spec = _reg.get_recommender_spec("user_knn_cf")
    fitted = spec.fitter(im, None, {"k": 2})
    result = spec.recommend_fn(fitted, [1], 5, exclude_known=True)
    returned_ids = result.recommendations["item_id"].tolist()
    assert "A" not in returned_ids
    assert "B" not in returned_ids


def test_user_knn_cf_determinism():
    im = _make_small_interactions()
    spec = _reg.get_recommender_spec("user_knn_cf")

    f1 = spec.fitter(im, None, {"k": 2})
    f2 = spec.fitter(im, None, {"k": 2})
    r1 = spec.recommend_fn(f1, [1, 2, 3], 3, exclude_known=True)
    r2 = spec.recommend_fn(f2, [1, 2, 3], 3, exclude_known=True)

    pd.testing.assert_frame_equal(r1.recommendations, r2.recommendations)


def test_user_knn_cf_cold_start_user():
    """Unknown user ids (not in user_index) yield an empty result."""
    im = _make_small_interactions()
    spec = _reg.get_recommender_spec("user_knn_cf")
    fitted = spec.fitter(im, None, {"k": 2})
    result = spec.recommend_fn(fitted, [99], 3, exclude_known=True)
    assert len(result.recommendations) == 0


def test_user_knn_cf_jaccard_similarity():
    im = _make_small_interactions()
    spec = _reg.get_recommender_spec("user_knn_cf")
    fitted = spec.fitter(im, None, {"k": 2, "similarity": "jaccard"})
    result = spec.recommend_fn(fitted, [1, 2], 3, exclude_known=True)
    assert isinstance(result, RecommendationResult)
    assert len(result.recommendations) > 0


def test_user_knn_cf_pearson_similarity():
    im = _make_small_interactions()
    spec = _reg.get_recommender_spec("user_knn_cf")
    fitted = spec.fitter(im, None, {"k": 2, "similarity": "pearson"})
    result = spec.recommend_fn(fitted, [1, 2], 3, exclude_known=True)
    assert isinstance(result, RecommendationResult)
    assert len(result.recommendations) > 0


def test_user_knn_cf_codegen_is_parseable():
    """Rendered codegen snippet for user_knn_cf must be syntactically valid Python."""
    fit_def = RecommendFit()
    fit_node = fit_def.instantiate(algorithm="user_knn_cf", params={})
    frag = fit_def.preview(fit_node)
    code = frag.render()
    ast.parse(code)


def test_user_knn_cf_equivalence_execute_vs_codegen():
    """ADR 0002: execute == running the emitted code, for user_knn_cf."""
    im = _make_small_interactions()
    fit_def = RecommendFit()
    fit_node = fit_def.instantiate(algorithm="user_knn_cf", params={})

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


# ---------------------------------------------------------------------------
# item_knn_cf
# ---------------------------------------------------------------------------


def _make_item_common_fixture() -> InteractionMatrix:
    """3 users x 3 items where item X has max 1 common user with any item.

    Users: 10 (X), 20 (X, Y), 30 (Y, Z)
    Item X shares at most 1 user with any other item.
    With min_common_users=0: user 10 gets recommendations (X's neighbors).
    With min_common_users=2: X has no neighbors -> user 10 gets empty.
    """
    df = pd.DataFrame(
        {
            "user_id": [10, 20, 20, 30, 30],
            "item_id": ["X", "X", "Y", "Y", "Z"],
            "value": [1, 1, 1, 1, 1],
        }
    )
    return InteractionMatrix.from_dataframe(
        df, user_col="user_id", item_col="item_id", value_col="value"
    )


def test_item_knn_cf_fit_returns_fitted_recommender():
    im = _make_small_interactions()
    spec = _reg.get_recommender_spec("item_knn_cf")
    result = spec.fitter(im, None, {"k": 2})
    assert isinstance(result, FittedRecommender)
    assert result.algorithm == "item_knn_cf"
    assert result.algorithm_family == "collaborative"
    assert "similarity_matrix_density" in result.fit_stats
    assert "mean_neighborhood_size" in result.fit_stats


def test_item_knn_cf_recommend_hand_verified():
    """
    Item-based KNN with k=2, cosine similarity, exclude_known=True.

    Fixture: _make_hand_verified_fixture()
    Items: X(0), Y(1), Z(2)
    Users: 10, 20, 30, 40, 50

    Item vectors (from matrix.T, 5-D user-space):
      X = [5, 1, 0, 3, 0]  norm = sqrt(35) = 5.916
      Y = [1, 0, 2, 0, 4]  norm = sqrt(21) = 4.583
      Z = [0, 3, 1, 2, 0]  norm = sqrt(14) = 3.742

    Cosine similarities (item-item):
      cos(X,Y) =  5 / (5.916*4.583) = 0.184
      cos(X,Z) =  9 / (5.916*3.742) = 0.407
      cos(Y,Z) =  2 / (4.583*3.742) = 0.117

    k=2 -> top neighbors for each item:
      X: Y(0.184), Z(0.407)
      Y: X(0.184), Z(0.117)
      Z: X(0.407), Y(0.117)

    User 10's known items: X(value=5), Y(value=1)
    From X -> Z: 5 * 0.407 = 2.035
    From Y -> Z: 1 * 0.117 = 0.117
    Z total = 2.152
    Expected: only item Z at rank 1.
    """
    im = _make_hand_verified_fixture()
    spec = _reg.get_recommender_spec("item_knn_cf")
    fitted = spec.fitter(im, None, {"k": 2})
    result = spec.recommend_fn(fitted, [10], 3, exclude_known=True)
    assert result.recommendations["item_id"].tolist() == ["Z"]
    assert float(result.recommendations["score"].iloc[0]) > 0


def test_item_knn_cf_min_common_users_filters_neighbors():
    """Setting min_common_users above an item's max overlap removes all neighbors.

    User 10 only knows item X. X shares at most 1 user with any other item.
    With min_common_users=0: X has neighbors (non-empty recommendation set).
    With min_common_users=2: X has no neighbors (empty recommendation set).
    """
    im = _make_item_common_fixture()
    spec = _reg.get_recommender_spec("item_knn_cf")

    r0 = spec.fitter(im, None, {"k": 3, "min_common_users": 0})
    res0 = spec.recommend_fn(r0, [10], 5, exclude_known=True)
    assert len(res0.recommendations) > 0

    r2 = spec.fitter(im, None, {"k": 3, "min_common_users": 2})
    res2 = spec.recommend_fn(r2, [10], 5, exclude_known=True)
    assert len(res2.recommendations) == 0


def test_item_knn_cf_exclude_known():
    """Items the target user has already interacted with never appear."""
    im = _make_small_interactions()
    spec = _reg.get_recommender_spec("item_knn_cf")
    fitted = spec.fitter(im, None, {"k": 2})
    result = spec.recommend_fn(fitted, [1], 5, exclude_known=True)
    returned_ids = result.recommendations["item_id"].tolist()
    assert "A" not in returned_ids
    assert "B" not in returned_ids


def test_item_knn_cf_determinism():
    im = _make_small_interactions()
    spec = _reg.get_recommender_spec("item_knn_cf")

    f1 = spec.fitter(im, None, {"k": 2})
    f2 = spec.fitter(im, None, {"k": 2})
    r1 = spec.recommend_fn(f1, [1, 2, 3], 3, exclude_known=True)
    r2 = spec.recommend_fn(f2, [1, 2, 3], 3, exclude_known=True)

    pd.testing.assert_frame_equal(r1.recommendations, r2.recommendations)


def test_item_knn_cf_cold_start_user():
    """Unknown user ids (not in user_index) yield an empty result."""
    im = _make_small_interactions()
    spec = _reg.get_recommender_spec("item_knn_cf")
    fitted = spec.fitter(im, None, {"k": 2})
    result = spec.recommend_fn(fitted, [99], 3, exclude_known=True)
    assert len(result.recommendations) == 0


def test_item_knn_cf_jaccard_similarity():
    im = _make_small_interactions()
    spec = _reg.get_recommender_spec("item_knn_cf")
    fitted = spec.fitter(im, None, {"k": 2, "similarity": "jaccard"})
    result = spec.recommend_fn(fitted, [1, 2], 3, exclude_known=True)
    assert isinstance(result, RecommendationResult)
    assert len(result.recommendations) > 0


def _make_pearson_item_fixture() -> InteractionMatrix:
    """4 users x 3 items designed for positive item-item pearson correlations.

    User-item matrix:
       A  B  C
    1: 5  4  0
    2: 3  3  3
    3: 2  2  2
    4: 0  0  5

    Item pearson: all pairwise positive (co-correlated user patterns).
    User 1 (A=5, B=4) should get C recommended with k=2.
    """
    df = pd.DataFrame(
        {
            "user_id": [1, 1, 2, 2, 2, 3, 3, 3, 4],
            "item_id": ["A", "B", "A", "B", "C", "A", "B", "C", "C"],
            "value": [5, 4, 3, 3, 3, 2, 2, 2, 5],
        }
    )
    return InteractionMatrix.from_dataframe(
        df, user_col="user_id", item_col="item_id", value_col="value"
    )


def test_item_knn_cf_pearson_similarity():
    im = _make_pearson_item_fixture()
    spec = _reg.get_recommender_spec("item_knn_cf")
    fitted = spec.fitter(im, None, {"k": 2, "similarity": "pearson"})
    result = spec.recommend_fn(fitted, [1], 3, exclude_known=True)
    assert isinstance(result, RecommendationResult)
    assert len(result.recommendations) > 0


def test_item_knn_cf_codegen_is_parseable():
    """Rendered codegen snippet for item_knn_cf must be syntactically valid Python."""
    fit_def = RecommendFit()
    fit_node = fit_def.instantiate(algorithm="item_knn_cf", params={})
    frag = fit_def.preview(fit_node)
    code = frag.render()
    ast.parse(code)


def test_item_knn_cf_equivalence_execute_vs_codegen():
    """ADR 0002: execute == running the emitted code, for item_knn_cf."""
    im = _make_small_interactions()
    fit_def = RecommendFit()
    fit_node = fit_def.instantiate(algorithm="item_knn_cf", params={})

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


# ---------------------------------------------------------------------------
# svd_cf
# ---------------------------------------------------------------------------


def test_svd_cf_fit_returns_fitted_recommender():
    im = _make_small_interactions()
    spec = _reg.get_recommender_spec("svd_cf")
    result = spec.fitter(im, None, {"n_components": 2, "seed": 0})
    assert isinstance(result, FittedRecommender)
    assert result.algorithm == "svd_cf"
    assert result.algorithm_family == "collaborative"
    assert "n_components" in result.fit_stats
    assert "explained_variance_ratio" in result.fit_stats


def test_svd_cf_recommend_returns_valid_result():
    im = _make_small_interactions()
    spec = _reg.get_recommender_spec("svd_cf")
    fitted = spec.fitter(im, None, {"n_components": 2, "seed": 0})
    result = spec.recommend_fn(fitted, [1], 3, exclude_known=False)
    assert isinstance(result, RecommendationResult)
    assert len(result.recommendations) > 0
    cols = list(result.recommendations.columns)
    for c in ["user_id", "item_id", "rank", "score"]:
        assert c in cols
    ranks = result.recommendations["rank"].tolist()
    assert ranks == list(range(1, len(ranks) + 1))


def test_svd_cf_exclude_known():
    im = _make_small_interactions()
    spec = _reg.get_recommender_spec("svd_cf")
    fitted = spec.fitter(im, None, {"n_components": 2, "seed": 0})
    result = spec.recommend_fn(fitted, [1], 5, exclude_known=True)
    returned_ids = result.recommendations["item_id"].tolist()
    assert "A" not in returned_ids
    assert "B" not in returned_ids


def test_svd_cf_determinism():
    im = _make_small_interactions()
    spec = _reg.get_recommender_spec("svd_cf")

    f1 = spec.fitter(im, None, {"n_components": 2, "seed": 0})
    f2 = spec.fitter(im, None, {"n_components": 2, "seed": 0})
    r1 = spec.recommend_fn(f1, [1, 2, 3], 3, exclude_known=True)
    r2 = spec.recommend_fn(f2, [1, 2, 3], 3, exclude_known=True)

    pd.testing.assert_frame_equal(r1.recommendations, r2.recommendations)


def test_svd_cf_n_components_clamped_on_tiny_matrix():
    im = _make_small_interactions()
    spec = _reg.get_recommender_spec("svd_cf")
    # min(4, 3) - 1 = 2; request n_components=100 to test clamping
    result = spec.fitter(im, None, {"n_components": 100, "seed": 0})
    assert result.fit_stats["n_components"] <= min(im.n_users, im.n_items) - 1


def test_svd_cf_codegen_is_parseable():
    """Rendered codegen snippet for svd_cf must be syntactically valid Python."""
    fit_def = RecommendFit()
    fit_node = fit_def.instantiate(algorithm="svd_cf", params={"n_components": 2, "seed": 0})
    frag = fit_def.preview(fit_node)
    code = frag.render()
    ast.parse(code)


def test_svd_cf_equivalence_execute_vs_codegen():
    """ADR 0002: execute == running the emitted code, for svd_cf."""
    im = _make_small_interactions()
    fit_def = RecommendFit()
    fit_node = fit_def.instantiate(algorithm="svd_cf", params={"n_components": 2, "seed": 0})

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


# ---------------------------------------------------------------------------
# nmf_cf
# ---------------------------------------------------------------------------


def test_nmf_cf_fit_returns_fitted_recommender():
    im = _make_small_interactions()
    spec = _reg.get_recommender_spec("nmf_cf")
    result = spec.fitter(im, None, {"n_components": 2, "seed": 0})
    assert isinstance(result, FittedRecommender)
    assert result.algorithm == "nmf_cf"
    assert result.algorithm_family == "collaborative"
    assert "n_components" in result.fit_stats
    assert "reconstruction_err" in result.fit_stats
    assert "n_iter" in result.fit_stats


def test_nmf_cf_recommend_returns_valid_result():
    im = _make_small_interactions()
    spec = _reg.get_recommender_spec("nmf_cf")
    fitted = spec.fitter(im, None, {"n_components": 2, "seed": 0})
    result = spec.recommend_fn(fitted, [1], 3, exclude_known=False)
    assert isinstance(result, RecommendationResult)
    assert len(result.recommendations) > 0
    cols = list(result.recommendations.columns)
    for c in ["user_id", "item_id", "rank", "score"]:
        assert c in cols
    ranks = result.recommendations["rank"].tolist()
    assert ranks == list(range(1, len(ranks) + 1))


def test_nmf_cf_exclude_known():
    im = _make_small_interactions()
    spec = _reg.get_recommender_spec("nmf_cf")
    fitted = spec.fitter(im, None, {"n_components": 2, "seed": 0})
    result = spec.recommend_fn(fitted, [1], 5, exclude_known=True)
    returned_ids = result.recommendations["item_id"].tolist()
    assert "A" not in returned_ids
    assert "B" not in returned_ids


def test_nmf_cf_determinism():
    im = _make_small_interactions()
    spec = _reg.get_recommender_spec("nmf_cf")

    f1 = spec.fitter(im, None, {"n_components": 2, "seed": 0})
    f2 = spec.fitter(im, None, {"n_components": 2, "seed": 0})
    r1 = spec.recommend_fn(f1, [1, 2, 3], 3, exclude_known=True)
    r2 = spec.recommend_fn(f2, [1, 2, 3], 3, exclude_known=True)

    pd.testing.assert_frame_equal(r1.recommendations, r2.recommendations)


def test_nmf_cf_n_components_clamped_on_tiny_matrix():
    im = _make_small_interactions()
    spec = _reg.get_recommender_spec("nmf_cf")
    # min(4, 3) - 1 = 2; request n_components=100 to test clamping
    result = spec.fitter(im, None, {"n_components": 100, "seed": 0})
    assert result.fit_stats["n_components"] <= min(im.n_users, im.n_items) - 1


def test_nmf_cf_codegen_is_parseable():
    """Rendered codegen snippet for nmf_cf must be syntactically valid Python."""
    fit_def = RecommendFit()
    fit_node = fit_def.instantiate(algorithm="nmf_cf", params={"n_components": 2, "seed": 0})
    frag = fit_def.preview(fit_node)
    code = frag.render()
    ast.parse(code)


def test_nmf_cf_equivalence_execute_vs_codegen():
    """ADR 0002: execute == running the emitted code, for nmf_cf."""
    im = _make_small_interactions()
    fit_def = RecommendFit()
    fit_node = fit_def.instantiate(algorithm="nmf_cf", params={"n_components": 2, "seed": 0})

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
