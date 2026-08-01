"""Tests for ef.recommend.save_model / ef.recommend.load_model.

Covers round-trip persistence and error handling for FittedRecommender serialization.
"""

from __future__ import annotations

import pathlib

import pandas as pd
import pytest

# Register the seed catalog so a popularity fitter exists
from emergentflow.recommend import (
    catalog,  # noqa: F401
    fit,
    load_model,
    random_split,
    recommend,
    save_model,
)
from emergentflow.recommend.interactions import InteractionMatrix
from emergentflow.recommend.models import FittedRecommender


@pytest.fixture
def interaction_matrix() -> InteractionMatrix:
    """A tiny implicit interaction matrix (3 users, 4 items)."""
    df = pd.DataFrame(
        {
            "user_id": ["u1", "u1", "u1", "u2", "u2", "u3"],
            "item_id": ["i1", "i2", "i3", "i1", "i4", "i2"],
            "rating": [1, 1, 1, 1, 1, 1],
        }
    )
    train, _test = random_split(
        df, user_col="user_id", item_col="item_id", test_ratio=0.2, seed=0, implicit=True
    )
    return train


def test_recommend_save_model_returns_artifact_ref(
    interaction_matrix: InteractionMatrix, tmp_path: pathlib.Path
) -> None:
    """save_model returns an ArtifactRef with the correct URI."""
    rec = fit(interaction_matrix, algorithm="popularity")
    path = tmp_path / "popularity.joblib"
    ref = save_model(rec, path)
    assert ref.uri == str(path)
    assert path.is_file()
    assert path.with_suffix(path.suffix + ".meta.json").is_file()


def test_recommend_save_load_round_trip(
    interaction_matrix: InteractionMatrix, tmp_path: pathlib.Path
) -> None:
    """fit -> save -> load -> recommend produces consistent results."""
    rec = fit(interaction_matrix, algorithm="popularity")
    original = recommend(rec, n=2)

    path = tmp_path / "popularity.joblib"
    save_model(rec, path)
    loaded = load_model(path)

    reloaded = recommend(loaded, n=2)
    assert isinstance(loaded, FittedRecommender)
    assert loaded.algorithm == "popularity"
    assert loaded.algorithm_family == "baseline"
    pd.testing.assert_frame_equal(original.recommendations, reloaded.recommendations)


def test_recommend_save_model_writes_meta_sidecar(
    interaction_matrix: InteractionMatrix, tmp_path: pathlib.Path
) -> None:
    """save_model writes a .meta.json sidecar with algorithm info."""
    import json

    rec = fit(interaction_matrix, algorithm="popularity")
    path = tmp_path / "popularity.joblib"
    save_model(rec, path)

    meta_path = path.with_suffix(path.suffix + ".meta.json")
    assert meta_path.is_file()
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["algorithm"] == "popularity"
    assert meta["algorithm_family"] == "baseline"
    assert meta["n_users"] == 3
    assert meta["n_items"] == 4


def test_recommend_load_model_raises_file_not_found(tmp_path: pathlib.Path) -> None:
    """load_model raises FileNotFoundError for a missing file."""

    path = tmp_path / "nonexistent.joblib"
    with pytest.raises(FileNotFoundError):
        load_model(path)


def test_recommend_load_model_raises_on_wrong_type(tmp_path: pathlib.Path) -> None:
    """load_model raises ModelPersistenceError when loaded object is not FittedRecommender."""
    import joblib

    from emergentflow.ml.errors import ModelPersistenceError

    path = tmp_path / "not_a_recommender.joblib"
    joblib.dump("this is a string", path)

    with pytest.raises(ModelPersistenceError):
        load_model(path)


def test_recommend_save_model_with_artifact_ref(
    interaction_matrix: InteractionMatrix, tmp_path: pathlib.Path
) -> None:
    """load_model accepts an ArtifactRef as input."""
    rec = fit(interaction_matrix, algorithm="popularity")
    path = tmp_path / "popularity.joblib"
    ref = save_model(rec, path)
    loaded = load_model(ref)
    assert isinstance(loaded, FittedRecommender)
    assert loaded.algorithm == "popularity"
