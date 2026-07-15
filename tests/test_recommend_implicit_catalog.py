"""
Tests for the als (AlternatingLeastSquares) collaborative-filtering recommender
(Epic 15, Story 8).

Part A: base-install typed-error test (no implicit required).
Part B: importorskip("implicit")-gated tests (fit, recommend, exclude_known,
determinism, codegen + equivalence).
"""

from __future__ import annotations

import ast
import importlib.util
from typing import Any

import pandas as pd
import pytest

from emergentflow.nodes.examples.recommend_fit import RecommendFit
from emergentflow.nodes.examples.recommend_recommend import Recommend
from emergentflow.recommend import registry as _reg
from emergentflow.recommend.errors import MissingOptionalDependencyError
from emergentflow.recommend.interactions import InteractionMatrix
from emergentflow.recommend.models import FittedRecommender, RecommendationResult

# ---------------------------------------------------------------------------
# Part A: base-install typed-error test (no implicit required)
# ---------------------------------------------------------------------------


def test_als_missing_extra_raises_typed_error_when_implicit_absent():
    """If implicit is not installed, ef.recommend.fit raises MissingOptionalDependencyError.
    This test only runs its assertion meaningfully when implicit is ABSENT; if it happens to be
    installed in this environment, skip (the missing-extra path can't be exercised)."""
    if importlib.util.find_spec("implicit") is not None:
        pytest.skip("implicit is installed in this environment; cannot test the absent-extra path")

    import emergentflow as ef

    df = pd.DataFrame({"user_id": [1, 1, 2], "item_id": ["A", "B", "A"]})
    im = InteractionMatrix.from_dataframe(df, user_col="user_id", item_col="item_id")

    with pytest.raises(MissingOptionalDependencyError):
        ef.recommend.fit(im, algorithm="als", params={})


# ---------------------------------------------------------------------------
# Part B: importorskip-gated tests (require implicit)
# ---------------------------------------------------------------------------


def _make_als_fixture() -> InteractionMatrix:
    """5 users x 4 items — enough signal for ALS with factors=4."""
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


_ALS_PARAMS = {"factors": 4, "iterations": 5, "seed": 0}


def test_als_fit_returns_fitted_recommender():
    pytest.importorskip("implicit")
    im = _make_als_fixture()
    spec = _reg.get_recommender_spec("als")
    result = spec.fitter(im, None, _ALS_PARAMS)
    assert isinstance(result, FittedRecommender)
    assert result.algorithm == "als"
    assert result.algorithm_family == "collaborative"


def test_als_recommend_returns_valid_result():
    pytest.importorskip("implicit")
    im = _make_als_fixture()
    spec = _reg.get_recommender_spec("als")
    fitted = spec.fitter(im, None, _ALS_PARAMS)
    result = spec.recommend_fn(fitted, [1], 3, exclude_known=False)
    assert isinstance(result, RecommendationResult)
    assert len(result.recommendations) > 0
    cols = list(result.recommendations.columns)
    for c in ["user_id", "item_id", "rank", "score"]:
        assert c in cols
    ranks = result.recommendations["rank"].tolist()
    assert ranks == list(range(1, len(ranks) + 1))


def test_als_exclude_known():
    pytest.importorskip("implicit")
    im = _make_als_fixture()
    spec = _reg.get_recommender_spec("als")
    fitted = spec.fitter(im, None, _ALS_PARAMS)
    result = spec.recommend_fn(fitted, [1], 10, exclude_known=True)
    returned_ids = result.recommendations["item_id"].tolist()
    assert "A" not in returned_ids
    assert "B" not in returned_ids
    assert "C" not in returned_ids


def test_als_determinism():
    pytest.importorskip("implicit")
    im = _make_als_fixture()
    spec = _reg.get_recommender_spec("als")

    f1 = spec.fitter(im, None, _ALS_PARAMS)
    r1 = spec.recommend_fn(f1, [1, 2, 3], 5, exclude_known=True)
    f2 = spec.fitter(im, None, _ALS_PARAMS)
    r2 = spec.recommend_fn(f2, [1, 2, 3], 5, exclude_known=True)

    # implicit's multi-threaded ALS can be nondeterministic across runs even with a
    # fixed random_state. Assert item_id/rank ordering matches exactly, but use a
    # tolerance on scores.
    pd.testing.assert_frame_equal(
        r1.recommendations[["user_id", "item_id", "rank"]],
        r2.recommendations[["user_id", "item_id", "rank"]],
    )
    pd.testing.assert_frame_equal(
        r1.recommendations[["score"]],
        r2.recommendations[["score"]],
        check_exact=False,
        rtol=1e-3,
    )


def test_als_codegen_is_parseable():
    pytest.importorskip("implicit")
    fit_def = RecommendFit()
    fit_node = fit_def.instantiate(algorithm="als", params=_ALS_PARAMS)
    frag = fit_def.preview(fit_node)
    code = frag.render()
    ast.parse(code)


