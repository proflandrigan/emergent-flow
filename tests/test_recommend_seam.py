"""Seam tests for ``ef.recommend.fit``/``recommend``/``similar_items`` and the algorithm
allow-list registry (Epic 15, Story 2).

Covers every public-op registration, unknown-algorithm/unknown-param/missing-param errors,
determinism, no-mutation, the ``FittedRecommender`` result-payload degrade path (live model
never serialized), dispatch through ``recommend_fn``/``similar_items_fn``, and the
monkeypatched optional-dependency gate.
"""

from __future__ import annotations

import importlib.util

import numpy as np
import pandas as pd
import pytest

from emergentflow.api import PUBLIC_OPS, is_inspectable
from emergentflow.recommend import fit, recommend, similar_items
from emergentflow.recommend import registry as _reg
from emergentflow.recommend.errors import (
    InvalidRecommenderParamsError,
    MissingOptionalDependencyError,
    UnknownAlgorithmError,
)
from emergentflow.recommend.interactions import InteractionMatrix
from emergentflow.recommend.models import FittedRecommender, RecommendationResult
from emergentflow.recommend.registry import RecommenderSpec, register_recommender


def _make_interaction_matrix() -> InteractionMatrix:
    """Deterministic 3-user x 3-item interaction matrix for seam tests."""
    df = pd.DataFrame(
        {
            "user_id": ["alice", "alice", "bob", "bob", "carol"],
            "item_id": ["item_a", "item_b", "item_a", "item_c", "item_b"],
            "value": [1, 2, 3, 1, 4],
        }
    )
    return InteractionMatrix.from_dataframe(
        df, user_col="user_id", item_col="item_id", value_col="value"
    )


def _pop_fitter(
    interactions: InteractionMatrix,
    item_features: pd.DataFrame | None,
    params: dict,
) -> FittedRecommender:
    return FittedRecommender(
        algorithm="_TestPop",
        algorithm_family="baseline",
        n_users=interactions.n_users,
        n_items=interactions.n_items,
        fit_stats={
            "n_interactions": interactions.n_interactions,
            "n_items": interactions.n_items,
        },
        model={"matrix": interactions.matrix, "item_ids": interactions.item_ids},
    )


def _pop_recommend_fn(
    recommender: FittedRecommender,
    user_ids: list | None,
    n: int,
    exclude_known: bool,
) -> RecommendationResult:
    matrix = recommender.model["matrix"]
    item_ids = recommender.model["item_ids"]
    sums = matrix.sum(axis=0).A1
    sorted_indices = np.argsort(-sums)
    rows = []
    for uid in user_ids or []:
        for rank, idx in enumerate(sorted_indices[:n], start=1):
            rows.append(
                {"user_id": uid, "item_id": item_ids[idx], "rank": rank, "score": float(sums[idx])}
            )
    return RecommendationResult(recommendations=pd.DataFrame(rows))


_TestPopSpec = RecommenderSpec(
    key="_TestPop",
    family="baseline",
    fitter=_pop_fitter,
    recommend_fn=_pop_recommend_fn,
)


def test_fit_and_recommend_are_registered_public_ops():
    assert "ef.recommend.fit" in PUBLIC_OPS
    assert "ef.recommend.recommend" in PUBLIC_OPS
    assert "ef.recommend.similar_items" in PUBLIC_OPS


def test_fit_returns_inspectable_fitted_recommender():
    register_recommender(_TestPopSpec)
    try:
        im = _make_interaction_matrix()
        fr = fit(im, algorithm="_TestPop", params={})
        assert isinstance(fr, FittedRecommender)
        assert is_inspectable(fr)
        assert fr.algorithm_family == "baseline"
    finally:
        _reg._REGISTRY.pop("_TestPop", None)


def test_unknown_algorithm_key_raises():
    im = _make_interaction_matrix()
    with pytest.raises(UnknownAlgorithmError):
        fit(im, algorithm="NotAnAlgorithm", params={})


def test_unknown_param_raises():
    register_recommender(_TestPopSpec)
    try:
        im = _make_interaction_matrix()
        with pytest.raises(InvalidRecommenderParamsError):
            fit(im, algorithm="_TestPop", params={"bogus_param": 1})
    finally:
        _reg._REGISTRY.pop("_TestPop", None)


def test_missing_required_param_raises():
    spec = RecommenderSpec(
        key="_TestRequiresK",
        family="baseline",
        fitter=_pop_fitter,
        recommend_fn=_pop_recommend_fn,
        required_params=("k",),
    )
    register_recommender(spec)
    try:
        im = _make_interaction_matrix()
        with pytest.raises(InvalidRecommenderParamsError):
            fit(im, algorithm="_TestRequiresK", params={})
    finally:
        _reg._REGISTRY.pop("_TestRequiresK", None)


