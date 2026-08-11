"""Tests for the two-tower deep recommender (Epic 15, Story 11).

Part A: base-install typed-error test (no torch required).
Part B: pytest.importorskip("torch")-gated tests via the generic node/registry path
       (item-features only, or no features).
Part C: pytest.importorskip("torch")-gated tests via the dedicated ``fit_two_tower()``
       wrapper / ``RecommendFitTwoTower`` node (both item AND user features).
"""

from __future__ import annotations

import ast
import importlib.util
from typing import Any

import pandas as pd
import pytest

from emergentflow.nodes.examples.recommend_fit import RecommendFit
from emergentflow.nodes.examples.recommend_fit_two_tower import RecommendFitTwoTower
from emergentflow.nodes.examples.recommend_recommend import Recommend
from emergentflow.recommend import registry as _reg
from emergentflow.recommend.errors import (
    InvalidRecommenderParamsError,
    MissingOptionalDependencyError,
)
from emergentflow.recommend.interactions import InteractionMatrix
from emergentflow.recommend.models import FittedRecommender, RecommendationResult

# ---------------------------------------------------------------------------
# Part A — missing-extra typed error
# ---------------------------------------------------------------------------


def test_two_tower_missing_extra_raises_typed_error_when_torch_absent():
    """If torch is not installed, ef.recommend.fit raises MissingOptionalDependencyError.
    This test only runs its assertion meaningfully when torch is ABSENT; if it happens to be
    installed in this environment, skip (the missing-extra path can't be exercised)."""
    if importlib.util.find_spec("torch") is not None:
        pytest.skip("torch is installed in this environment; cannot test the absent-extra path")

    import emergentflow as ef

    df = pd.DataFrame({"user_id": [1, 1, 2], "item_id": ["A", "B", "A"]})
    im = InteractionMatrix.from_dataframe(df, user_col="user_id", item_col="item_id")

    with pytest.raises(MissingOptionalDependencyError):
        ef.recommend.fit(im, algorithm="two_tower", params={})


# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------


