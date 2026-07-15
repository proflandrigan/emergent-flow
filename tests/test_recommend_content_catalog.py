"""
Golden + equivalence tests for the Epic 15 Story 5 content-based catalog
(tfidf_similarity, feature_knn).

Structure mirrors ``tests/test_recommend_baseline_catalog.py``:
1. Per-algorithm fit/recommend tests on small hand-verified fixtures.
2. Determinism, exclude_known, cold-start, and missing-item-features correctness.
3. ADR-0002 equivalence (execute == codegen) for tfidf_similarity via the
   existing ``RecommendFit``/``Recommend`` node classes.
"""

from __future__ import annotations

import ast
from typing import Any

import numpy as np
import pandas as pd
import pytest
from scipy import sparse

from emergentflow.nodes.examples.recommend_fit import RecommendFit
from emergentflow.nodes.examples.recommend_recommend import Recommend
from emergentflow.recommend import registry as _reg
from emergentflow.recommend.errors import InvalidRecommenderParamsError
from emergentflow.recommend.interactions import InteractionMatrix
from emergentflow.recommend.models import FittedRecommender, RecommendationResult

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

ITEMS_TFIDF = ["A", "B", "C", "D"]


def _make_tfidf_interactions() -> InteractionMatrix:
    """4 users x 4 items. Items A/B/C have text features; D has none."""
    df = pd.DataFrame(
        {
            "user_id": [1, 1, 2, 2, 3, 3, 4],
            "item_id": ["A", "B", "B", "C", "A", "D", "D"],
            "value": 1,
        }
    )
    return InteractionMatrix.from_dataframe(df, user_col="user_id", item_col="item_id")


def _make_tfidf_item_features() -> pd.DataFrame:
    """Item features for A, B, C (D is deliberately absent)."""
    return pd.DataFrame(
        {
            "item_id": ["A", "B", "C"],
            "description": ["cat dog", "car truck", "cat dog pet"],
        }
    )


ITEMS_FKNN = ["A", "B", "C", "D"]


def _make_fknn_interactions() -> InteractionMatrix:
    """4 users x 4 items. Items A/B/C have numeric features; D has none."""
    df = pd.DataFrame(
        {
            "user_id": [1, 1, 2, 2, 3, 3, 4],
            "item_id": ["A", "B", "B", "C", "A", "D", "D"],
            "value": 1,
        }
    )
    return InteractionMatrix.from_dataframe(df, user_col="user_id", item_col="item_id")


def _make_fknn_item_features() -> pd.DataFrame:
    """2-D numeric features for A, B, C (D is deliberately absent)."""
    return pd.DataFrame(
        {
            "item_id": ["A", "B", "C"],
            "f1": [1.0, 0.0, 1.0],
            "f2": [0.0, 1.0, 1.0],
        }
    )


def _run_codegen(definition, node, scope):
    """exec a node's preview fragment in *scope* and return the updated scope."""
    frag = definition.preview(node)
    exec(frag.render(), scope)
    return scope


def _make_tfidf_single_interaction_fixture() -> tuple[InteractionMatrix, pd.DataFrame]:
    """Simpler fixture: user 1 only interacted with A (which has 'cat dog').
    C is in the interaction matrix (via user 3) so it stays in the item universe."""
    df = pd.DataFrame({"user_id": [1, 2, 2, 3], "item_id": ["A", "A", "B", "C"], "value": 1})
    im = InteractionMatrix.from_dataframe(df, user_col="user_id", item_col="item_id")
    item_features = pd.DataFrame(
        {"item_id": ["A", "B", "C"], "description": ["cat dog", "car truck", "cat dog pet"]}
    )
    return im, item_features


# ===================================================================
# tfidf_similarity
# ===================================================================


def test_tfidf_fit_returns_fitted_recommender():
    im = _make_tfidf_interactions()
    item_features = _make_tfidf_item_features()
    spec = _reg.get_recommender_spec("tfidf_similarity")

    fitted = spec.fitter(
        im,
        item_features,
        {"item_id_col": "item_id", "text_col": "description"},
    )
    assert isinstance(fitted, FittedRecommender)
    assert fitted.algorithm == "tfidf_similarity"
    assert fitted.algorithm_family == "content"
    assert "n_interactions" in fitted.fit_stats
    assert "sparsity" in fitted.fit_stats
    assert "vocab_size" in fitted.fit_stats


def test_tfidf_missing_item_features_does_not_crash():
    """Item D is present in interactions but absent from item_features."""
    im = _make_tfidf_interactions()
    item_features = _make_tfidf_item_features()
    spec = _reg.get_recommender_spec("tfidf_similarity")

    fitted = spec.fitter(
        im,
        item_features,
        {"item_id_col": "item_id", "text_col": "description"},
    )
    # D gets a zero feature vector — recommend should not crash
    result = spec.recommend_fn(fitted, [4], 5, exclude_known=False)
    assert isinstance(result, RecommendationResult)


