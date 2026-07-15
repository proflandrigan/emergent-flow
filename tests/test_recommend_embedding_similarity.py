"""
Tests for the ``embedding_similarity`` algorithm in the content-based catalog and the
``RecommendByEmbedding`` node.
"""

from __future__ import annotations

import ast
from typing import Any

import numpy as np
import pandas as pd
import pytest

from emergentflow.nodes.examples.recommend_by_embedding import RecommendByEmbedding
from emergentflow.recommend import registry as _reg
from emergentflow.recommend.errors import InvalidRecommenderParamsError
from emergentflow.recommend.interactions import InteractionMatrix
from emergentflow.recommend.models import FittedRecommender, RecommendationResult

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

ITEMS = ["A", "B", "C", "D"]


def _make_interactions() -> InteractionMatrix:
    """4 users x 4 items. Items A/B/C have embeddings; D has none."""
    df = pd.DataFrame(
        {
            "user_id": [1, 1, 2, 2, 3, 3, 4],
            "item_id": ["A", "B", "B", "C", "A", "D", "D"],
            "value": 1,
        }
    )
    return InteractionMatrix.from_dataframe(df, user_col="user_id", item_col="item_id")


def _make_item_features() -> pd.DataFrame:
    """2-D embeddings for A, B, C (D is deliberately absent)."""
    return pd.DataFrame(
        {
            "item_id": ["A", "B", "C"],
            "embedding": [
                [1.0, 0.0],
                [0.0, 1.0],
                [1.0, 1.0],
            ],
        }
    )


def _make_single_interaction_fixture() -> tuple[InteractionMatrix, pd.DataFrame]:
    """Simpler fixture: user 1 only interacted with A. C is in the item universe."""
    df = pd.DataFrame({"user_id": [1, 2, 2, 3], "item_id": ["A", "A", "B", "C"], "value": 1})
    im = InteractionMatrix.from_dataframe(df, user_col="user_id", item_col="item_id")
    item_features = pd.DataFrame(
        {"item_id": ["A", "B", "C"], "embedding": [[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]]}
    )
    return im, item_features


def _run_codegen(definition, node, scope):
    """exec a node's preview fragment in *scope* and return the updated scope."""
    frag = definition.preview(node)
    exec(frag.render(), scope)
    return scope


# ===================================================================
# embedding_similarity (catalog-level algorithm)
# ===================================================================


def test_embedding_fit_returns_fitted_recommender():
    im = _make_interactions()
    item_features = _make_item_features()
    spec = _reg.get_recommender_spec("embedding_similarity")

    fitted = spec.fitter(
        im,
        item_features,
        {"item_id_col": "item_id", "embedding_col": "embedding"},
    )
    assert isinstance(fitted, FittedRecommender)
    assert fitted.algorithm == "embedding_similarity"
    assert fitted.algorithm_family == "content"
    assert fitted.fit_stats["n_interactions"] == im.n_interactions
    assert fitted.fit_stats["sparsity"] == 1.0 - im.density
    assert fitted.fit_stats["embedding_dim"] == 2


def test_embedding_missing_item_features_does_not_crash():
    """Item D is present in interactions but absent from item_features (gets zero vector)."""
    im = _make_interactions()
    item_features = _make_item_features()
    spec = _reg.get_recommender_spec("embedding_similarity")

    fitted = spec.fitter(
        im,
        item_features,
        {"item_id_col": "item_id", "embedding_col": "embedding"},
    )
    result = spec.recommend_fn(fitted, [4], 5, exclude_known=False)
    assert isinstance(result, RecommendationResult)
    assert len(result.recommendations) > 0


def test_embedding_recommend_expected_order_and_scores():
    """User 1 interacted with A ([1,0]) only. Profile = [1,0].
    Cosine to C ([1,1]): sim = 1/sqrt(2) ≈ 0.7071, dist = 0.2929, score = -0.2929.
    Cosine to B ([0,1]): sim = 0, dist = 1, score = -1.
    Expected: C first, B second."""
    im, item_features = _make_single_interaction_fixture()
    spec = _reg.get_recommender_spec("embedding_similarity")

    fitted = spec.fitter(
        im,
        item_features,
        {"item_id_col": "item_id", "embedding_col": "embedding", "metric": "cosine"},
    )
    result = spec.recommend_fn(fitted, [1], 5, exclude_known=True)
    ids = result.recommendations["item_id"].tolist()
    scores = result.recommendations["score"].tolist()

    assert ids[0] == "C"
    assert ids[1] == "B"

    expected_c_dist = 1.0 - 1.0 / np.sqrt(2.0)
    expected_b_dist = 1.0 - 0.0
    assert abs(scores[0] - (-expected_c_dist)) < 1e-10
    assert abs(scores[1] - (-expected_b_dist)) < 1e-10