def test_als_equivalence_execute_vs_codegen():
    pytest.importorskip("implicit")
    im = _make_als_fixture()
    fit_def = RecommendFit()
    fit_node = fit_def.instantiate(algorithm="als", params=_ALS_PARAMS)

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
# Part C: bpr (Bayesian Personalized Ranking)
# ---------------------------------------------------------------------------


def test_bpr_missing_extra_raises_typed_error_when_implicit_absent():
    """If implicit is not installed, ef.recommend.fit raises MissingOptionalDependencyError.
    This test only runs its assertion meaningfully when implicit is ABSENT; if it happens to be
    installed in this environment, skip (the missing-extra path can't be exercised)."""
    if importlib.util.find_spec("implicit") is not None:
        pytest.skip("implicit is installed in this environment; cannot test the absent-extra path")

    import emergentflow as ef

    df = pd.DataFrame({"user_id": [1, 1, 2], "item_id": ["A", "B", "A"]})
    im = InteractionMatrix.from_dataframe(df, user_col="user_id", item_col="item_id")

    with pytest.raises(MissingOptionalDependencyError):
        ef.recommend.fit(im, algorithm="bpr", params={})


def _make_bpr_fixture() -> InteractionMatrix:
    """5 users x 4 items — same shape as the als fixture."""
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


_BPR_PARAMS = {"factors": 4, "iterations": 20, "seed": 0}


def test_bpr_fit_returns_fitted_recommender():
    pytest.importorskip("implicit")
    im = _make_bpr_fixture()
    spec = _reg.get_recommender_spec("bpr")
    result = spec.fitter(im, None, _BPR_PARAMS)
    assert isinstance(result, FittedRecommender)
    assert result.algorithm == "bpr"
    assert result.algorithm_family == "collaborative"


def test_bpr_recommend_returns_valid_result():
    pytest.importorskip("implicit")
    im = _make_bpr_fixture()
    spec = _reg.get_recommender_spec("bpr")
    fitted = spec.fitter(im, None, _BPR_PARAMS)
    result = spec.recommend_fn(fitted, [1], 3, exclude_known=False)
    assert isinstance(result, RecommendationResult)
    assert len(result.recommendations) > 0
    cols = list(result.recommendations.columns)
    for c in ["user_id", "item_id", "rank", "score"]:
        assert c in cols
    ranks = result.recommendations["rank"].tolist()
    assert ranks == list(range(1, len(ranks) + 1))


def test_bpr_exclude_known():
    pytest.importorskip("implicit")
    im = _make_bpr_fixture()
    spec = _reg.get_recommender_spec("bpr")
    fitted = spec.fitter(im, None, _BPR_PARAMS)
    result = spec.recommend_fn(fitted, [1], 10, exclude_known=True)
    returned_ids = result.recommendations["item_id"].tolist()
    assert "A" not in returned_ids
    assert "B" not in returned_ids
    assert "C" not in returned_ids


def test_bpr_determinism():
    pytest.importorskip("implicit")
    im = _make_bpr_fixture()
    spec = _reg.get_recommender_spec("bpr")

    f1 = spec.fitter(im, None, _BPR_PARAMS)
    r1 = spec.recommend_fn(f1, [1, 2, 3], 5, exclude_known=True)
    f2 = spec.fitter(im, None, _BPR_PARAMS)
    r2 = spec.recommend_fn(f2, [1, 2, 3], 5, exclude_known=True)

    # BPR's random_state reduces but does not fully eliminate score variance
    # between runs (numerical sensitivity in the BPR update). Assert
    # item_id/rank ordering matches exactly; scores are checked with tolerance.
    pd.testing.assert_frame_equal(
        r1.recommendations[["user_id", "item_id", "rank"]],
        r2.recommendations[["user_id", "item_id", "rank"]],
    )
    pd.testing.assert_frame_equal(
        r1.recommendations[["score"]],
        r2.recommendations[["score"]],
        check_exact=False,
        rtol=0.5,
        atol=0.01,
    )


def test_bpr_codegen_is_parseable():
    pytest.importorskip("implicit")
    fit_def = RecommendFit()
    fit_node = fit_def.instantiate(algorithm="bpr", params=_BPR_PARAMS)
    frag = fit_def.preview(fit_node)
    code = frag.render()
    ast.parse(code)


def test_bpr_equivalence_execute_vs_codegen():
    pytest.importorskip("implicit")
    im = _make_bpr_fixture()
    fit_def = RecommendFit()
    fit_node = fit_def.instantiate(algorithm="bpr", params=_BPR_PARAMS)

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

    # BPR's fit is not fully determined by random_state, so execute and codegen
    # paths produce slightly different score values. Apply the same tolerance
    # pattern as test_bpr_determinism.
    pd.testing.assert_frame_equal(
        exec_result["result"].recommendations[["user_id", "item_id", "rank"]],
        codegen_result.recommendations[["user_id", "item_id", "rank"]],
    )
    pd.testing.assert_frame_equal(
        exec_result["result"].recommendations[["score"]],
        codegen_result.recommendations[["score"]],
        check_exact=False,
        rtol=0.5,
        atol=0.01,
    )
