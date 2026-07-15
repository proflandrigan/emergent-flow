"""
Tests for the ncf (Neural Collaborative Filtering) deep recommender
(Epic 15, Story 10).

Part A: base-install typed-error test (no torch required).
Part B: importorskip("torch")-gated tests (fit, recommend, exclude_known,
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
# Part A: base-install typed-error test (no torch required)
# ---------------------------------------------------------------------------


def test_ncf_missing_extra_raises_typed_error_when_torch_absent():
    """If torch is not installed, ef.recommend.fit raises MissingOptionalDependencyError.
    This test only runs its assertion meaningfully when torch is ABSENT; if it happens to be
    installed in this environment, skip (the missing-extra path can't be exercised)."""
    if importlib.util.find_spec("torch") is not None:
        pytest.skip("torch is installed in this environment; cannot test the absent-extra path")

    import emergentflow as ef

    df = pd.DataFrame({"user_id": [1, 1, 2], "item_id": ["A", "B", "A"]})
    im = InteractionMatrix.from_dataframe(df, user_col="user_id", item_col="item_id")

    with pytest.raises(MissingOptionalDependencyError):
        ef.recommend.fit(im, algorithm="ncf", params={})


# ---------------------------------------------------------------------------
# Part B: importorskip-gated tests (require torch)
# ---------------------------------------------------------------------------


def _make_ncf_fixture() -> InteractionMatrix:
    """5 users x 4 items — enough signal for NCF with embedding_dim=4."""
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


_NCF_PARAMS = {"embedding_dim": 4, "epochs": 5, "seed": 0}


def test_ncf_fit_returns_fitted_recommender():
    pytest.importorskip("torch")
    im = _make_ncf_fixture()
    spec = _reg.get_recommender_spec("ncf")
    result = spec.fitter(im, None, _NCF_PARAMS)
    assert isinstance(result, FittedRecommender)
    assert result.algorithm == "ncf"
    assert result.algorithm_family == "deep"


def test_ncf_recommend_returns_valid_result():
    pytest.importorskip("torch")
    im = _make_ncf_fixture()
    spec = _reg.get_recommender_spec("ncf")
    fitted = spec.fitter(im, None, _NCF_PARAMS)
    result = spec.recommend_fn(fitted, [1], 3, exclude_known=False)
    assert isinstance(result, RecommendationResult)
    assert len(result.recommendations) > 0
    cols = list(result.recommendations.columns)
    for c in ["user_id", "item_id", "rank", "score"]:
        assert c in cols
    ranks = result.recommendations["rank"].tolist()
    assert ranks == list(range(1, len(ranks) + 1))


def test_ncf_exclude_known():
    pytest.importorskip("torch")
    im = _make_ncf_fixture()
    spec = _reg.get_recommender_spec("ncf")
    fitted = spec.fitter(im, None, _NCF_PARAMS)
    result = spec.recommend_fn(fitted, [1], 10, exclude_known=True)
    returned_ids = result.recommendations["item_id"].tolist()
    assert "A" not in returned_ids
    assert "B" not in returned_ids
    assert "C" not in returned_ids


def test_ncf_determinism():
    pytest.importorskip("torch")
    im = _make_ncf_fixture()
    spec = _reg.get_recommender_spec("ncf")

    f1 = spec.fitter(im, None, _NCF_PARAMS)
    r1 = spec.recommend_fn(f1, [1, 2, 3], 3, exclude_known=True)
    f2 = spec.fitter(im, None, _NCF_PARAMS)
    r2 = spec.recommend_fn(f2, [1, 2, 3], 3, exclude_known=True)

    pd.testing.assert_frame_equal(r1.recommendations, r2.recommendations)


def test_ncf_codegen_is_parseable():
    pytest.importorskip("torch")
    fit_def = RecommendFit()
    fit_node = fit_def.instantiate(algorithm="ncf", params=_NCF_PARAMS)
    frag = fit_def.preview(fit_node)
    code = frag.render()
    ast.parse(code)


def test_ncf_equivalence_execute_vs_codegen():
    pytest.importorskip("torch")
    im = _make_ncf_fixture()
    fit_def = RecommendFit()
    fit_node = fit_def.instantiate(algorithm="ncf", params=_NCF_PARAMS)

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