def test_fit_is_deterministic():
    register_recommender(_TestPopSpec)
    try:
        im = _make_interaction_matrix()
        a = fit(im, algorithm="_TestPop", params={})
        b = fit(im, algorithm="_TestPop", params={})
        assert a.fit_stats == b.fit_stats
        sums_a = a.model["matrix"].sum(axis=0).A1.tolist()
        sums_b = b.model["matrix"].sum(axis=0).A1.tolist()
        assert sums_a == sums_b
    finally:
        _reg._REGISTRY.pop("_TestPop", None)


def test_fit_does_not_mutate_interactions():
    register_recommender(_TestPopSpec)
    try:
        im = _make_interaction_matrix()
        before_nnz = im.matrix.nnz
        before_users = list(im.user_ids)
        before_items = list(im.item_ids)
        fit(im, algorithm="_TestPop", params={})
        assert im.matrix.nnz == before_nnz
        assert list(im.user_ids) == before_users
        assert list(im.item_ids) == before_items
    finally:
        _reg._REGISTRY.pop("_TestPop", None)


def test_live_model_never_serialized_in_payload():
    from emergentflow.server.payload import to_payload

    register_recommender(_TestPopSpec)
    try:
        im = _make_interaction_matrix()
        fr = fit(im, algorithm="_TestPop", params={})
        payload = to_payload(fr)
        assert payload["kind"] == "record"
        assert payload["fields"]["model"]["kind"] == "unsupported"
        assert payload["fields"]["fit_stats"]["kind"] == "json"
    finally:
        _reg._REGISTRY.pop("_TestPop", None)


def test_recommend_dispatches_to_recommend_fn_and_returns_recommendation_result():
    register_recommender(_TestPopSpec)
    try:
        im = _make_interaction_matrix()
        fr = fit(im, algorithm="_TestPop", params={})
        result = recommend(fr, user_ids=["alice"], n=1)
        assert isinstance(result, RecommendationResult)
        assert list(result.recommendations.columns) == ["user_id", "item_id", "rank", "score"]
        assert len(result.recommendations) == 1
        assert result.recommendations["user_id"].iloc[0] == "alice"
    finally:
        _reg._REGISTRY.pop("_TestPop", None)


def test_similar_items_raises_when_unsupported():
    register_recommender(_TestPopSpec)
    try:
        im = _make_interaction_matrix()
        fr = fit(im, algorithm="_TestPop", params={})
        with pytest.raises(InvalidRecommenderParamsError):
            similar_items(fr, item_ids=["item_a"])
    finally:
        _reg._REGISTRY.pop("_TestPop", None)


def test_similar_items_dispatches_when_supported():
    def _similar_fn(recommender: FittedRecommender, item_ids: list, n: int) -> RecommendationResult:
        rows = []
        for iid in item_ids:
            for rank in range(1, n + 1):
                rows.append({"user_id": None, "item_id": iid, "rank": rank, "score": 1.0 / rank})
        return RecommendationResult(recommendations=pd.DataFrame(rows))

    def _fitter(interactions, item_features, params):
        return FittedRecommender(
            algorithm="_TestSimilar",
            algorithm_family="baseline",
            n_users=interactions.n_users,
            n_items=interactions.n_items,
            fit_stats={"n_interactions": interactions.n_interactions},
            model={"matrix": interactions.matrix, "item_ids": interactions.item_ids},
        )

    spec = RecommenderSpec(
        key="_TestSimilar",
        family="baseline",
        fitter=_fitter,
        recommend_fn=_pop_recommend_fn,
        similar_items_fn=_similar_fn,
    )
    register_recommender(spec)
    try:
        im = _make_interaction_matrix()
        fr = fit(im, algorithm="_TestSimilar", params={})
        result = similar_items(fr, item_ids=["item_a"], n=2)
        assert isinstance(result, RecommendationResult)
        assert len(result.recommendations) == 2
        assert list(result.recommendations["item_id"]) == ["item_a", "item_a"]
        assert list(result.recommendations["rank"]) == [1, 2]
    finally:
        _reg._REGISTRY.pop("_TestSimilar", None)


def test_missing_optional_dependency_raises_typed_error(monkeypatch):
    def _fake_find_spec(name, *args, **kwargs):
        return None

    monkeypatch.setattr(importlib.util, "find_spec", _fake_find_spec)

    def _never_called(interactions, item_features, params):
        raise AssertionError("fitter must not run when the required extra is absent")

    spec = RecommenderSpec(
        key="_TestMissingDep",
        family="baseline",
        fitter=_never_called,
        recommend_fn=_pop_recommend_fn,
        requires_extra="emergentflow[recommend]",
    )
    register_recommender(spec)
    try:
        im = _make_interaction_matrix()
        with pytest.raises(MissingOptionalDependencyError):
            fit(im, algorithm="_TestMissingDep", params={})
    finally:
        _reg._REGISTRY.pop("_TestMissingDep", None)
