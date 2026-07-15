"""Node tests for ``recommend.fit``/``recommend.recommend``/``recommend.similar_items``
(Epic 15, Story Group B).

Covers ADR-0002 codegen/execute equivalence, the optional ``item_features`` port, and the
``RecommendationResult`` type-token registration.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from emergentflow.nodes.examples.recommend_compare import RecommendCompare
from emergentflow.nodes.examples.recommend_evaluate import RecommendEvaluate
from emergentflow.nodes.examples.recommend_fit import RecommendFit
from emergentflow.nodes.examples.recommend_recommend import Recommend
from emergentflow.nodes.examples.recommend_similar_items import SimilarItems
from emergentflow.recommend import registry as _reg
from emergentflow.recommend.interactions import InteractionMatrix
from emergentflow.recommend.models import EvalResult, FittedRecommender, RecommendationResult
from emergentflow.recommend.registry import RecommenderSpec, register_recommender
from emergentflow.types.registry import registry as type_registry

# ---------------------------------------------------------------------------
# Fixtures -- copied from tests/test_recommend_seam.py
# ---------------------------------------------------------------------------


def _make_interaction_matrix() -> InteractionMatrix:
    """Deterministic 3-user x 3-item interaction matrix for tests."""
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
            "item_features_provided": item_features is not None,
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


def _similar_fn(recommender: FittedRecommender, item_ids: list, n: int) -> RecommendationResult:
    rows = []
    for iid in item_ids:
        for rank in range(1, n + 1):
            rows.append({"user_id": None, "item_id": iid, "rank": rank, "score": 1.0 / rank})
    return RecommendationResult(recommendations=pd.DataFrame(rows))


def _similar_fitter(interactions, item_features, params):
    return FittedRecommender(
        algorithm="_TestSimilar",
        algorithm_family="baseline",
        n_users=interactions.n_users,
        n_items=interactions.n_items,
        fit_stats={"n_interactions": interactions.n_interactions},
        model={"matrix": interactions.matrix, "item_ids": interactions.item_ids},
    )


_TestSimilarSpec = RecommenderSpec(
    key="_TestSimilar",
    family="baseline",
    fitter=_similar_fitter,
    recommend_fn=_pop_recommend_fn,
    similar_items_fn=_similar_fn,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_codegen(definition, node, scope):
    """exec a node's preview fragment in *scope* and return the updated scope."""
    frag = definition.preview(node)
    exec(frag.render(), scope)
    return scope


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_recommend_fit_node_codegen_and_execute_are_equivalent():
    register_recommender(_TestPopSpec)
    try:
        im = _make_interaction_matrix()
        definition = RecommendFit()
        node = definition.instantiate(algorithm="_TestPop", params={})

        exec_result = definition.execute(node, {"interactions": im})
        assert isinstance(exec_result["recommender"], FittedRecommender)

        scope = {"interactions": im, "item_features": None}
        _run_codegen(definition, node, scope)
        codegen_result = scope["recommender"]
        assert isinstance(codegen_result, FittedRecommender)

        assert exec_result["recommender"].algorithm == codegen_result.algorithm
        assert exec_result["recommender"].n_users == codegen_result.n_users
        assert exec_result["recommender"].n_items == codegen_result.n_items
        assert exec_result["recommender"].fit_stats == codegen_result.fit_stats
    finally:
        _reg._REGISTRY.pop("_TestPop", None)


def test_recommend_fit_node_with_item_features_port():
    register_recommender(_TestPopSpec)
    try:
        im = _make_interaction_matrix()
        item_features = pd.DataFrame({"item_id": ["item_a"], "feature": [1.0]})
        definition = RecommendFit()
        node = definition.instantiate(algorithm="_TestPop", params={})

        exec_result = definition.execute(node, {"interactions": im, "item_features": item_features})
        assert exec_result["recommender"].fit_stats["item_features_provided"] is True

        scope = {"interactions": im, "item_features": item_features}
        _run_codegen(definition, node, scope)
        codegen_result = scope["recommender"]
        assert codegen_result.fit_stats["item_features_provided"] is True
    finally:
        _reg._REGISTRY.pop("_TestPop", None)