def test_embedding_duplicate_item_features_raises_typed_error():
    """Duplicate item_id_col values in item_features must raise a typed error, not a raw
    pandas ValueError from .reindex()."""
    im = _make_interactions()
    item_features = pd.DataFrame(
        {
            "item_id": ["A", "A", "B", "C"],
            "embedding": [[1.0, 0.0], [2.0, 0.0], [0.0, 1.0], [1.0, 1.0]],
        }
    )
    spec = _reg.get_recommender_spec("embedding_similarity")

    with pytest.raises(InvalidRecommenderParamsError, match="duplicate"):
        spec.fitter(im, item_features, {"item_id_col": "item_id", "embedding_col": "embedding"})


def test_embedding_exclude_known():
    """User 1 known items (A, B) are excluded from recommendations."""
    im = _make_interactions()
    item_features = _make_item_features()
    spec = _reg.get_recommender_spec("embedding_similarity")

    fitted = spec.fitter(
        im,
        item_features,
        {"item_id_col": "item_id", "embedding_col": "embedding"},
    )
    result = spec.recommend_fn(fitted, [1], 5, exclude_known=True)
    ids = result.recommendations["item_id"].tolist()
    assert "A" not in ids
    assert "B" not in ids


def test_embedding_cold_start_user():
    """Users with no interactions get zero rows."""
    im = _make_interactions()
    item_features = _make_item_features()
    spec = _reg.get_recommender_spec("embedding_similarity")

    fitted = spec.fitter(
        im,
        item_features,
        {"item_id_col": "item_id", "embedding_col": "embedding"},
    )
    result = spec.recommend_fn(fitted, [99], 5, exclude_known=False)
    assert len(result.recommendations) == 0


def test_embedding_determinism():
    """Two independent fit+recommend calls produce identical recommendations."""
    im = _make_interactions()
    item_features = _make_item_features()
    spec = _reg.get_recommender_spec("embedding_similarity")

    f1 = spec.fitter(im, item_features, {"item_id_col": "item_id", "embedding_col": "embedding"})
    f2 = spec.fitter(im, item_features, {"item_id_col": "item_id", "embedding_col": "embedding"})
    r1 = spec.recommend_fn(f1, None, 5, exclude_known=True)
    r2 = spec.recommend_fn(f2, None, 5, exclude_known=True)

    pd.testing.assert_frame_equal(r1.recommendations, r2.recommendations)


# ===================================================================
# RecommendByEmbedding node — codegen/execute
# ===================================================================


def test_recommend_by_embedding_codegen_is_parseable():
    definition = RecommendByEmbedding()
    node = definition.instantiate(
        item_id_col="item_id",
        embedding_col="embedding",
        metric="cosine",
    )
    frag = definition.preview(node)
    code = frag.render()
    ast.parse(code)


def test_recommend_by_embedding_equivalence_execute_vs_codegen():
    """ADR 0002: execute == running the emitted code, for RecommendByEmbedding."""
    im, item_features = _make_single_interaction_fixture()

    definition = RecommendByEmbedding()
    node = definition.instantiate(
        item_id_col="item_id",
        embedding_col="embedding",
        metric="cosine",
    )

    # execute path
    exec_result = definition.execute(
        node,
        {"interactions": im, "item_features": item_features},
    )
    exec_recommender = exec_result["recommender"]
    assert isinstance(exec_recommender, FittedRecommender)

    # codegen path
    scope: dict[str, Any] = {"interactions": im, "item_features": item_features}
    _run_codegen(definition, node, scope)
    codegen_recommender = scope["recommender"]
    assert isinstance(codegen_recommender, FittedRecommender)

    assert exec_recommender.algorithm == codegen_recommender.algorithm
    assert exec_recommender.n_users == codegen_recommender.n_users
    assert exec_recommender.n_items == codegen_recommender.n_items
    assert exec_recommender.fit_stats == codegen_recommender.fit_stats