def test_tfidf_recommend_expected_order():
    """User 1 interacted with A only ('cat dog'). Content closest to C ('cat dog pet'),
    then B ('car truck')."""
    im, item_features = _make_tfidf_single_interaction_fixture()
    spec = _reg.get_recommender_spec("tfidf_similarity")

    fitted = spec.fitter(
        im,
        item_features,
        {"item_id_col": "item_id", "text_col": "description"},
    )
    result = spec.recommend_fn(fitted, [1], 5, exclude_known=True)
    ids = result.recommendations["item_id"].tolist()
    # C shares vocabulary (cat, dog) with A; B shares none
    assert ids[0] == "C"
    assert ids[1] == "B"


def test_tfidf_cold_start_user():
    """Users with no interactions get zero rows."""
    im = _make_tfidf_interactions()
    item_features = _make_tfidf_item_features()
    spec = _reg.get_recommender_spec("tfidf_similarity")

    fitted = spec.fitter(
        im,
        item_features,
        {"item_id_col": "item_id", "text_col": "description"},
    )
    # User not in user_index
    result = spec.recommend_fn(fitted, [99], 5, exclude_known=False)
    assert len(result.recommendations) == 0
    # User in user_index but with all-zero row
    zero_im = InteractionMatrix(
        matrix=sparse.csr_matrix((1, im.n_items), dtype=float),
        user_ids=[42],
        item_ids=im.item_ids,
    )
    fitted_zero = spec.fitter(
        zero_im,
        item_features,
        {"item_id_col": "item_id", "text_col": "description"},
    )
    result2 = spec.recommend_fn(fitted_zero, None, 5, exclude_known=False)
    assert len(result2.recommendations) == 0


def test_tfidf_duplicate_item_features_raises_typed_error():
    """Duplicate item_id_col values in item_features must raise a typed error, not a raw
    pandas ValueError from .reindex()."""
    im = _make_tfidf_interactions()
    item_features = pd.DataFrame(
        {
            "item_id": ["A", "A", "B", "C"],
            "description": ["cat dog", "cat dog dup", "car truck", "cat dog pet"],
        }
    )
    spec = _reg.get_recommender_spec("tfidf_similarity")

    with pytest.raises(InvalidRecommenderParamsError, match="duplicate"):
        spec.fitter(im, item_features, {"item_id_col": "item_id", "text_col": "description"})


def test_tfidf_exclude_known():
    """User 1 known items (A, B) are excluded from recommendations."""
    im = _make_tfidf_interactions()
    item_features = _make_tfidf_item_features()
    spec = _reg.get_recommender_spec("tfidf_similarity")

    fitted = spec.fitter(
        im,
        item_features,
        {"item_id_col": "item_id", "text_col": "description"},
    )
    result = spec.recommend_fn(fitted, [1], 5, exclude_known=True)
    ids = result.recommendations["item_id"].tolist()
    assert "A" not in ids
    assert "B" not in ids


def test_tfidf_determinism():
    im = _make_tfidf_interactions()
    item_features = _make_tfidf_item_features()
    spec = _reg.get_recommender_spec("tfidf_similarity")

    f1 = spec.fitter(im, item_features, {"item_id_col": "item_id", "text_col": "description"})
    f2 = spec.fitter(im, item_features, {"item_id_col": "item_id", "text_col": "description"})
    r1 = spec.recommend_fn(f1, None, 5, exclude_known=True)
    r2 = spec.recommend_fn(f2, None, 5, exclude_known=True)

    pd.testing.assert_frame_equal(r1.recommendations, r2.recommendations)


# ===================================================================
# feature_knn
# ===================================================================


def test_feature_knn_fit_returns_fitted_recommender():
    im = _make_fknn_interactions()
    item_features = _make_fknn_item_features()
    spec = _reg.get_recommender_spec("feature_knn")

    fitted = spec.fitter(
        im,
        item_features,
        {"item_id_col": "item_id", "feature_cols": ["f1", "f2"]},
    )
    assert isinstance(fitted, FittedRecommender)
    assert fitted.algorithm == "feature_knn"
    assert fitted.algorithm_family == "content"
    assert fitted.fit_stats["n_feature_cols"] == 2


def test_feature_knn_missing_item_features_does_not_crash():
    """Item D is present in interactions but absent from item_features."""
    im = _make_fknn_interactions()
    item_features = _make_fknn_item_features()
    spec = _reg.get_recommender_spec("feature_knn")

    fitted = spec.fitter(
        im,
        item_features,
        {"item_id_col": "item_id", "feature_cols": ["f1", "f2"]},
    )
    result = spec.recommend_fn(fitted, [4], 5, exclude_known=False)
    assert isinstance(result, RecommendationResult)