def test_recommend_node_codegen_and_execute_are_equivalent():
    register_recommender(_TestPopSpec)
    try:
        im = _make_interaction_matrix()
        fit_def = RecommendFit()
        fit_node = fit_def.instantiate(algorithm="_TestPop", params={})
        rec_def = Recommend()
        rec_node = rec_def.instantiate()

        fit_result = fit_def.execute(fit_node, {"interactions": im})
        exec_result = rec_def.execute(rec_node, {"recommender": fit_result["recommender"]})
        assert isinstance(exec_result["result"], RecommendationResult)

        scope = {"interactions": im, "item_features": None}
        _run_codegen(fit_def, fit_node, scope)
        _run_codegen(rec_def, rec_node, scope)
        codegen_result = scope["result"]
        assert isinstance(codegen_result, RecommendationResult)

        pd.testing.assert_frame_equal(
            exec_result["result"].recommendations,
            codegen_result.recommendations,
        )
    finally:
        _reg._REGISTRY.pop("_TestPop", None)


def test_similar_items_node_codegen_and_execute_are_equivalent():
    register_recommender(_TestSimilarSpec)
    try:
        im = _make_interaction_matrix()
        fit_def = RecommendFit()
        fit_node = fit_def.instantiate(algorithm="_TestSimilar", params={})
        sim_def = SimilarItems()
        sim_node = sim_def.instantiate(item_ids=["item_a"], n=2)

        fit_result = fit_def.execute(fit_node, {"interactions": im})
        exec_result = sim_def.execute(
            sim_node,
            {"recommender": fit_result["recommender"]},
        )
        assert isinstance(exec_result["result"], RecommendationResult)

        scope = {"interactions": im, "item_features": None}
        _run_codegen(fit_def, fit_node, scope)
        _run_codegen(sim_def, sim_node, scope)
        codegen_result = scope["result"]
        assert isinstance(codegen_result, RecommendationResult)

        pd.testing.assert_frame_equal(
            exec_result["result"].recommendations,
            codegen_result.recommendations,
        )
    finally:
        _reg._REGISTRY.pop("_TestSimilar", None)


def test_recommendation_result_type_token_is_registered():
    assert type_registry.is_registered("RecommendationResult")


def test_evalresult_type_token_is_registered():
    assert type_registry.is_registered("EvalResult")


def test_recommend_evaluate_node_codegen_and_execute_are_equivalent():
    register_recommender(_TestPopSpec)
    try:
        im = _make_interaction_matrix()
        test_df = pd.DataFrame(
            {
                "user_id": ["alice", "bob", "carol"],
                "item_id": ["item_c", "item_b", "item_a"],
            }
        )
        test_im = InteractionMatrix.from_dataframe(test_df, user_col="user_id", item_col="item_id")

        fit_def = RecommendFit()
        fit_node = fit_def.instantiate(algorithm="_TestPop", params={})
        fit_result = fit_def.execute(fit_node, {"interactions": im})

        eval_def = RecommendEvaluate()
        eval_node = eval_def.instantiate(k=10)

        exec_result = eval_def.execute(
            eval_node,
            {"recommender": fit_result["recommender"], "test_interactions": test_im},
        )
        assert isinstance(exec_result["result"], EvalResult)

        scope = {"interactions": im, "item_features": None}
        _run_codegen(fit_def, fit_node, scope)
        scope_eval = {"recommender": scope["recommender"], "test_interactions": test_im}
        _run_codegen(eval_def, eval_node, scope_eval)
        codegen_result = scope_eval["result"]
        assert isinstance(codegen_result, EvalResult)

        assert exec_result["result"].k == codegen_result.k
        assert exec_result["result"].algorithm == codegen_result.algorithm
        assert exec_result["result"].aggregate == codegen_result.aggregate
        pd.testing.assert_frame_equal(exec_result["result"].per_user, codegen_result.per_user)
    finally:
        _reg._REGISTRY.pop("_TestPop", None)


def test_recommend_compare_node_codegen_and_execute_are_equivalent():
    register_recommender(_TestPopSpec)
    register_recommender(_TestSimilarSpec)
    try:
        im = _make_interaction_matrix()

        fit_def = RecommendFit()
        fit_pop_node = fit_def.instantiate(algorithm="_TestPop", params={})
        fit_sim_node = fit_def.instantiate(algorithm="_TestSimilar", params={})

        rec_a = fit_def.execute(fit_pop_node, {"interactions": im})["recommender"]
        rec_b = fit_def.execute(fit_sim_node, {"interactions": im})["recommender"]

        compare_def = RecommendCompare()
        compare_node = compare_def.instantiate(k=10)

        exec_result = compare_def.execute(
            compare_node,
            {"recommenders": [rec_a, rec_b], "test_interactions": im},
        )

        scope = {"recommenders": [rec_a, rec_b], "test_interactions": im}
        _run_codegen(compare_def, compare_node, scope)
        codegen_result = scope["result"]

        pd.testing.assert_frame_equal(exec_result["result"], codegen_result)
    finally:
        _reg._REGISTRY.pop("_TestPop", None)
        _reg._REGISTRY.pop("_TestSimilar", None)