def _make_two_tower_fixture() -> InteractionMatrix:
    """5 users x 4 items — same shape as the als/ncf fixtures."""
    df = pd.DataFrame(
        {
            "user_id": [1, 1, 1, 2, 2, 2, 3, 3, 3, 4, 4, 4, 5, 5, 5],
            "item_id": ["A", "B", "C", "A", "B", "D", "B", "C", "D", "A", "C", "D", "A", "B", "D"],
            "value": [5, 3, 1, 4, 2, 1, 3, 5, 2, 2, 4, 1, 3, 1, 5],
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


_TT_PARAMS = {"user_embedding_dim": 4, "item_embedding_dim": 4, "epochs": 3, "seed": 0}

_ITEM_FEATURES = pd.DataFrame(
    {"item_id": ["A", "B", "C", "D"], "popularity": [10.0, 5.0, 3.0, 1.0]}
)
_USER_FEATURES = pd.DataFrame({"user_id": [1, 2, 3, 4, 5], "age": [25.0, 30.0, 22.0, 40.0, 35.0]})

# ---------------------------------------------------------------------------
# Part B — generic item-only path (via _reg.get_recommender_spec /
#          RecommendFit / Recommend)
# ---------------------------------------------------------------------------


def test_two_tower_fit_returns_fitted_recommender():
    pytest.importorskip("torch")
    im = _make_two_tower_fixture()
    spec = _reg.get_recommender_spec("two_tower")
    result = spec.fitter(im, None, _TT_PARAMS)
    assert isinstance(result, FittedRecommender)
    assert result.algorithm == "two_tower"
    assert result.algorithm_family == "deep"


def test_two_tower_recommend_returns_valid_result():
    pytest.importorskip("torch")
    im = _make_two_tower_fixture()
    spec = _reg.get_recommender_spec("two_tower")
    fitted = spec.fitter(im, None, _TT_PARAMS)
    result = spec.recommend_fn(fitted, [1], 3, exclude_known=False)
    assert isinstance(result, RecommendationResult)
    assert len(result.recommendations) > 0
    cols = list(result.recommendations.columns)
    for c in ["user_id", "item_id", "rank", "score"]:
        assert c in cols
    ranks = result.recommendations["rank"].tolist()
    assert ranks == list(range(1, len(ranks) + 1))


def test_two_tower_exclude_known():
    pytest.importorskip("torch")
    im = _make_two_tower_fixture()
    spec = _reg.get_recommender_spec("two_tower")
    fitted = spec.fitter(im, None, _TT_PARAMS)
    result = spec.recommend_fn(fitted, [1], 10, exclude_known=True)
    returned_ids = result.recommendations["item_id"].tolist()
    assert "A" not in returned_ids
    assert "B" not in returned_ids
    assert "C" not in returned_ids


def test_two_tower_determinism():
    pytest.importorskip("torch")
    im = _make_two_tower_fixture()
    spec = _reg.get_recommender_spec("two_tower")

    f1 = spec.fitter(im, None, _TT_PARAMS)
    r1 = spec.recommend_fn(f1, [1, 2, 3], 3, exclude_known=True)
    f2 = spec.fitter(im, None, _TT_PARAMS)
    r2 = spec.recommend_fn(f2, [1, 2, 3], 3, exclude_known=True)

    pd.testing.assert_frame_equal(r1.recommendations, r2.recommendations)


def test_two_tower_mismatched_embedding_dims_raises():
    pytest.importorskip("torch")
    im = _make_two_tower_fixture()
    spec = _reg.get_recommender_spec("two_tower")
    with pytest.raises(InvalidRecommenderParamsError):
        spec.fitter(im, None, {"user_embedding_dim": 4, "item_embedding_dim": 8})


def test_two_tower_invalid_loss_raises():
    pytest.importorskip("torch")
    im = _make_two_tower_fixture()
    spec = _reg.get_recommender_spec("two_tower")
    with pytest.raises(InvalidRecommenderParamsError):
        spec.fitter(im, None, {**_TT_PARAMS, "loss": "not_a_real_loss"})


@pytest.mark.parametrize("loss", ["bce", "bpr_loss", "softmax_cross_entropy"])
def test_two_tower_loss_variants_run(loss):
    pytest.importorskip("torch")
    im = _make_two_tower_fixture()
    spec = _reg.get_recommender_spec("two_tower")
    fitted = spec.fitter(im, None, {**_TT_PARAMS, "loss": loss})
    result = spec.recommend_fn(fitted, [1], 3, exclude_known=True)
    assert isinstance(result, RecommendationResult)
    assert len(result.recommendations) > 0


def test_two_tower_codegen_is_parseable():
    pytest.importorskip("torch")
    fit_def = RecommendFit()
    fit_node = fit_def.instantiate(algorithm="two_tower", params=_TT_PARAMS)
    frag = fit_def.preview(fit_node)
    code = frag.render()
    ast.parse(code)


def test_two_tower_equivalence_execute_vs_codegen():
    pytest.importorskip("torch")
    im = _make_two_tower_fixture()
    fit_def = RecommendFit()
    fit_node = fit_def.instantiate(algorithm="two_tower", params=_TT_PARAMS)

    rec_def = Recommend()
    rec_node = rec_def.instantiate(user_ids=[1, 2, 3, 4, 5], n=3, exclude_known=True)

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
# Part C — dedicated wrapper / dedicated node, with BOTH item and user features
# ---------------------------------------------------------------------------


def test_two_tower_fit_two_tower_wrapper_with_both_features():
    pytest.importorskip("torch")
    import emergentflow as ef

    im = _make_two_tower_fixture()
    fitted = ef.recommend.fit_two_tower(
        im, item_features=_ITEM_FEATURES, user_features=_USER_FEATURES, params=_TT_PARAMS
    )
    assert isinstance(fitted, FittedRecommender)
    assert fitted.algorithm == "two_tower"
    assert fitted.fit_stats["item_feature_dim"] == 1
    assert fitted.fit_stats["user_feature_dim"] == 1

    result = ef.recommend.recommend(fitted, user_ids=[1, 2], n=3, exclude_known=True)
    assert isinstance(result, RecommendationResult)
    assert len(result.recommendations) > 0


def test_two_tower_node_codegen_is_parseable():
    pytest.importorskip("torch")
    fit_def = RecommendFitTwoTower()
    fit_node = fit_def.instantiate(params=_TT_PARAMS)
    frag = fit_def.preview(fit_node)
    code = frag.render()
    ast.parse(code)


def test_two_tower_node_equivalence_execute_vs_codegen():
    pytest.importorskip("torch")
    im = _make_two_tower_fixture()
    fit_def = RecommendFitTwoTower()
    fit_node = fit_def.instantiate(params=_TT_PARAMS)

    rec_def = Recommend()
    rec_node = rec_def.instantiate(user_ids=[1, 2], n=3, exclude_known=True)

    # execute path
    fit_result = fit_def.execute(
        fit_node,
        {"interactions": im, "item_features": _ITEM_FEATURES, "user_features": _USER_FEATURES},
    )
    exec_result = rec_def.execute(rec_node, {"recommender": fit_result["recommender"]})

    # codegen path
    scope: dict[str, Any] = {
        "interactions": im,
        "item_features": _ITEM_FEATURES,
        "user_features": _USER_FEATURES,
    }
    _run_codegen(fit_def, fit_node, scope)
    _run_codegen(rec_def, rec_node, scope)
    codegen_result = scope["result"]

    pd.testing.assert_frame_equal(
        exec_result["result"].recommendations,
        codegen_result.recommendations,
    )


# ---------------------------------------------------------------------------
# Part D — id-embedding toggles (metadata-only / mixed modes)
# ---------------------------------------------------------------------------


def test_two_tower_user_metadata_only_with_user_features():
    pytest.importorskip("torch")
    import emergentflow as ef

    im = _make_two_tower_fixture()
    fitted = ef.recommend.fit_two_tower(
        im,
        item_features=_ITEM_FEATURES,
        user_features=_USER_FEATURES,
        params={**_TT_PARAMS, "use_user_id_embedding": False, "use_item_id_embedding": True},
    )
    assert isinstance(fitted, FittedRecommender)
    assert fitted.fit_stats["user_feature_dim"] > 0
    assert fitted.model["use_user_id_embedding"] is False
    assert fitted.model["use_item_id_embedding"] is True

    result = ef.recommend.recommend(fitted, user_ids=[1, 2], n=3, exclude_known=True)
    assert isinstance(result, RecommendationResult)
    assert len(result.recommendations) > 0


def test_two_tower_item_metadata_only_with_item_features():
    pytest.importorskip("torch")
    import emergentflow as ef

    im = _make_two_tower_fixture()
    fitted = ef.recommend.fit_two_tower(
        im,
        item_features=_ITEM_FEATURES,
        user_features=_USER_FEATURES,
        params={**_TT_PARAMS, "use_user_id_embedding": True, "use_item_id_embedding": False},
    )
    assert isinstance(fitted, FittedRecommender)
    assert fitted.fit_stats["item_feature_dim"] > 0
    assert fitted.model["use_user_id_embedding"] is True
    assert fitted.model["use_item_id_embedding"] is False

    result = ef.recommend.recommend(fitted, user_ids=[1, 2], n=3, exclude_known=True)
    assert isinstance(result, RecommendationResult)
    assert len(result.recommendations) > 0


def test_two_tower_metadata_only_both_towers_with_features():
    pytest.importorskip("torch")
    import emergentflow as ef

    im = _make_two_tower_fixture()
    fitted = ef.recommend.fit_two_tower(
        im,
        item_features=_ITEM_FEATURES,
        user_features=_USER_FEATURES,
        params={**_TT_PARAMS, "use_user_id_embedding": False, "use_item_id_embedding": False},
    )
    assert isinstance(fitted, FittedRecommender)
    assert fitted.model["use_user_id_embedding"] is False
    assert fitted.model["use_item_id_embedding"] is False

    result = ef.recommend.recommend(fitted, user_ids=[1, 2], n=3, exclude_known=True)
    assert isinstance(result, RecommendationResult)
    assert len(result.recommendations) > 0


def test_two_tower_user_metadata_only_without_user_features_raises():
    pytest.importorskip("torch")
    import emergentflow as ef

    im = _make_two_tower_fixture()
    with pytest.raises(InvalidRecommenderParamsError):
        ef.recommend.fit_two_tower(
            im,
            item_features=_ITEM_FEATURES,
            user_features=None,
            params={**_TT_PARAMS, "use_user_id_embedding": False},
        )