def test_feature_knn_recommend_expected_order_and_scores():
    """User 1 interacted with A ([1,0]) only. Profile = [1,0].
    Cosine to C ([1,1]) = 0.707 → distance 0.293 → score -0.293.
    Cosine to B ([0,1]) = 0.000 → distance 1.000 → score -1.000.
    Expected: C first, B second."""
    im, _ = _make_tfidf_single_interaction_fixture()
    item_features = pd.DataFrame(
        {"item_id": ["A", "B", "C"], "f1": [1.0, 0.0, 1.0], "f2": [0.0, 1.0, 1.0]}
    )
    spec = _reg.get_recommender_spec("feature_knn")

    fitted = spec.fitter(
        im,
        item_features,
        {
            "item_id_col": "item_id",
            "feature_cols": ["f1", "f2"],
            "metric": "cosine",
            "algorithm": "brute",
        },
    )
    result = spec.recommend_fn(fitted, [1], 5, exclude_known=True)
    ids = result.recommendations["item_id"].tolist()
    scores = result.recommendations["score"].tolist()

    assert ids[0] == "C"
    assert ids[1] == "B"

    expected_c_score = -(1.0 - 1.0 / np.sqrt(2.0))
    expected_b_score = -(1.0 - 0.0)
    assert abs(scores[0] - expected_c_score) < 1e-10
    assert abs(scores[1] - expected_b_score) < 1e-10


def test_feature_knn_cold_start_user():
    """User 99 has no interactions — gets zero rows."""
    im = _make_fknn_interactions()
    item_features = _make_fknn_item_features()
    spec = _reg.get_recommender_spec("feature_knn")

    fitted = spec.fitter(
        im,
        item_features,
        {"item_id_col": "item_id", "feature_cols": ["f1", "f2"]},
    )
    result = spec.recommend_fn(fitted, [99], 5, exclude_known=False)
    assert len(result.recommendations) == 0


def test_feature_knn_duplicate_item_features_raises_typed_error():
    """Duplicate item_id_col values in item_features must raise a typed error, not a raw
    pandas ValueError from .reindex()."""
    im = _make_fknn_interactions()
    item_features = pd.DataFrame(
        {
            "item_id": ["A", "A", "B", "C"],
            "f1": [1.0, 2.0, 0.0, 1.0],
            "f2": [0.0, 0.0, 1.0, 1.0],
        }
    )
    spec = _reg.get_recommender_spec("feature_knn")

    with pytest.raises(InvalidRecommenderParamsError, match="duplicate"):
        spec.fitter(im, item_features, {"item_id_col": "item_id", "feature_cols": ["f1", "f2"]})


def test_feature_knn_exclude_known():
    """User 1 known items (A, B) are excluded from recommendations."""
    im = _make_fknn_interactions()
    item_features = _make_fknn_item_features()
    spec = _reg.get_recommender_spec("feature_knn")

    fitted = spec.fitter(
        im,
        item_features,
        {"item_id_col": "item_id", "feature_cols": ["f1", "f2"]},
    )
    result = spec.recommend_fn(fitted, [1], 5, exclude_known=True)
    ids = result.recommendations["item_id"].tolist()
    assert "A" not in ids
    assert "B" not in ids


def test_feature_knn_determinism():
    im = _make_fknn_interactions()
    item_features = _make_fknn_item_features()
    spec = _reg.get_recommender_spec("feature_knn")

    f1 = spec.fitter(im, item_features, {"item_id_col": "item_id", "feature_cols": ["f1", "f2"]})
    f2 = spec.fitter(im, item_features, {"item_id_col": "item_id", "feature_cols": ["f1", "f2"]})
    r1 = spec.recommend_fn(f1, None, 5, exclude_known=True)
    r2 = spec.recommend_fn(f2, None, 5, exclude_known=True)

    pd.testing.assert_frame_equal(r1.recommendations, r2.recommendations)


# ===================================================================
# 3. ADR-0002 equivalence: codegen is parseable + execute == codegen
# ===================================================================


def test_tfidf_codegen_is_parseable():
    """Rendered codegen snippet for tfidf_similarity must be syntactically valid Python."""
    fit_def = RecommendFit()
    fit_node = fit_def.instantiate(
        algorithm="tfidf_similarity",
        params={"item_id_col": "item_id", "text_col": "description"},
    )
    frag = fit_def.preview(fit_node)
    code = frag.render()
    ast.parse(code)


def test_tfidf_equivalence_execute_vs_codegen():
    """ADR 0002: execute == running the emitted code, for tfidf_similarity."""
    im, item_features = _make_tfidf_single_interaction_fixture()

    fit_def = RecommendFit()
    fit_node = fit_def.instantiate(
        algorithm="tfidf_similarity",
        params={"item_id_col": "item_id", "text_col": "description"},
    )

    rec_def = Recommend()
    rec_node = rec_def.instantiate(user_ids=[1], n=5, exclude_known=False)

    # execute path
    fit_result = fit_def.execute(
        fit_node,
        {"interactions": im, "item_features": item_features},
    )
    exec_result = rec_def.execute(
        rec_node,
        {"recommender": fit_result["recommender"]},
    )

    # codegen path
    scope: dict[str, Any] = {"interactions": im, "item_features": item_features}
    _run_codegen(fit_def, fit_node, scope)
    _run_codegen(rec_def, rec_node, scope)
    codegen_result = scope["result"]

    pd.testing.assert_frame_equal(
        exec_result["result"].recommendations,
        codegen_result.recommendations,
    )
