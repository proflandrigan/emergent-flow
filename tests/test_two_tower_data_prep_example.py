"""End-to-end example: shaping a packed lists DataFrame into a fitted two-tower recommender.

Executable companion to docs/recommender-data-prep.md -- exercises ef.clean.explode_lists and
ef.clean.encode_lists feeding ef.recommend.prepare_interactions / fit_two_tower. The two-tower
fit needs the optional torch extra, so that portion is importorskip-gated.
"""

from __future__ import annotations

import pandas as pd
import pytest

import emergentflow as ef


def _packed_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "user_id": ["u1", "u2", "u3", "u4"],
            "item_ids": [["i1", "i2", "i3"], ["i2", "i4"], ["i1", "i4"], ["i3", "i4", "i1"]],
            "ratings": [[5, 3, 4], [2, 5], [4, 4], [3, 5, 2]],
            "fav_genres": [["rock", "jazz"], ["pop"], ["rock"], ["jazz", "pop"]],
        }
    )


def test_explode_lists_aligned_expands_interactions():
    """Aligned multi-column explode yields tidy long events (no cross-product)."""
    packed = _packed_frame()
    events = ef.clean.explode_lists(packed.copy(), columns=["item_ids", "ratings"])
    # 3 + 2 + 2 + 3 = 10 events
    assert len(events) == 10
    # aligned: u1's first event is (i1, 5), not a cross-join
    u1 = events[events["user_id"] == "u1"].reset_index(drop=True)
    assert list(u1["item_ids"]) == ["i1", "i2", "i3"]
    assert list(u1["ratings"]) == [5, 3, 4]
    # input not mutated
    assert isinstance(packed["item_ids"].iloc[0], list)


def test_encode_lists_builds_numeric_user_features():
    """Multi-hot encoding produces numeric, two-tower-ready feature columns keyed by user_id."""
    packed = _packed_frame()
    user_features = ef.clean.encode_lists(
        packed[["user_id", "fav_genres"]].copy(), column="fav_genres", prefix="genre"
    )
    assert "user_id" in user_features.columns
    assert set(user_features.columns) == {"user_id", "genre_jazz", "genre_pop", "genre_rock"}
    # u1 = [rock, jazz]
    u1 = user_features[user_features["user_id"] == "u1"].iloc[0]
    assert u1["genre_rock"] == 1 and u1["genre_jazz"] == 1 and u1["genre_pop"] == 0


def test_packed_lists_to_two_tower_end_to_end():
    """Full pipeline: packed -> explode -> prepare_interactions -> encode -> fit_two_tower."""
    pytest.importorskip("torch")
    packed = _packed_frame()

    events = ef.clean.explode_lists(packed.copy(), columns=["item_ids", "ratings"])
    interactions = ef.recommend.prepare_interactions(
        events, user_col="user_id", item_col="item_ids", value_col="ratings"
    )

    user_features = ef.clean.encode_lists(
        packed[["user_id", "fav_genres"]].copy(), column="fav_genres", prefix="genre"
    )
    # item-side features: one row per item, an item_id column + a numeric column
    item_features = pd.DataFrame(
        {"item_id": ["i1", "i2", "i3", "i4"], "popularity": [3.0, 2.0, 2.0, 3.0]}
    )

    recommender = ef.recommend.fit_two_tower(
        interactions,
        user_features=user_features,
        item_features=item_features,
        params={"epochs": 2, "user_embedding_dim": 8, "item_embedding_dim": 8, "seed": 0},
    )
    result = ef.recommend.recommend(recommender, n=3)
    # Mirrors tests/test_recommend_deep_two_tower.py's inspection of ef.recommend.recommend
    # output: a RecommendationResult wrapping a non-empty tidy DataFrame with the standard
    # user_id/item_id/rank/score columns.
    assert len(result.recommendations) > 0
    cols = list(result.recommendations.columns)
    for c in ["user_id", "item_id", "rank", "score"]:
        assert c in cols
