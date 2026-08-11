"""
Epic 15 Story 13 -- cross-registry ADR-0002 equivalence matrix for recommend.fit ->
recommend.recommend, keyed on the inspectable recommendation DataFrame (not one bespoke test
per algorithm -- every algorithm already has its own hand-verified correctness test elsewhere;
see the per-story catalog test files). Mirrors tests/test_ml_equivalence_matrix.py (Epic 8
Story 9) exactly in structure: one parametrized sweep per algorithm computed dynamically from
the live registry, so the matrix grows automatically as new algorithms are curated.
"""

from __future__ import annotations

import pandas as pd
import pytest

from emergentflow.nodes.examples.recommend_fit import RecommendFit
from emergentflow.nodes.examples.recommend_fit_sequence import RecommendFitSequence
from emergentflow.nodes.examples.recommend_recommend import Recommend
from emergentflow.recommend import build_sequences
from emergentflow.recommend.interactions import InteractionMatrix
from emergentflow.recommend.registry import get_recommender_spec, known_recommender_keys


def _run_codegen(definition, node, scope):
    """exec a node's preview fragment in *scope* and return the updated scope."""
    frag = definition.preview(node)
    exec(frag.render(), scope)  # noqa: S102 -- test-only, on our own emitted code
    return scope


def _make_sequence_dataset() -> object:
    """Small session dataset for sequential recommender equivalence tests."""
    df = pd.DataFrame(
        {
            "user_id": ["u1", "u1", "u1", "u2", "u2", "u2", "u3", "u3", "u3"],
            "item_id": ["i1", "i2", "i3", "i2", "i3", "i4", "i1", "i3", "i4"],
            "session_id": ["s1", "s1", "s1", "s2", "s2", "s2", "s3", "s3", "s3"],
        }
    )
    return build_sequences(
        df, user_col="user_id", item_col="item_id", session_col="session_id"
    )


def _make_interactions() -> InteractionMatrix:
    """5 users x 5 items, dense enough for KNN/SVD/NMF/ALS/BPR/NCF/two-tower with tiny k /
    n_components / factors / embedding dims (see _PARAMS overrides below)."""
    df = pd.DataFrame(
        {
            "user_id": [
                "u1",
                "u1",
                "u1",
                "u2",
                "u2",
                "u2",
                "u3",
                "u3",
                "u3",
                "u4",
                "u4",
                "u4",
                "u5",
                "u5",
                "u5",
            ],
            "item_id": [
                "i1",
                "i2",
                "i3",
                "i1",
                "i2",
                "i4",
                "i2",
                "i3",
                "i5",
                "i1",
                "i4",
                "i5",
                "i3",
                "i4",
                "i5",
            ],
            "value": [5, 3, 4, 4, 5, 2, 3, 4, 5, 2, 4, 3, 5, 2, 4],
        }
    )
    return InteractionMatrix.from_dataframe(
        df, user_col="user_id", item_col="item_id", value_col="value", implicit=False
    )


def _make_item_features() -> pd.DataFrame:
    """item_id + a text column (tfidf_similarity), numeric feature columns (feature_knn), and a
    pre-computed embedding column (embedding_similarity) -- covers every content-based key."""
    return pd.DataFrame(
        {
            "item_id": ["i1", "i2", "i3", "i4", "i5"],
            "description": [
                "action movie with car chases",
                "romantic comedy drama",
                "action packed thriller",
                "documentary about nature",
                "romantic drama with music",
            ],
            "feat1": [1.0, 2.0, 1.5, 3.0, 2.5],
            "feat2": [0.5, 1.5, 0.7, 2.0, 1.8],
            "embedding": [
                [0.1, 0.2, 0.3],
                [0.4, 0.1, 0.2],
                [0.15, 0.25, 0.28],
                [0.9, 0.8, 0.7],
                [0.42, 0.12, 0.22],
            ],
        }
    )


#: Per-key fit-param overrides -- only what's needed for a required_params key or to keep an
#: algorithm's default hyperparameters (k, n_components, factors, embedding dims, epochs) sane
#: for this tiny 5-user/5-item fixture. Mirrors tests/test_ml_equivalence_matrix.py's own
#: _FIT_TRANSFORM_OVERRIDES / _CLUSTER_DETECT_OVERRIDES pattern. A key with no entry here fits
#: with an empty params dict (`{}`).
_PARAMS: dict[str, dict] = {
    "random": {"seed": 0},
    "popularity_segmented": {"segment_col": "seg"},
    "tfidf_similarity": {"item_id_col": "item_id", "text_col": "description"},
    "feature_knn": {
        "item_id_col": "item_id",
        "feature_cols": ["feat1", "feat2"],
        "algorithm": "brute",
    },
    "embedding_similarity": {
        "item_id_col": "item_id",
        "embedding_col": "embedding",
        "metric": "cosine",
    },
    "user_knn_cf": {"k": 2},
    "item_knn_cf": {"k": 2},
    "svd_cf": {"n_components": 2, "seed": 0},
    "nmf_cf": {"n_components": 2, "seed": 0},
    "als": {"factors": 2, "iterations": 3, "seed": 0},
    "bpr": {"factors": 2, "iterations": 3, "seed": 0},
    "ncf": {
        "embedding_dim": 4,
        "mlp_layers": [4],
        "epochs": 1,
        "batch_size": 4,
        "seed": 0,
    },
    "two_tower": {
        "user_embedding_dim": 4,
        "item_embedding_dim": 4,
        "user_tower_layers": [4],
        "item_tower_layers": [4],
        "epochs": 1,
        "batch_size": 4,
        "seed": 0,
    },
    "gru4rec": {
        "embedding_dim": 4,
        "hidden_dim": 8,
        "epochs": 1,
        "batch_size": 4,
        "seed": 0,
    },
}

