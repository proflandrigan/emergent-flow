"""Tests for the GRU4Rec sequential recommender (Epic 15, Task 07).

All tests are gated on ``pytest.importorskip("torch")`` since torch is an optional
dependency. They exercise ``_fit_gru4rec`` / ``_recommend_gru4rec`` directly from the
catalog module (registration is deferred to Task 08).
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from emergentflow.recommend import build_sequences, fit, fit_sequence, recommend
from emergentflow.recommend.catalog import _fit_gru4rec, _recommend_gru4rec
from emergentflow.recommend.errors import InvalidRecommenderParamsError
from emergentflow.recommend.models import FittedRecommender, RecommendationResult
from emergentflow.recommend.registry import known_recommender_keys

_PARAMS = {"embedding_dim": 8, "hidden_dim": 16, "epochs": 5, "seed": 0}


def _make_sequences() -> object:
    df = pd.DataFrame(
        {
            "user_id": [
                "u0",
                "u0",
                "u0",
                "u0",
                "u1",
                "u1",
                "u1",
                "u1",
                "u2",
                "u2",
                "u2",
                "u3",
                "u3",
                "u3",
                "u3",
                "u3",
            ],
            "item_id": [
                "e",
                "f",
                "g",
                "h",
                "a",
                "b",
                "c",
                "d",
                "b",
                "c",
                "d",
                "a",
                "c",
                "d",
                "b",
                "a",
            ],
            "session_id": [
                "s0",
                "s0",
                "s0",
                "s0",
                "s1",
                "s1",
                "s1",
                "s1",
                "s2",
                "s2",
                "s2",
                "s3",
                "s3",
                "s3",
                "s3",
                "s3",
            ],
        }
    )
    return build_sequences(df, user_col="user_id", item_col="item_id", session_col="session_id")


def test_gru4rec_fit_returns_fitted_recommender():
    pytest.importorskip("torch")
    sequences = _make_sequences()
    fitted = _fit_gru4rec(sequences, _PARAMS)

    assert isinstance(fitted, FittedRecommender)
    assert fitted.algorithm == "gru4rec"
    assert fitted.algorithm_family == "sequential"
    assert fitted.n_users == len(sequences.session_ids)
    assert fitted.n_items == len(sequences.item_ids)
    assert fitted.fit_stats["n_sessions"] == len(sequences.sequences)
    assert fitted.fit_stats["n_items"] == len(sequences.item_ids)
    assert fitted.fit_stats["max_seq_len"] == sequences.max_seq_len
    assert fitted.fit_stats["embedding_dim"] == 8
    assert fitted.fit_stats["hidden_dim"] == 16
    assert fitted.fit_stats["epochs"] == 5
    assert math.isfinite(fitted.fit_stats["final_loss"])

    model = fitted.model["model"]
    assert model is not None
    # Embedding table includes the pad token; final linear emits n_items logits.
    assert model.embedding.num_embeddings == fitted.n_items + 1
    assert model.fc.out_features == fitted.n_items


def test_gru4rec_recommend_returns_n_per_session():
    pytest.importorskip("torch")
    sequences = _make_sequences()
    fitted = _fit_gru4rec(sequences, _PARAMS)
    result = _recommend_gru4rec(fitted, ["s1", "s2", "s3"], 3, exclude_known=False)

    assert isinstance(result, RecommendationResult)
    assert len(result.recommendations) == 3 * 3
    for c in ["user_id", "item_id", "rank", "score"]:
        assert c in result.recommendations.columns
    for session_id in ["s1", "s2", "s3"]:
        rows = result.recommendations[result.recommendations["user_id"] == session_id]
        assert len(rows) == 3
        assert rows["rank"].tolist() == [1, 2, 3]


def test_gru4rec_recommend_all_sessions_when_user_ids_none():
    pytest.importorskip("torch")
    sequences = _make_sequences()
    fitted = _fit_gru4rec(sequences, _PARAMS)
    result = _recommend_gru4rec(fitted, None, 2, exclude_known=False)

    assert isinstance(result, RecommendationResult)
    assert len(result.recommendations) == 4 * 2


def test_gru4rec_exclude_known():
    pytest.importorskip("torch")
    sequences = _make_sequences()
    fitted = _fit_gru4rec(sequences, _PARAMS)
    result = _recommend_gru4rec(fitted, ["s1"], 10, exclude_known=True)

    returned_ids = result.recommendations["item_id"].tolist()
    known = {"a", "b", "c", "d"}
    for item_id in returned_ids:
        assert item_id not in known


def test_gru4rec_cold_start_session_skipped():
    pytest.importorskip("torch")
    sequences = _make_sequences()
    fitted = _fit_gru4rec(sequences, _PARAMS)
    result = _recommend_gru4rec(fitted, ["s1", "no_such_session"], 2, exclude_known=False)

    assert isinstance(result, RecommendationResult)
    assert result.recommendations["user_id"].tolist() == ["s1", "s1"]


def test_gru4rec_deterministic_given_seed():
    pytest.importorskip("torch")
    sequences = _make_sequences()

    f1 = _fit_gru4rec(sequences, _PARAMS)
    r1 = _recommend_gru4rec(f1, ["s1", "s2", "s3"], 3, exclude_known=True)
    f2 = _fit_gru4rec(sequences, _PARAMS)
    r2 = _recommend_gru4rec(f2, ["s1", "s2", "s3"], 3, exclude_known=True)

    pd.testing.assert_frame_equal(r1.recommendations, r2.recommendations)


def test_gru4rec_training_loss_decreases():
    pytest.importorskip("torch")
    sequences = _make_sequences()

    f_early = _fit_gru4rec(sequences, {**_PARAMS, "epochs": 1})
    f_late = _fit_gru4rec(sequences, {**_PARAMS, "epochs": 10})

    assert math.isfinite(f_early.fit_stats["final_loss"])
    assert math.isfinite(f_late.fit_stats["final_loss"])
    assert f_late.fit_stats["final_loss"] < f_early.fit_stats["final_loss"]


def test_gru4rec_registered_in_registry():
    pytest.importorskip("torch")
    assert "gru4rec" in known_recommender_keys()


def test_gru4rec_fit_sequence_returns_fitted_recommender():
    pytest.importorskip("torch")
    sequences = _make_sequences()
    fitted = fit_sequence(sequences, algorithm="gru4rec", params=_PARAMS)

    assert isinstance(fitted, FittedRecommender)
    assert fitted.algorithm == "gru4rec"
    assert fitted.algorithm_family == "sequential"


def test_gru4rec_fit_raises_for_sequence_model():
    pytest.importorskip("torch")
    sequences = _make_sequences()
    with pytest.raises(InvalidRecommenderParamsError):
        fit(sequences, algorithm="gru4rec", params=_PARAMS)


def test_gru4rec_recommend_dispatches_through_seam():
    pytest.importorskip("torch")
    sequences = _make_sequences()
    fitted = fit_sequence(sequences, algorithm="gru4rec", params=_PARAMS)
    result = recommend(fitted, n=3)

    assert isinstance(result, RecommendationResult)
    assert len(result.recommendations) == 4 * 3
    for c in ["user_id", "item_id", "rank", "score"]:
        assert c in result.recommendations.columns