#: Content-based keys need the item_features DataFrame; every other key fits on the
#: InteractionMatrix alone.
_NEEDS_ITEM_FEATURES = {"tfidf_similarity", "feature_knn", "embedding_similarity"}

_N_RECOMMENDATIONS = 3


def _run_equivalence_for(algorithm: str) -> None:
    """Fit *algorithm* + generate recommendations via both execute() and codegen, and assert the
    resulting recommendation DataFrames are equivalent (float-tolerant, since some
    algorithms -- SVD/NMF/ALS/BPR/NCF/two_tower -- may carry tiny floating-point noise between
    two independent forward passes over identical weights)."""
    im = _make_interactions()
    item_features = _make_item_features() if algorithm in _NEEDS_ITEM_FEATURES else None
    params = _PARAMS.get(algorithm, {})

    fit_def = RecommendFit()
    fit_node = fit_def.instantiate(algorithm=algorithm, params=params)
    rec_def = Recommend()
    rec_node = rec_def.instantiate(n=_N_RECOMMENDATIONS)

    fit_inputs: dict = {"interactions": im}
    if item_features is not None:
        fit_inputs["item_features"] = item_features
    fit_result = fit_def.execute(fit_node, fit_inputs)
    exec_result = rec_def.execute(rec_node, {"recommender": fit_result["recommender"]})

    scope: dict = {"interactions": im, "item_features": item_features}
    _run_codegen(fit_def, fit_node, scope)
    _run_codegen(rec_def, rec_node, scope)
    codegen_result = scope["result"]

    pd.testing.assert_frame_equal(
        exec_result["result"].recommendations.reset_index(drop=True),
        codegen_result.recommendations.reset_index(drop=True),
        check_exact=False,
        rtol=1e-6,
        atol=1e-9,
    )


def _keys_requiring_extra(extra: str) -> list[str]:
    return sorted(
        k for k in known_recommender_keys() if get_recommender_spec(k).requires_extra == extra
    )


_BASE_KEYS = sorted(
    k for k in known_recommender_keys() if get_recommender_spec(k).requires_extra is None
)
_RECOMMEND_EXTRA_KEYS = _keys_requiring_extra("emergentflow[recommend]")
_TORCH_KEYS = sorted(
    k
    for k in _keys_requiring_extra("torch")
    if get_recommender_spec(k).fitter is not None
)
_TORCH_SEQUENCE_KEYS = sorted(
    k for k in _keys_requiring_extra("torch") if get_recommender_spec(k).sequence_fitter is not None
)


@pytest.mark.equivalence
@pytest.mark.parametrize("algorithm", _BASE_KEYS)
def test_recommend_fit_recommend_equivalence(algorithm: str) -> None:
    """ADR-0002: execute() and codegen produce equivalent recommendations for every base-install
    (no optional extra) registered algorithm."""
    _run_equivalence_for(algorithm)


@pytest.mark.equivalence
@pytest.mark.parametrize("algorithm", _RECOMMEND_EXTRA_KEYS)
def test_recommend_fit_recommend_equivalence_implicit_extra(algorithm: str) -> None:
    """ADR-0002, [recommend]-extra keys (implicit-backed ALS/BPR)."""
    pytest.importorskip("implicit")
    _run_equivalence_for(algorithm)


@pytest.mark.equivalence
@pytest.mark.parametrize("algorithm", _TORCH_KEYS)
def test_recommend_fit_recommend_equivalence_torch(algorithm: str) -> None:
    """ADR-0002, torch-backed deep keys (NCF, two-tower)."""
    pytest.importorskip("torch")
    _run_equivalence_for(algorithm)


@pytest.mark.equivalence
@pytest.mark.parametrize("algorithm", _TORCH_SEQUENCE_KEYS)
def test_recommend_fit_sequence_recommend_equivalence_torch(algorithm: str) -> None:
    """ADR-0002, torch-backed sequence keys (GRU4Rec)."""
    pytest.importorskip("torch")
    sequences = _make_sequence_dataset()
    params = _PARAMS.get(algorithm, {})

    fit_def = RecommendFitSequence()
    fit_node = fit_def.instantiate(algorithm=algorithm, params=params)
    rec_def = Recommend()
    rec_node = rec_def.instantiate(n=_N_RECOMMENDATIONS)

    fit_result = fit_def.execute(fit_node, {"sequences": sequences})
    exec_result = rec_def.execute(rec_node, {"recommender": fit_result["recommender"]})

    scope: dict = {"sequences": sequences}
    _run_codegen(fit_def, fit_node, scope)
    _run_codegen(rec_def, rec_node, scope)
    codegen_result = scope["result"]

    pd.testing.assert_frame_equal(
        exec_result["result"].recommendations.reset_index(drop=True),
        codegen_result.recommendations.reset_index(drop=True),
        check_exact=False,
        rtol=1e-6,
        atol=1e-9,
    )
