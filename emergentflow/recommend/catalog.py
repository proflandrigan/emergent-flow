"""
emergentflow.recommend.catalog
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Seed recommender catalog for baseline algorithms (Epic 15, Story 4).

Importing this module registers a small, curated set of baseline-family recommendation
algorithm entries into ``emergentflow.recommend.registry`` as an import-time side effect,
mirroring ``emergentflow.stats.catalog`` and ``emergentflow.ml.catalog``.

This is a SEED set of four baseline algorithms (random, popularity, popularity_segmented,
co_occurrence) and three content-based algorithms (tfidf_similarity, feature_knn,
embedding_similarity) so the ``ef.recommend.fit``/``recommend``/``similar_items`` seam and
its tests have representative algorithms to exercise. Collaborative-filtering and deep
recommenders are widened across Epic 15 Stories 6-13 as reviewed allow-list changes, not
enumerated here.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.decomposition import NMF, TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.neighbors import NearestNeighbors

from emergentflow.recommend.errors import InvalidRecommenderParamsError
from emergentflow.recommend.interactions import InteractionMatrix
from emergentflow.recommend.models import (
    FittedRecommender,
    RecommendationResult,
    SequenceDataset,
)
from emergentflow.recommend.registry import (
    RecommenderParamSpec,
    RecommenderSpec,
    register_recommender,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _compute_popularity_scores(matrix, score_type: str) -> np.ndarray:
    """Compute per-item popularity scores from a sparse interaction matrix.

    Parameters
    ----------
    matrix: sparse matrix of shape ``(n_users, n_items)``.
    score_type: ``"count"`` — sum of interaction values per column;
        ``"mean_rating"`` — sum of values / count of nonzero entries per column;
        ``"weighted"`` — count * mean_rating (popularity + quality blend).

    Returns
    -------
    1-D numpy array of length ``n_items``.
    """
    col_sum = np.asarray(matrix.sum(axis=0)).ravel()
    col_nnz = matrix.getnnz(axis=0)
    if score_type == "count":
        return col_sum
    if score_type == "mean_rating":
        return np.divide(
            col_sum,
            col_nnz,
            out=np.zeros_like(col_sum, dtype=float),
            where=col_nnz > 0,
        )
    if score_type == "weighted":
        mean_rating = np.divide(
            col_sum,
            col_nnz,
            out=np.zeros_like(col_sum, dtype=float),
            where=col_nnz > 0,
        )
        return col_sum * mean_rating
    raise ValueError(f"unknown score_type: {score_type!r}")


def _align_item_features(
    item_features: pd.DataFrame,
    item_id_col: str,
    interactions: InteractionMatrix,
) -> pd.DataFrame:
    """Reindex *item_features* to ``interactions.item_ids`` order (the content-based
    archetype's shared alignment step).

    Items in ``interactions.item_ids`` missing a row in *item_features* get an all-NaN row
    (the caller degrades this to a zero feature vector); rows in *item_features* for items
    not in ``interactions.item_index`` are dropped. Raises
    :class:`InvalidRecommenderParamsError` — rather than letting a raw pandas
    ``ValueError`` ("cannot reindex on an axis with duplicate labels") escape — if
    *item_id_col* has duplicate values, since reindexing would otherwise be ambiguous.
    """
    duplicated = item_features[item_id_col].duplicated()
    if duplicated.any():
        dupes = sorted(item_features.loc[duplicated, item_id_col].unique().tolist())
        raise InvalidRecommenderParamsError(
            f"item_features has duplicate {item_id_col!r} value(s): {dupes!r}; "
            "each item must appear at most once."
        )
    return item_features.set_index(item_id_col).reindex(interactions.item_ids)


def _co_occurrence_metric(
    co_count: float,
    count_i: float,
    count_j: float,
    n_users: int,
    metric: str,
    min_support: float,
) -> float:
    """Compute a single pair's metric score: support, confidence, or lift.

    Returns ``0.0`` when any required count is zero or support is below
    ``min_support``.
    """
    if co_count == 0:
        return 0.0
    support = co_count / n_users
    if support < min_support:
        return 0.0
    if metric == "support":
        return float(support)
    if count_i == 0:
        return 0.0
    confidence = co_count / count_i
    if metric == "confidence":
        return float(confidence)
    if count_j == 0:
        return 0.0
    expected = count_j / n_users
    if expected == 0:
        return 0.0
    return float(confidence / expected)


# ===================================================================
# random (baseline)
# ===================================================================


def _fit_random(
    interactions: InteractionMatrix,
    item_features: pd.DataFrame | None,
    params: dict[str, Any],
) -> FittedRecommender:
    seed = int(params.get("seed", 0))
    return FittedRecommender(
        algorithm="random",
        algorithm_family="baseline",
        n_users=interactions.n_users,
        n_items=interactions.n_items,
        fit_stats={
            "n_interactions": interactions.n_interactions,
            "sparsity": 1.0 - interactions.density,
        },
        model={
            "item_ids": interactions.item_ids,
            "seed": seed,
            "matrix": interactions.matrix,
            "user_index": interactions.user_index,
            "item_index": interactions.item_index,
        },
    )


def _recommend_random(
    recommender: FittedRecommender,
    user_ids: list[Any] | None,
    n: int,
    exclude_known: bool,
) -> RecommendationResult:
    model = recommender.model
    item_ids = model["item_ids"]
    seed = model["seed"]
    matrix = model["matrix"]
    user_index = model["user_index"]

    if user_ids is None:
        user_ids = list(user_index.keys())

    rows: list[dict[str, Any]] = []
    rng = np.random.default_rng(seed)
    for uid in user_ids:
        n_items = len(item_ids)
        candidates = list(range(n_items))
        if exclude_known and uid in user_index:
            uid_idx = user_index[uid]
            known_cols = set(matrix[uid_idx].indices.tolist())
            candidates = [c for c in candidates if c not in known_cols]

        drawn = rng.choice(candidates, size=min(n, len(candidates)), replace=False)
        for rank, idx in enumerate(drawn, start=1):
            rows.append(
                {
                    "user_id": uid,
                    "item_id": item_ids[idx],
                    "rank": rank,
                    "score": 1.0,
                }
            )

    return RecommendationResult(recommendations=pd.DataFrame(rows))


register_recommender(
    RecommenderSpec(
        key="random",
        family="baseline",
        fitter=_fit_random,
        recommend_fn=_recommend_random,
        similar_items_fn=None,
        required_params=(),
        optional_params=("n", "seed"),
        param_metadata=(
            RecommenderParamSpec(
                name="n", type="int", default=None, help="Number of recommendations per user."
            ),
            RecommenderParamSpec(
                name="seed",
                type="int",
                default=0,
                help="Random seed for reproducible random draws.",
            ),
        ),
        handles_cold_start_users=True,
        handles_cold_start_items=True,
        description="Random recommendation baseline — draws N random items per user, "
        "deterministic given seed.",
    )
)


# ===================================================================
# popularity (baseline, global)
# ===================================================================


def _fit_popularity(
    interactions: InteractionMatrix,
    item_features: pd.DataFrame | None,
    params: dict[str, Any],
) -> FittedRecommender:
    score_type = str(params.get("score_type", "count"))
    scores = _compute_popularity_scores(interactions.matrix, score_type)
    n_items_scored = int((scores > 0).sum())

    return FittedRecommender(
        algorithm="popularity",
        algorithm_family="baseline",
        n_users=interactions.n_users,
        n_items=interactions.n_items,
        fit_stats={
            "n_interactions": interactions.n_interactions,
            "sparsity": 1.0 - interactions.density,
            "n_items_scored": n_items_scored,
        },
        model={
            "item_ids": interactions.item_ids,
            "scores": scores,
            "score_type": score_type,
            "matrix": interactions.matrix,
            "user_index": interactions.user_index,
            "item_index": interactions.item_index,
        },
    )


def _recommend_popularity(
    recommender: FittedRecommender,
    user_ids: list[Any] | None,
    n: int,
    exclude_known: bool,
) -> RecommendationResult:
    model = recommender.model
    item_ids = model["item_ids"]
    scores = model["scores"]
    matrix = model["matrix"]
    user_index = model["user_index"]

    if user_ids is None:
        user_ids = list(user_index.keys())

    sorted_indices = np.argsort(-scores).tolist()

    rows: list[dict[str, Any]] = []
    for uid in user_ids:
        candidates = sorted_indices
        if exclude_known and uid in user_index:
            uid_idx = user_index[uid]
            known_cols = set(matrix[uid_idx].indices.tolist())
            candidates = [idx for idx in sorted_indices if idx not in known_cols]

        for rank, idx in enumerate(candidates[:n], start=1):
            rows.append(
                {
                    "user_id": uid,
                    "item_id": item_ids[idx],
                    "rank": rank,
                    "score": float(scores[idx]),
                }
            )

    return RecommendationResult(recommendations=pd.DataFrame(rows))


register_recommender(
    RecommenderSpec(
        key="popularity",
        family="baseline",
        fitter=_fit_popularity,
        recommend_fn=_recommend_popularity,
        similar_items_fn=None,
        required_params=(),
        optional_params=("n", "score_type"),
        param_metadata=(
            RecommenderParamSpec(
                name="n", type="int", default=None, help="Number of recommendations per user."
            ),
            RecommenderParamSpec(
                name="score_type",
                type="str",
                default="count",
                help="How to score item popularity from the interaction matrix.",
                choices=("count", "mean_rating", "weighted"),
            ),
        ),
        handles_cold_start_users=True,
        handles_cold_start_items=False,
        description="Global popularity baseline — same top-N ranking for every user "
        "(score_type: count / mean_rating / weighted).",
    )
)


# ===================================================================
# popularity_segmented (baseline)
# ===================================================================

# params["user_segments"] ({user_id: segment_value}) is how the caller supplies
# per-user segments because InteractionMatrix has no user-features frame yet.
# segment_col is a descriptive label only. When user_segments is absent or empty,
# every user is treated as a single segment (global popularity behavior). When a
# user is missing from user_segments, the fitter falls back to the global ranking.


def _fit_popularity_segmented(
    interactions: InteractionMatrix,
    item_features: pd.DataFrame | None,
    params: dict[str, Any],
) -> FittedRecommender:
    segment_col = str(params["segment_col"])
    user_segments: dict[Any, Any] = params.get("user_segments") or {}
    score_type = str(params.get("score_type", "count"))
    matrix = interactions.matrix
    user_index = interactions.user_index

    if not user_segments:
        user_segments = {uid: None for uid in interactions.user_ids}

    segment_users: dict[Any, list[int]] = {}
    for uid, seg in user_segments.items():
        if uid in user_index:
            segment_users.setdefault(seg, []).append(user_index[uid])

    global_scores = _compute_popularity_scores(matrix, score_type)

    segment_scores: dict[Any, np.ndarray] = {}
    for seg, user_idxs in segment_users.items():
        if not user_idxs:
            segment_scores[seg] = global_scores
        else:
            sub = matrix[user_idxs, :]
            segment_scores[seg] = _compute_popularity_scores(sub, score_type)

    return FittedRecommender(
        algorithm="popularity_segmented",
        algorithm_family="baseline",
        n_users=interactions.n_users,
        n_items=interactions.n_items,
        fit_stats={
            "n_interactions": interactions.n_interactions,
            "sparsity": 1.0 - interactions.density,
            "n_items_scored": int((global_scores > 0).sum()),
            "n_segments": len(segment_scores),
        },
        model={
            "item_ids": interactions.item_ids,
            "segment_scores": segment_scores,
            "segment_col": segment_col,
            "user_to_segment": user_segments,
            "global_scores": global_scores,
            "score_type": score_type,
            "matrix": interactions.matrix,
            "user_index": interactions.user_index,
            "item_index": interactions.item_index,
        },
    )


def _recommend_popularity_segmented(
    recommender: FittedRecommender,
    user_ids: list[Any] | None,
    n: int,
    exclude_known: bool,
) -> RecommendationResult:
    model = recommender.model
    item_ids = model["item_ids"]
    user_to_segment = model["user_to_segment"]
    segment_scores = model["segment_scores"]
    global_scores = model["global_scores"]
    matrix = model["matrix"]
    user_index = model["user_index"]

    if user_ids is None:
        user_ids = list(user_index.keys())

    rows: list[dict[str, Any]] = []
    for uid in user_ids:
        # `.get(uid)` alone can't tell "uid absent from user_to_segment" apart from "uid
        # present with an explicit segment of None" -- both default to None. Check
        # membership explicitly so a genuinely-absent user always falls back to
        # global_scores, even if some other user was explicitly assigned segment None.
        if uid in user_to_segment:
            scores = segment_scores.get(user_to_segment[uid], global_scores)
        else:
            scores = global_scores
        sorted_indices = np.argsort(-scores).tolist()

        candidates = sorted_indices
        if exclude_known and uid in user_index:
            uid_idx = user_index[uid]
            known_cols = set(matrix[uid_idx].indices.tolist())
            candidates = [idx for idx in sorted_indices if idx not in known_cols]

        for rank, idx in enumerate(candidates[:n], start=1):
            rows.append(
                {
                    "user_id": uid,
                    "item_id": item_ids[idx],
                    "rank": rank,
                    "score": float(scores[idx]),
                }
            )

    return RecommendationResult(recommendations=pd.DataFrame(rows))


register_recommender(
    RecommenderSpec(
        key="popularity_segmented",
        family="baseline",
        fitter=_fit_popularity_segmented,
        recommend_fn=_recommend_popularity_segmented,
        similar_items_fn=None,
        required_params=("segment_col",),
        optional_params=("n", "score_type", "user_segments"),
        param_metadata=(
            RecommenderParamSpec(
                name="segment_col",
                type="str",
                default=None,
                help="Descriptive label for the segmentation column being used.",
                required=True,
            ),
            RecommenderParamSpec(
                name="n", type="int", default=None, help="Number of recommendations per user."
            ),
            RecommenderParamSpec(
                name="score_type",
                type="str",
                default="count",
                help="How to score item popularity within each segment.",
                choices=("count", "mean_rating", "weighted"),
            ),
            RecommenderParamSpec(
                name="user_segments",
                type="any",
                default=None,
                help="Mapping of user id to segment value used to group users.",
            ),
        ),
        handles_cold_start_users=True,
        handles_cold_start_items=False,
        description="Per-segment popularity baseline — popularity computed separately "
        "within each user segment (supplied via params[user_segments]).",
    )
)


# ===================================================================
# co_occurrence (baseline, association rules)
# ===================================================================


def _fit_co_occurrence(
    interactions: InteractionMatrix,
    item_features: pd.DataFrame | None,
    params: dict[str, Any],
) -> FittedRecommender:
    metric = str(params.get("metric", "lift"))
    min_support = float(params.get("min_support", 0.0))
    matrix = interactions.matrix
    n_users = interactions.n_users

    binary = (matrix > 0).astype(float)
    co_occurrence = (binary.T @ binary).tocsr()
    item_marginals = np.asarray(binary.sum(axis=0)).ravel()

    diag = co_occurrence.diagonal()
    n_self = int((diag != 0).sum())
    n_pairs = co_occurrence.nnz - n_self

    return FittedRecommender(
        algorithm="co_occurrence",
        algorithm_family="baseline",
        n_users=n_users,
        n_items=interactions.n_items,
        fit_stats={
            "n_interactions": interactions.n_interactions,
            "sparsity": 1.0 - interactions.density,
            "n_item_pairs_with_cooccurrence": n_pairs,
        },
        model={
            "item_ids": interactions.item_ids,
            "item_index": interactions.item_index,
            "co_occurrence": co_occurrence,
            "item_marginals": item_marginals,
            "n_users": n_users,
            "metric": metric,
            "min_support": min_support,
            "matrix": interactions.matrix,
            "user_index": interactions.user_index,
        },
    )


def _recommend_co_occurrence(
    recommender: FittedRecommender,
    user_ids: list[Any] | None,
    n: int,
    exclude_known: bool,
) -> RecommendationResult:
    model = recommender.model
    co_occ = model["co_occurrence"]
    item_marginals = model["item_marginals"]
    n_users = model["n_users"]
    metric = model["metric"]
    min_support = model["min_support"]
    item_ids = model["item_ids"]
    matrix = model["matrix"]
    user_index = model["user_index"]

    if user_ids is None:
        user_ids = list(user_index.keys())

    rows: list[dict[str, Any]] = []
    for uid in user_ids:
        if uid not in user_index:
            continue
        uid_idx = user_index[uid]
        user_row = matrix[uid_idx]
        known_items = user_row.indices.tolist()
        if not known_items:
            continue

        candidate_scores: dict[int, float] = {}
        for i in known_items:
            count_i = item_marginals[i]
            row = co_occ[i]
            for j_idx, co_count in zip(row.indices, row.data, strict=True):
                if j_idx == i:
                    continue
                if exclude_known and j_idx in known_items:
                    continue
                count_j = item_marginals[j_idx]
                score = _co_occurrence_metric(
                    float(co_count),
                    float(count_i),
                    float(count_j),
                    n_users,
                    metric,
                    min_support,
                )
                if score > 0:
                    candidate_scores[j_idx] = candidate_scores.get(j_idx, 0.0) + score

        sorted_candidates = sorted(candidate_scores.items(), key=lambda x: -x[1])
        for rank, (item_idx, score) in enumerate(sorted_candidates[:n], start=1):
            rows.append(
                {
                    "user_id": uid,
                    "item_id": item_ids[item_idx],
                    "rank": rank,
                    "score": float(score),
                }
            )

    return RecommendationResult(recommendations=pd.DataFrame(rows))


def _similar_co_occurrence(
    recommender: FittedRecommender,
    item_ids: list[Any],
    n: int,
) -> RecommendationResult:
    model = recommender.model
    co_occ = model["co_occurrence"]
    item_marginals = model["item_marginals"]
    n_users = model["n_users"]
    metric = model["metric"]
    min_support = model["min_support"]
    all_item_ids = model["item_ids"]
    item_index = model["item_index"]

    rows: list[dict[str, Any]] = []
    for qid in item_ids:
        if qid not in item_index:
            continue
        q_idx = item_index[qid]
        count_q = item_marginals[q_idx]
        q_row = co_occ[q_idx]
        candidates: list[tuple[int, float]] = []
        for j_idx, co_count in zip(q_row.indices, q_row.data, strict=True):
            if j_idx == q_idx:
                continue
            count_j = item_marginals[j_idx]
            score = _co_occurrence_metric(
                float(co_count),
                float(count_q),
                float(count_j),
                n_users,
                metric,
                min_support,
            )
            if score > 0:
                candidates.append((j_idx, score))

        candidates.sort(key=lambda x: -x[1])
        for rank, (j_idx, score) in enumerate(candidates[:n], start=1):
            rows.append(
                {
                    "user_id": None,
                    "item_id": all_item_ids[j_idx],
                    "rank": rank,
                    "score": float(score),
                }
            )

    return RecommendationResult(recommendations=pd.DataFrame(rows))


register_recommender(
    RecommenderSpec(
        key="co_occurrence",
        family="baseline",
        fitter=_fit_co_occurrence,
        recommend_fn=_recommend_co_occurrence,
        similar_items_fn=_similar_co_occurrence,
        required_params=(),
        optional_params=("n", "metric", "min_support"),
        param_metadata=(
            RecommenderParamSpec(
                name="n", type="int", default=None, help="Number of recommendations per user."
            ),
            RecommenderParamSpec(
                name="metric",
                type="str",
                default="lift",
                help="Item-item association metric used to rank co-occurring items.",
                choices=("lift", "confidence", "support"),
            ),
            RecommenderParamSpec(
                name="min_support",
                type="float",
                default=0.0,
                help="Minimum support threshold below which a pair's score is zeroed out.",
            ),
        ),
        handles_cold_start_users=False,
        handles_cold_start_items=False,
        description="Co-occurrence / association-rules baseline — item-item lift, "
        "confidence, or support from the binary interaction matrix.",
    )
)


# ===================================================================
# tfidf_similarity (content-based)
# ===================================================================

# The item universe is always defined by InteractionMatrix, not item_features:
# items present in interactions.item_ids but MISSING a row in item_features
# get a zero feature vector; rows in item_features for items NOT in
# interactions.item_index are ignored (dropped).
#
# item_id_col is required because InteractionMatrix does not specify which
# column of item_features identifies the item — the fitter must be told
# explicitly (mirrors the user_segments workaround for popularity_segmented).


def _fit_tfidf_similarity(
    interactions: InteractionMatrix,
    item_features: pd.DataFrame | None,
    params: dict[str, Any],
) -> FittedRecommender:
    if item_features is None:
        raise InvalidRecommenderParamsError(
            "algorithm 'tfidf_similarity' requires item_features (an item-features DataFrame)."
        )
    item_id_col = str(params["item_id_col"])
    text_col = str(params["text_col"])
    max_features = params.get("max_features")
    ngram_range = tuple(params.get("ngram_range", (1, 1)))

    aligned = _align_item_features(item_features, item_id_col, interactions)
    aligned[text_col] = aligned[text_col].fillna("")

    vectorizer = TfidfVectorizer(max_features=max_features, ngram_range=ngram_range)
    item_feature_matrix = vectorizer.fit_transform(aligned[text_col])

    return FittedRecommender(
        algorithm="tfidf_similarity",
        algorithm_family="content",
        n_users=interactions.n_users,
        n_items=interactions.n_items,
        fit_stats={
            "n_interactions": interactions.n_interactions,
            "sparsity": 1.0 - interactions.density,
            "vocab_size": len(vectorizer.vocabulary_),
        },
        model={
            "item_ids": interactions.item_ids,
            "item_index": interactions.item_index,
            "item_feature_matrix": item_feature_matrix,
            "matrix": interactions.matrix,
            "user_index": interactions.user_index,
        },
    )


def _recommend_tfidf_similarity(
    recommender: FittedRecommender,
    user_ids: list[Any] | None,
    n: int,
    exclude_known: bool,
) -> RecommendationResult:
    model = recommender.model
    item_feature_matrix = model["item_feature_matrix"]
    matrix = model["matrix"]
    user_index = model["user_index"]
    item_ids = model["item_ids"]

    if user_ids is None:
        user_ids = list(user_index.keys())

    rows: list[dict[str, Any]] = []
    for uid in user_ids:
        if uid not in user_index:
            continue
        uid_idx = user_index[uid]
        known_idx = matrix[uid_idx].indices.tolist()
        if not known_idx:
            continue

        profile = np.asarray(item_feature_matrix[known_idx].mean(axis=0)).ravel()

        similarities = cosine_similarity(profile.reshape(1, -1), item_feature_matrix).ravel()

        sorted_indices = np.argsort(-similarities).tolist()
        candidates = sorted_indices
        if exclude_known:
            known_set = set(known_idx)
            candidates = [idx for idx in sorted_indices if idx not in known_set]

        for rank, idx in enumerate(candidates[:n], start=1):
            rows.append(
                {
                    "user_id": uid,
                    "item_id": item_ids[idx],
                    "rank": rank,
                    "score": float(similarities[idx]),
                }
            )

    return RecommendationResult(recommendations=pd.DataFrame(rows))


register_recommender(
    RecommenderSpec(
        key="tfidf_similarity",
        family="content",
        fitter=_fit_tfidf_similarity,
        recommend_fn=_recommend_tfidf_similarity,
        similar_items_fn=None,
        required_params=("item_id_col", "text_col"),
        optional_params=("n", "max_features", "ngram_range"),
        param_metadata=(
            RecommenderParamSpec(
                name="item_id_col",
                type="str",
                default=None,
                help="Column in item_features identifying each item.",
                required=True,
            ),
            RecommenderParamSpec(
                name="text_col",
                type="str",
                default=None,
                help="Column in item_features holding the text to vectorize.",
                required=True,
            ),
            RecommenderParamSpec(
                name="n", type="int", default=None, help="Number of recommendations per user."
            ),
            RecommenderParamSpec(
                name="max_features",
                type="any",
                default=None,
                help="Maximum vocabulary size for the TF-IDF vectorizer (None = unlimited).",
            ),
            RecommenderParamSpec(
                name="ngram_range",
                type="list",
                default=(1, 1),
                help="Lower/upper bound (inclusive) of n-gram sizes to extract.",
            ),
        ),
        handles_cold_start_users=False,
        handles_cold_start_items=True,
        description="Content-based filtering via TF-IDF cosine similarity — "
        "builds a user profile from the centroid of their known items' TF-IDF vectors.",
    )
)


# ===================================================================
# feature_knn (content-based)
# ===================================================================

# The item universe is always defined by InteractionMatrix, not item_features:
# items present in interactions.item_ids but MISSING a row in item_features
# get a zero feature vector; rows in item_features for items NOT in
# interactions.item_index are ignored (dropped).
#
# item_id_col is required because InteractionMatrix does not specify which
# column of item_features identifies the item — the fitter must be told
# explicitly (mirrors the user_segments workaround for popularity_segmented).


def _fit_feature_knn(
    interactions: InteractionMatrix,
    item_features: pd.DataFrame | None,
    params: dict[str, Any],
) -> FittedRecommender:
    if item_features is None:
        raise InvalidRecommenderParamsError(
            "algorithm 'feature_knn' requires item_features (an item-features DataFrame)."
        )
    item_id_col = str(params["item_id_col"])
    feature_cols = list(params["feature_cols"])
    metric = str(params.get("metric", "cosine"))
    algorithm = str(params.get("algorithm", "brute"))

    aligned = _align_item_features(item_features, item_id_col, interactions)
    feature_matrix = aligned[feature_cols].fillna(0.0).to_numpy()

    nn = NearestNeighbors(metric=metric, algorithm=algorithm)
    nn.fit(feature_matrix)

    return FittedRecommender(
        algorithm="feature_knn",
        algorithm_family="content",
        n_users=interactions.n_users,
        n_items=interactions.n_items,
        fit_stats={
            "n_interactions": interactions.n_interactions,
            "sparsity": 1.0 - interactions.density,
            "n_feature_cols": len(feature_cols),
        },
        model={
            "item_ids": interactions.item_ids,
            "item_index": interactions.item_index,
            "nn": nn,
            "feature_matrix": feature_matrix,
            "matrix": interactions.matrix,
            "user_index": interactions.user_index,
        },
    )


def _recommend_feature_knn(
    recommender: FittedRecommender,
    user_ids: list[Any] | None,
    n: int,
    exclude_known: bool,
) -> RecommendationResult:
    model = recommender.model
    nn = model["nn"]
    feature_matrix = model["feature_matrix"]
    matrix = model["matrix"]
    user_index = model["user_index"]
    item_ids = model["item_ids"]
    n_items = len(item_ids)

    if user_ids is None:
        user_ids = list(user_index.keys())

    rows: list[dict[str, Any]] = []
    for uid in user_ids:
        if uid not in user_index:
            continue
        uid_idx = user_index[uid]
        known_idx = matrix[uid_idx].indices.tolist()
        if not known_idx:
            continue

        profile = feature_matrix[known_idx].mean(axis=0)

        # Over-fetch by len(known_idx) so excluding known items still fills n
        over_fetch = min(n + len(known_idx), n_items)
        distances, indices = nn.kneighbors(profile.reshape(1, -1), n_neighbors=over_fetch)
        dists = distances[0]
        idxs = indices[0]

        # Negate distance so higher score = more similar (consistent with
        # every other algorithm's score-higher-is-better convention).
        candidates: list[tuple[int, float]] = []
        for j, idx in enumerate(idxs):
            score = -float(dists[j])
            if exclude_known and idx in known_idx:
                continue
            candidates.append((idx, score))

        candidates.sort(key=lambda x: -x[1])
        for rank, (idx, score) in enumerate(candidates[:n], start=1):
            rows.append(
                {
                    "user_id": uid,
                    "item_id": item_ids[idx],
                    "rank": rank,
                    "score": score,
                }
            )

    return RecommendationResult(recommendations=pd.DataFrame(rows))


register_recommender(
    RecommenderSpec(
        key="feature_knn",
        family="content",
        fitter=_fit_feature_knn,
        recommend_fn=_recommend_feature_knn,
        similar_items_fn=None,
        required_params=("item_id_col", "feature_cols"),
        optional_params=("n", "metric", "algorithm"),
        param_metadata=(
            RecommenderParamSpec(
                name="item_id_col",
                type="str",
                default=None,
                help="Column in item_features identifying each item.",
                required=True,
            ),
            RecommenderParamSpec(
                name="feature_cols",
                type="list",
                default=None,
                help="Numeric columns in item_features to build the KNN feature vectors from.",
                required=True,
            ),
            RecommenderParamSpec(
                name="n", type="int", default=None, help="Number of recommendations per user."
            ),
            RecommenderParamSpec(
                name="metric",
                type="str",
                default="cosine",
                help="Distance metric used by NearestNeighbors.",
                choices=("cosine", "euclidean", "manhattan"),
            ),
            RecommenderParamSpec(
                name="algorithm",
                type="str",
                default="brute",
                help="NearestNeighbors search algorithm.",
                choices=("brute", "auto", "ball_tree", "kd_tree"),
            ),
        ),
        handles_cold_start_users=False,
        handles_cold_start_items=True,
        description="Content-based KNN via NearestNeighbors over numeric "
        "feature columns — builds a user profile from the centroid of their "
        "known items' feature vectors.",
    )
)


# ===================================================================
# embedding_similarity (content-based)
# ===================================================================

# The item universe is always defined by InteractionMatrix, not item_features:
# items present in interactions.item_ids but MISSING a row in item_features
# get a zero feature vector; rows in item_features for items NOT in
# interactions.item_index are ignored (dropped).
#
# item_id_col is required because InteractionMatrix does not specify which
# column of item_features identifies the item — the fitter must be told
# explicitly (mirrors the user_segments workaround for popularity_segmented).


def _fit_embedding_similarity(
    interactions: InteractionMatrix,
    item_features: pd.DataFrame | None,
    params: dict[str, Any],
) -> FittedRecommender:
    if item_features is None:
        raise InvalidRecommenderParamsError(
            "algorithm 'embedding_similarity' requires item_features "
            "(a DataFrame with an embedding column)."
        )
    item_id_col = str(params["item_id_col"])
    embedding_col = str(params["embedding_col"])
    metric = str(params.get("metric", "cosine"))

    aligned = _align_item_features(item_features, item_id_col, interactions)

    embeddings_raw = aligned[embedding_col].tolist()
    try:
        dim = next(len(e) for e in embeddings_raw if isinstance(e, (list, tuple, np.ndarray)))
    except StopIteration:
        raise InvalidRecommenderParamsError(
            f"no valid embedding found in column {embedding_col!r}; every row is missing or NaN."
        ) from None
    zero_vec = [0.0] * dim
    embeddings = [
        list(e) if isinstance(e, (list, tuple, np.ndarray)) else zero_vec for e in embeddings_raw
    ]
    feature_matrix = np.array(embeddings, dtype=float)

    nn = NearestNeighbors(metric=metric, algorithm="brute")
    nn.fit(feature_matrix)

    return FittedRecommender(
        algorithm="embedding_similarity",
        algorithm_family="content",
        n_users=interactions.n_users,
        n_items=interactions.n_items,
        fit_stats={
            "n_interactions": interactions.n_interactions,
            "sparsity": 1.0 - interactions.density,
            "embedding_dim": dim,
        },
        model={
            "item_ids": interactions.item_ids,
            "item_index": interactions.item_index,
            "nn": nn,
            "feature_matrix": feature_matrix,
            "matrix": interactions.matrix,
            "user_index": interactions.user_index,
        },
    )


def _recommend_embedding_similarity(
    recommender: FittedRecommender,
    user_ids: list[Any] | None,
    n: int,
    exclude_known: bool,
) -> RecommendationResult:
    model = recommender.model
    nn = model["nn"]
    feature_matrix = model["feature_matrix"]
    matrix = model["matrix"]
    user_index = model["user_index"]
    item_ids = model["item_ids"]
    n_items = len(item_ids)

    if user_ids is None:
        user_ids = list(user_index.keys())

    rows: list[dict[str, Any]] = []
    for uid in user_ids:
        if uid not in user_index:
            continue
        uid_idx = user_index[uid]
        known_idx = matrix[uid_idx].indices.tolist()
        if not known_idx:
            continue

        profile = feature_matrix[known_idx].mean(axis=0)

        over_fetch = min(n + len(known_idx), n_items)
        distances, indices = nn.kneighbors(profile.reshape(1, -1), n_neighbors=over_fetch)
        dists = distances[0]
        idxs = indices[0]

        candidates: list[tuple[int, float]] = []
        for j, idx in enumerate(idxs):
            score = -float(dists[j])
            if exclude_known and idx in known_idx:
                continue
            candidates.append((idx, score))

        candidates.sort(key=lambda x: -x[1])
        for rank, (idx, score) in enumerate(candidates[:n], start=1):
            rows.append(
                {
                    "user_id": uid,
                    "item_id": item_ids[idx],
                    "rank": rank,
                    "score": score,
                }
            )

    return RecommendationResult(recommendations=pd.DataFrame(rows))


register_recommender(
    RecommenderSpec(
        key="embedding_similarity",
        family="content",
        fitter=_fit_embedding_similarity,
        recommend_fn=_recommend_embedding_similarity,
        similar_items_fn=None,
        required_params=("item_id_col", "embedding_col"),
        optional_params=("n", "metric"),
        param_metadata=(
            RecommenderParamSpec(
                name="item_id_col",
                type="str",
                default=None,
                help="Column in item_features identifying each item.",
                required=True,
            ),
            RecommenderParamSpec(
                name="embedding_col",
                type="str",
                default=None,
                help="Column in item_features holding each item's dense embedding vector.",
                required=True,
            ),
            RecommenderParamSpec(
                name="n", type="int", default=None, help="Number of recommendations per user."
            ),
            RecommenderParamSpec(
                name="metric",
                type="str",
                default="cosine",
                help="Distance metric used by NearestNeighbors.",
                choices=("cosine", "euclidean"),
            ),
        ),
        handles_cold_start_users=False,
        handles_cold_start_items=True,
        description="Content-based filtering via dense embedding similarity "
        "(sklearn NearestNeighbors, cosine/euclidean) — user profile is the "
        "centroid of their known items' embeddings; embeddings are supplied "
        "pre-computed (e.g. via ef.llm.embed) or user-supplied.",
    )
)


# ===================================================================
# Shared helpers for memory-based collaborative filtering (Story 7)
# ===================================================================


def _similarity_matrix(matrix, similarity: str) -> np.ndarray:
    """Dense n x n similarity matrix between the rows of a sparse (n, m) matrix.

    cosine: sklearn cosine_similarity (sparse-aware).
    pearson: adjusted/mean-centered cosine similarity -- each row's nonzero
        entries are centered on that row's own mean (computed only over its
        observed/nonzero entries) before cosine similarity is applied; this is
        the standard sparse approximation to Pearson correlation for rating
        matrices.
    jaccard: intersection-over-union of each row's nonzero column-index sets.
    """
    if similarity == "cosine":
        return cosine_similarity(matrix)
    if similarity == "pearson":
        centered = matrix.tocsr(copy=True).astype(float)
        row_start = centered.indptr[:-1]
        row_end = centered.indptr[1:]
        for i in range(centered.shape[0]):
            start, end = row_start[i], row_end[i]
            if end > start:
                row_mean = centered.data[start:end].mean()
                centered.data[start:end] -= row_mean
        return cosine_similarity(centered)
    if similarity == "jaccard":
        binary = (matrix > 0).astype(float)
        intersection = np.asarray((binary @ binary.T).todense())
        row_sums = np.asarray(binary.sum(axis=1)).ravel()
        union = row_sums[:, None] + row_sums[None, :] - intersection
        with np.errstate(divide="ignore", invalid="ignore"):
            sim = np.divide(intersection, union, out=np.zeros_like(intersection), where=union > 0)
        return sim
    raise InvalidRecommenderParamsError(f"unknown similarity: {similarity!r}")


def _common_counts(matrix) -> np.ndarray:
    """n x n matrix of the number of shared nonzero columns between each pair of rows."""
    binary = (matrix > 0).astype(float)
    return np.asarray((binary @ binary.T).todense())


def _top_k_sparse(
    sim: np.ndarray, k: int, common: np.ndarray, min_common: int
) -> sparse.csr_matrix:
    """Threshold *sim* to the top-k neighbors per row (excluding self and any
    pair below *min_common* shared observations), returned as a sparse CSR matrix."""
    n = sim.shape[0]
    masked = sim.copy()
    np.fill_diagonal(masked, -np.inf)
    masked[common < min_common] = -np.inf

    rows: list[int] = []
    cols: list[int] = []
    data: list[float] = []
    for i in range(n):
        row = masked[i]
        valid = np.where(row > -np.inf)[0]
        if valid.size == 0:
            continue
        top = valid[np.argsort(-row[valid])[:k]]
        for j in top:
            rows.append(i)
            cols.append(int(j))
            data.append(float(row[j]))
    return sparse.csr_matrix((data, (rows, cols)), shape=(n, n))


# ===================================================================
# user_knn_cf (collaborative, memory-based)
# ===================================================================


def _fit_user_knn_cf(
    interactions: InteractionMatrix,
    item_features: pd.DataFrame | None,
    params: dict[str, Any],
) -> FittedRecommender:
    k = int(params.get("k", 5))
    similarity = str(params.get("similarity", "cosine"))
    min_common_items = int(params.get("min_common_items", 1))
    matrix = interactions.matrix

    sim = _similarity_matrix(matrix, similarity)
    common = _common_counts(matrix)
    sim_topk = _top_k_sparse(sim, k, common, min_common_items)

    neighborhood_sizes = np.diff(sim_topk.indptr)

    return FittedRecommender(
        algorithm="user_knn_cf",
        algorithm_family="collaborative",
        n_users=interactions.n_users,
        n_items=interactions.n_items,
        fit_stats={
            "n_interactions": interactions.n_interactions,
            "sparsity": 1.0 - interactions.density,
            "similarity_matrix_density": (
                float(sim_topk.nnz / (interactions.n_users**2)) if interactions.n_users else 0.0
            ),
            "mean_neighborhood_size": (
                float(neighborhood_sizes.mean()) if len(neighborhood_sizes) else 0.0
            ),
        },
        model={
            "item_ids": interactions.item_ids,
            "similarity": sim_topk,
            "matrix": matrix,
            "user_index": interactions.user_index,
            "item_index": interactions.item_index,
        },
    )


def _recommend_user_knn_cf(
    recommender: FittedRecommender,
    user_ids: list[Any] | None,
    n: int,
    exclude_known: bool,
) -> RecommendationResult:
    model = recommender.model
    sim = model["similarity"]
    matrix = model["matrix"]
    user_index = model["user_index"]
    item_ids = model["item_ids"]

    if user_ids is None:
        user_ids = list(user_index.keys())

    rows: list[dict[str, Any]] = []
    for uid in user_ids:
        if uid not in user_index:
            continue
        uid_idx = user_index[uid]
        sim_row = sim[uid_idx]
        neighbor_idxs = sim_row.indices
        neighbor_weights = sim_row.data
        if neighbor_idxs.size == 0:
            continue

        known_idx = set(matrix[uid_idx].indices.tolist())

        item_scores: dict[int, float] = {}
        for n_idx, weight in zip(neighbor_idxs, neighbor_weights, strict=True):
            if weight <= 0:
                continue
            neighbor_row = matrix[n_idx]
            for item_idx, value in zip(neighbor_row.indices, neighbor_row.data, strict=True):
                if exclude_known and item_idx in known_idx:
                    continue
                item_scores[item_idx] = item_scores.get(item_idx, 0.0) + weight * value

        sorted_items = sorted(item_scores.items(), key=lambda x: -x[1])
        for rank, (item_idx, score) in enumerate(sorted_items[:n], start=1):
            rows.append(
                {
                    "user_id": uid,
                    "item_id": item_ids[item_idx],
                    "rank": rank,
                    "score": float(score),
                }
            )

    return RecommendationResult(recommendations=pd.DataFrame(rows))


register_recommender(
    RecommenderSpec(
        key="user_knn_cf",
        family="collaborative",
        fitter=_fit_user_knn_cf,
        recommend_fn=_recommend_user_knn_cf,
        similar_items_fn=None,
        required_params=(),
        optional_params=("k", "similarity", "n", "min_common_items"),
        param_metadata=(
            RecommenderParamSpec(
                name="k", type="int", default=5, help="Number of nearest neighbor users to use."
            ),
            RecommenderParamSpec(
                name="similarity",
                type="str",
                default="cosine",
                help="User-user similarity measure.",
                choices=("cosine", "pearson", "jaccard"),
            ),
            RecommenderParamSpec(
                name="n", type="int", default=None, help="Number of recommendations per user."
            ),
            RecommenderParamSpec(
                name="min_common_items",
                type="int",
                default=1,
                help="Minimum shared interacted items required for a neighbor to count.",
            ),
        ),
        handles_cold_start_users=False,
        handles_cold_start_items=False,
        description="User-based KNN collaborative filtering -- finds the K most "
        "similar users (cosine/pearson/jaccard) and recommends items they liked "
        "that the target user hasn't seen.",
    )
)


# ===================================================================
# item_knn_cf (collaborative, memory-based)
# ===================================================================


def _fit_item_knn_cf(
    interactions: InteractionMatrix,
    item_features: pd.DataFrame | None,
    params: dict[str, Any],
) -> FittedRecommender:
    k = int(params.get("k", 5))
    similarity = str(params.get("similarity", "cosine"))
    min_common_users = int(params.get("min_common_users", 1))
    matrix = interactions.matrix
    item_matrix = matrix.T.tocsr()

    sim = _similarity_matrix(item_matrix, similarity)
    common = _common_counts(item_matrix)
    sim_topk = _top_k_sparse(sim, k, common, min_common_users)

    neighborhood_sizes = np.diff(sim_topk.indptr)

    return FittedRecommender(
        algorithm="item_knn_cf",
        algorithm_family="collaborative",
        n_users=interactions.n_users,
        n_items=interactions.n_items,
        fit_stats={
            "n_interactions": interactions.n_interactions,
            "sparsity": 1.0 - interactions.density,
            "similarity_matrix_density": (
                float(sim_topk.nnz / (interactions.n_items**2)) if interactions.n_items else 0.0
            ),
            "mean_neighborhood_size": (
                float(neighborhood_sizes.mean()) if len(neighborhood_sizes) else 0.0
            ),
        },
        model={
            "item_ids": interactions.item_ids,
            "similarity": sim_topk,
            "matrix": matrix,
            "user_index": interactions.user_index,
            "item_index": interactions.item_index,
        },
    )


def _recommend_item_knn_cf(
    recommender: FittedRecommender,
    user_ids: list[Any] | None,
    n: int,
    exclude_known: bool,
) -> RecommendationResult:
    model = recommender.model
    sim = model["similarity"]
    matrix = model["matrix"]
    user_index = model["user_index"]
    item_ids = model["item_ids"]

    if user_ids is None:
        user_ids = list(user_index.keys())

    rows: list[dict[str, Any]] = []
    for uid in user_ids:
        if uid not in user_index:
            continue
        uid_idx = user_index[uid]
        user_row = matrix[uid_idx]
        known_idx = user_row.indices
        known_values = user_row.data
        if known_idx.size == 0:
            continue
        known_set = set(known_idx.tolist())

        item_scores: dict[int, float] = {}
        for item_idx, value in zip(known_idx, known_values, strict=True):
            sim_row = sim[item_idx]
            for neighbor_idx, weight in zip(sim_row.indices, sim_row.data, strict=True):
                if weight <= 0:
                    continue
                if exclude_known and neighbor_idx in known_set:
                    continue
                item_scores[neighbor_idx] = item_scores.get(neighbor_idx, 0.0) + weight * value

        sorted_items = sorted(item_scores.items(), key=lambda x: -x[1])
        for rank, (item_idx, score) in enumerate(sorted_items[:n], start=1):
            rows.append(
                {
                    "user_id": uid,
                    "item_id": item_ids[item_idx],
                    "rank": rank,
                    "score": float(score),
                }
            )

    return RecommendationResult(recommendations=pd.DataFrame(rows))


register_recommender(
    RecommenderSpec(
        key="item_knn_cf",
        family="collaborative",
        fitter=_fit_item_knn_cf,
        recommend_fn=_recommend_item_knn_cf,
        similar_items_fn=None,
        required_params=(),
        optional_params=("k", "similarity", "n", "min_common_users"),
        param_metadata=(
            RecommenderParamSpec(
                name="k", type="int", default=5, help="Number of nearest neighbor items to use."
            ),
            RecommenderParamSpec(
                name="similarity",
                type="str",
                default="cosine",
                help="Item-item similarity measure.",
                choices=("cosine", "pearson", "jaccard"),
            ),
            RecommenderParamSpec(
                name="n", type="int", default=None, help="Number of recommendations per user."
            ),
            RecommenderParamSpec(
                name="min_common_users",
                type="int",
                default=1,
                help="Minimum shared interacting users required for a neighbor to count.",
            ),
        ),
        handles_cold_start_users=False,
        handles_cold_start_items=False,
        description="Item-based KNN collaborative filtering -- for each item a "
        "user has interacted with, finds the K most similar items (cosine/"
        "pearson/jaccard) and scores unseen items by weighted similarity.",
    )
)


# ===================================================================
# Shared recommend_fn for factor-model collaborative filtering (Story 8)
# ===================================================================


def _recommend_factor_model(
    recommender: FittedRecommender,
    user_ids: list[Any] | None,
    n: int,
    exclude_known: bool,
) -> RecommendationResult:
    """Shared recommend_fn for factor-model algorithms (svd_cf, nmf_cf): ranks
    unseen items by the dot product of a user's latent factor vector with each
    item's latent factor vector (the reconstructed-rating approach)."""
    model = recommender.model
    user_factors = model["user_factors"]
    item_factors = model["item_factors"]
    matrix = model["matrix"]
    user_index = model["user_index"]
    item_ids = model["item_ids"]

    if user_ids is None:
        user_ids = list(user_index.keys())

    rows: list[dict[str, Any]] = []
    for uid in user_ids:
        if uid not in user_index:
            continue
        uid_idx = user_index[uid]
        scores = item_factors @ user_factors[uid_idx]

        sorted_indices = np.argsort(-scores).tolist()
        candidates = sorted_indices
        if exclude_known:
            known_set = set(matrix[uid_idx].indices.tolist())
            candidates = [idx for idx in sorted_indices if idx not in known_set]

        for rank, idx in enumerate(candidates[:n], start=1):
            rows.append(
                {
                    "user_id": uid,
                    "item_id": item_ids[idx],
                    "rank": rank,
                    "score": float(scores[idx]),
                }
            )

    return RecommendationResult(recommendations=pd.DataFrame(rows))


# ===================================================================
# svd_cf (collaborative, model-based)
# ===================================================================


def _fit_svd_cf(
    interactions: InteractionMatrix,
    item_features: pd.DataFrame | None,
    params: dict[str, Any],
) -> FittedRecommender:
    n_components = int(params.get("n_components", 10))
    seed = int(params.get("seed", 0))
    matrix = interactions.matrix

    # sklearn's TruncatedSVD requires ``n_components < min(n_samples, n_features)``; when the
    # smaller interaction-matrix dimension is <= 1 there is no latent space to extract (a 1-item
    # catalog, or a matrix with a single row/column), so the fit cannot be performed at all. The
    # previous ``else 1`` fallback fed n_components=1 to TruncatedSVD, which raised a raw
    # ``ValueError: ... a minimum of 2 is required by TruncatedSVD`` on any single-dimension
    # matrix -- an untyped crash that skipped even the sibling nmf_cf handles. Surface it as the
    # same typed InvalidRecommenderParamsError used across the family instead.
    if min(matrix.shape) < 2:
        raise InvalidRecommenderParamsError(
            "algorithm 'svd_cf' requires at least 2 users and 2 items to factorize; "
            f"got shape {matrix.shape}."
        )

    max_components = min(matrix.shape) - 1
    n_components = max(1, min(n_components, max_components))

    svd = TruncatedSVD(n_components=n_components, random_state=seed)
    user_factors = svd.fit_transform(matrix)
    item_factors = svd.components_.T

    return FittedRecommender(
        algorithm="svd_cf",
        algorithm_family="collaborative",
        n_users=interactions.n_users,
        n_items=interactions.n_items,
        fit_stats={
            "n_interactions": interactions.n_interactions,
            "sparsity": 1.0 - interactions.density,
            "n_components": n_components,
            "explained_variance_ratio": float(svd.explained_variance_ratio_.sum()),
        },
        model={
            "item_ids": interactions.item_ids,
            "user_factors": user_factors,
            "item_factors": item_factors,
            "matrix": matrix,
            "user_index": interactions.user_index,
            "item_index": interactions.item_index,
        },
    )


register_recommender(
    RecommenderSpec(
        key="svd_cf",
        family="collaborative",
        fitter=_fit_svd_cf,
        recommend_fn=_recommend_factor_model,
        similar_items_fn=None,
        required_params=(),
        optional_params=("n_components", "n", "seed"),
        param_metadata=(
            RecommenderParamSpec(
                name="n_components",
                type="int",
                default=10,
                help="Number of latent factors (SVD components) to learn.",
            ),
            RecommenderParamSpec(
                name="n", type="int", default=None, help="Number of recommendations per user."
            ),
            RecommenderParamSpec(
                name="seed", type="int", default=0, help="Random seed for the SVD solver."
            ),
        ),
        handles_cold_start_users=False,
        handles_cold_start_items=False,
        description="Matrix-factorization CF via sklearn TruncatedSVD -- learns "
        "latent user/item factors and ranks unseen items by predicted rating "
        "(dot product of factors).",
    )
)

# ===================================================================
# nmf_cf (collaborative, model-based)
# ===================================================================


def _fit_nmf_cf(
    interactions: InteractionMatrix,
    item_features: pd.DataFrame | None,
    params: dict[str, Any],
) -> FittedRecommender:
    n_components = int(params.get("n_components", 10))
    seed = int(params.get("seed", 0))
    max_iter = int(params.get("max_iter", 200))
    matrix = interactions.matrix

    max_components = min(matrix.shape) - 1
    n_components = max(1, min(n_components, max_components)) if max_components > 0 else 1

    nmf = NMF(n_components=n_components, random_state=seed, max_iter=max_iter, init="nndsvda")
    user_factors = nmf.fit_transform(matrix)
    item_factors = nmf.components_.T

    return FittedRecommender(
        algorithm="nmf_cf",
        algorithm_family="collaborative",
        n_users=interactions.n_users,
        n_items=interactions.n_items,
        fit_stats={
            "n_interactions": interactions.n_interactions,
            "sparsity": 1.0 - interactions.density,
            "n_components": n_components,
            "reconstruction_err": float(nmf.reconstruction_err_),
            "n_iter": int(nmf.n_iter_),
        },
        model={
            "item_ids": interactions.item_ids,
            "user_factors": user_factors,
            "item_factors": item_factors,
            "matrix": matrix,
            "user_index": interactions.user_index,
            "item_index": interactions.item_index,
        },
    )


register_recommender(
    RecommenderSpec(
        key="nmf_cf",
        family="collaborative",
        fitter=_fit_nmf_cf,
        recommend_fn=_recommend_factor_model,
        similar_items_fn=None,
        required_params=(),
        optional_params=("n_components", "n", "seed", "max_iter"),
        param_metadata=(
            RecommenderParamSpec(
                name="n_components",
                type="int",
                default=10,
                help="Number of latent factors (NMF components) to learn.",
            ),
            RecommenderParamSpec(
                name="n", type="int", default=None, help="Number of recommendations per user."
            ),
            RecommenderParamSpec(
                name="seed", type="int", default=0, help="Random seed for the NMF solver."
            ),
            RecommenderParamSpec(
                name="max_iter",
                type="int",
                default=200,
                help="Maximum number of NMF solver iterations.",
            ),
        ),
        handles_cold_start_users=False,
        handles_cold_start_items=False,
        description="Matrix-factorization CF via sklearn NMF -- learns "
        "non-negative latent user/item factors and ranks unseen items by "
        "predicted rating (dot product of factors).",
    )
)


# ===================================================================
# als (collaborative, model-based, requires emergentflow[recommend])
# ===================================================================


def _fit_als(
    interactions: InteractionMatrix,
    item_features: pd.DataFrame | None,
    params: dict[str, Any],
) -> FittedRecommender:
    """Fit implicit.als.AlternatingLeastSquares. Requires ``emergentflow[recommend]``
    (checked by ``ef.recommend.fit`` before this fitter ever runs -- see module/task docs)."""
    import implicit.als

    factors = int(params.get("factors", 64))
    regularization = float(params.get("regularization", 0.01))
    iterations = int(params.get("iterations", 15))
    seed = int(params.get("seed", 0))
    matrix = interactions.matrix.tocsr()

    model = implicit.als.AlternatingLeastSquares(
        factors=factors,
        regularization=regularization,
        iterations=iterations,
        random_state=seed,
    )
    model.fit(matrix)

    return FittedRecommender(
        algorithm="als",
        algorithm_family="collaborative",
        n_users=interactions.n_users,
        n_items=interactions.n_items,
        fit_stats={
            "n_interactions": interactions.n_interactions,
            "sparsity": 1.0 - interactions.density,
            "factors": factors,
            "iterations": iterations,
        },
        model={
            "item_ids": interactions.item_ids,
            "implicit_model": model,
            "user_factors": model.user_factors,
            "item_factors": model.item_factors,
            "matrix": matrix,
            "user_index": interactions.user_index,
            "item_index": interactions.item_index,
        },
    )


def _recommend_implicit_model(
    recommender: FittedRecommender,
    user_ids: list[Any] | None,
    n: int,
    exclude_known: bool,
) -> RecommendationResult:
    """Shared recommend_fn for implicit-backed algorithms (als, bpr): both expose the
    same ``.recommend(userid, user_items_row, N, filter_already_liked_items)`` API on
    their fitted model object -- normalized here under the single key
    ``"implicit_model"`` set by both fitters.

    ``implicit``'s ``recommend`` always returns exactly N items per user even when
    ``filter_already_liked_items=True`` reduces the candidate pool below N -- it
    pads the remaining slots with the user's own items at ``-inf``-equivalent scores
    (``np.finfo(np.float32).min``). We strip those padding entries so that every row
    in the returned ``RecommendationResult`` represents a genuine recommendation
    (score > ``np.finfo(np.float32).min``)."""
    model_dict = recommender.model
    implicit_model = model_dict["implicit_model"]
    matrix = model_dict["matrix"]
    user_index = model_dict["user_index"]
    item_ids = model_dict["item_ids"]

    if user_ids is None:
        user_ids = list(user_index.keys())

    _MIN_SCORE = np.finfo(np.float32).min

    rows: list[dict[str, Any]] = []
    for uid in user_ids:
        if uid not in user_index:
            continue
        uid_idx = user_index[uid]
        known_items: set[int] = set(matrix[uid_idx].indices) if exclude_known else set()
        ids_arr, scores_arr = implicit_model.recommend(
            uid_idx,
            matrix[uid_idx],
            N=n,
            filter_already_liked_items=exclude_known,
        )
        rank = 0
        for item_idx, score in zip(ids_arr, scores_arr, strict=True):
            if float(score) <= _MIN_SCORE:
                continue
            if item_idx in known_items:
                continue
            rank += 1
            rows.append(
                {
                    "user_id": uid,
                    "item_id": item_ids[int(item_idx)],
                    "rank": rank,
                    "score": float(score),
                }
            )

    return RecommendationResult(recommendations=pd.DataFrame(rows))


register_recommender(
    RecommenderSpec(
        key="als",
        family="collaborative",
        fitter=_fit_als,
        recommend_fn=_recommend_implicit_model,
        similar_items_fn=None,
        required_params=(),
        optional_params=("factors", "regularization", "iterations", "n", "seed"),
        param_metadata=(
            RecommenderParamSpec(
                name="factors", type="int", default=64, help="Number of latent factors."
            ),
            RecommenderParamSpec(
                name="regularization",
                type="float",
                default=0.01,
                help="L2 regularization strength.",
            ),
            RecommenderParamSpec(
                name="iterations",
                type="int",
                default=15,
                help="Number of ALS optimization iterations.",
            ),
            RecommenderParamSpec(
                name="n", type="int", default=None, help="Number of recommendations per user."
            ),
            RecommenderParamSpec(
                name="seed", type="int", default=0, help="Random seed for reproducible fitting."
            ),
        ),
        requires_extra="emergentflow[recommend]",
        handles_cold_start_users=False,
        handles_cold_start_items=False,
        description="Implicit-feedback matrix factorization via "
        "implicit.als.AlternatingLeastSquares -- requires the "
        "emergentflow[recommend] extra. Deterministic given seed.",
    )
)


# ===================================================================
# bpr (collaborative, model-based, requires emergentflow[recommend])
# ===================================================================


def _fit_bpr(
    interactions: InteractionMatrix,
    item_features: pd.DataFrame | None,
    params: dict[str, Any],
) -> FittedRecommender:
    """Fit implicit.bpr.BayesianPersonalizedRanking. Requires ``emergentflow[recommend]``
    (checked by ``ef.recommend.fit`` before this fitter ever runs -- see module/task docs)."""
    import implicit.bpr

    factors = int(params.get("factors", 64))
    learning_rate = float(params.get("learning_rate", 0.01))
    regularization = float(params.get("regularization", 0.01))
    iterations = int(params.get("iterations", 100))
    seed = int(params.get("seed", 0))
    matrix = interactions.matrix.tocsr()

    # num_threads=1: implicit's multi-threaded BPR SGD updates race on shared factor
    # rows, so random_state alone does not make item ranking reproducible across runs;
    # single-threaded fitting is required for the ADR-0002 equivalence gate to hold.
    model = implicit.bpr.BayesianPersonalizedRanking(
        factors=factors,
        learning_rate=learning_rate,
        regularization=regularization,
        iterations=iterations,
        random_state=seed,
        num_threads=1,
    )
    model.fit(matrix)

    return FittedRecommender(
        algorithm="bpr",
        algorithm_family="collaborative",
        n_users=interactions.n_users,
        n_items=interactions.n_items,
        fit_stats={
            "n_interactions": interactions.n_interactions,
            "sparsity": 1.0 - interactions.density,
            "factors": factors,
            "iterations": iterations,
        },
        model={
            "item_ids": interactions.item_ids,
            "implicit_model": model,
            "user_factors": model.user_factors,
            "item_factors": model.item_factors,
            "matrix": matrix,
            "user_index": interactions.user_index,
            "item_index": interactions.item_index,
        },
    )


register_recommender(
    RecommenderSpec(
        key="bpr",
        family="collaborative",
        fitter=_fit_bpr,
        recommend_fn=_recommend_implicit_model,
        similar_items_fn=None,
        required_params=(),
        optional_params=("factors", "learning_rate", "regularization", "iterations", "n", "seed"),
        param_metadata=(
            RecommenderParamSpec(
                name="factors", type="int", default=64, help="Number of latent factors."
            ),
            RecommenderParamSpec(
                name="learning_rate",
                type="float",
                default=0.01,
                help="SGD learning rate.",
            ),
            RecommenderParamSpec(
                name="regularization",
                type="float",
                default=0.01,
                help="L2 regularization strength.",
            ),
            RecommenderParamSpec(
                name="iterations",
                type="int",
                default=100,
                help="Number of BPR SGD iterations.",
            ),
            RecommenderParamSpec(
                name="n", type="int", default=None, help="Number of recommendations per user."
            ),
            RecommenderParamSpec(
                name="seed", type="int", default=0, help="Random seed for reproducible fitting."
            ),
        ),
        requires_extra="emergentflow[recommend]",
        handles_cold_start_users=False,
        handles_cold_start_items=False,
        description="Implicit-feedback Bayesian Personalized Ranking via "
        "implicit.bpr.BayesianPersonalizedRanking -- requires the "
        "emergentflow[recommend] extra. Deterministic given seed.",
    )
)


# ===================================================================
# ncf (deep, requires torch)
# ===================================================================


def _fit_ncf(
    interactions: InteractionMatrix,
    item_features: pd.DataFrame | None,
    params: dict[str, Any],
) -> FittedRecommender:
    """Fit a Neural Collaborative Filtering model (GMF + MLP, He et al. 2017). Requires torch
    (checked by ``ef.recommend.fit`` before this fitter ever runs -- see module/task docs).

    ``item_features`` is accepted but ignored: NCF is a pure collaborative deep model using only
    the interaction matrix."""
    import torch  # noqa: PLC0415  (lazy: torch is not a hard dependency)
    import torch.nn as nn  # noqa: PLC0415  (lazy: torch is not a hard dependency)

    embedding_dim = int(params.get("embedding_dim", 8))
    mlp_layers: list = list(params.get("mlp_layers", [32, 16, 8]))
    epochs = int(params.get("epochs", 20))
    batch_size = int(params.get("batch_size", 256))
    learning_rate = float(params.get("learning_rate", 0.01))
    negative_samples = int(params.get("negative_samples", 4))
    seed = int(params.get("seed", 0))

    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)

    n_users = interactions.n_users
    n_items = interactions.n_items
    matrix = interactions.matrix

    class _NCFModel(nn.Module):
        def __init__(
            self, n_users: int, n_items: int, embedding_dim: int, mlp_layers: list[int]
        ) -> None:
            super().__init__()
            self.user_emb_gmf = nn.Embedding(n_users, embedding_dim)
            self.item_emb_gmf = nn.Embedding(n_items, embedding_dim)
            self.user_emb_mlp = nn.Embedding(n_users, embedding_dim)
            self.item_emb_mlp = nn.Embedding(n_items, embedding_dim)

            layers: list[nn.Module] = []
            prev_dim = 2 * embedding_dim
            for layer_size in mlp_layers:
                layers.append(nn.Linear(prev_dim, layer_size))
                layers.append(nn.ReLU())
                prev_dim = layer_size
            self.mlp = nn.Sequential(*layers)

            self.output = nn.Linear(embedding_dim + mlp_layers[-1], 1)

        def forward(self, user_idx: torch.LongTensor, item_idx: torch.LongTensor) -> torch.Tensor:
            gmf = self.user_emb_gmf(user_idx) * self.item_emb_gmf(item_idx)
            mlp_in = torch.cat([self.user_emb_mlp(user_idx), self.item_emb_mlp(item_idx)], dim=-1)
            mlp_out = self.mlp(mlp_in)
            combined = torch.cat([gmf, mlp_out], dim=-1)
            return self.output(combined).squeeze(-1)

    model = _NCFModel(n_users, n_items, embedding_dim, mlp_layers)
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)
    criterion = nn.BCEWithLogitsLoss()

    pos_rows, pos_cols = matrix.nonzero()
    n_pos = len(pos_rows)
    rng = np.random.default_rng(seed)

    user_known: dict[int, set[int]] = {}
    for u_idx in range(n_users):
        user_known[u_idx] = set(matrix[u_idx].indices)

    final_loss = 0.0
    for _epoch in range(epochs):
        train_users: list[int] = []
        train_items: list[int] = []
        train_labels: list[float] = []

        for i in range(n_pos):
            u_idx = int(pos_rows[i])
            i_idx = int(pos_cols[i])

            train_users.append(u_idx)
            train_items.append(i_idx)
            train_labels.append(1.0)

            known = user_known[u_idx]
            neg_count = 0
            attempts = 0
            while neg_count < negative_samples and attempts < 20:
                neg_i = int(rng.integers(0, n_items))
                attempts += 1
                if neg_i not in known:
                    train_users.append(u_idx)
                    train_items.append(neg_i)
                    train_labels.append(0.0)
                    neg_count += 1

        indices = rng.permutation(len(train_users))
        train_users_arr = np.array(train_users, dtype=np.int64)[indices]
        train_items_arr = np.array(train_items, dtype=np.int64)[indices]
        train_labels_arr = np.array(train_labels, dtype=np.float32)[indices]

        n_train = len(train_users_arr)
        epoch_loss = 0.0
        n_batches = 0

        for start in range(0, n_train, batch_size):
            end = start + batch_size
            u_batch = torch.from_numpy(train_users_arr[start:end])
            i_batch = torch.from_numpy(train_items_arr[start:end])
            l_batch = torch.from_numpy(train_labels_arr[start:end])

            optimizer.zero_grad()
            outputs = model(u_batch, i_batch)
            loss = criterion(outputs, l_batch)
            loss.backward()
            optimizer.step()

            epoch_loss += loss.item()
            n_batches += 1

        final_loss = epoch_loss / max(n_batches, 1)

    model.eval()

    return FittedRecommender(
        algorithm="ncf",
        algorithm_family="deep",
        n_users=interactions.n_users,
        n_items=interactions.n_items,
        fit_stats={
            "n_interactions": interactions.n_interactions,
            "sparsity": 1.0 - interactions.density,
            "embedding_dim": embedding_dim,
            "epochs": epochs,
            "final_loss": final_loss,
        },
        model={
            "model": model,
            "item_ids": interactions.item_ids,
            "matrix": interactions.matrix,
            "user_index": interactions.user_index,
            "item_index": interactions.item_index,
        },
    )


def _recommend_ncf(
    recommender: FittedRecommender,
    user_ids: list[Any] | None,
    n: int,
    exclude_known: bool,
) -> RecommendationResult:
    """Recommend top-N unseen items via a fitted NCF model."""
    import torch  # noqa: PLC0415  (lazy: torch is not a hard dependency)

    model_dict = recommender.model
    model = model_dict["model"]
    item_ids = model_dict["item_ids"]
    matrix = model_dict["matrix"]
    user_index = model_dict["user_index"]

    if user_ids is None:
        user_ids = list(user_index.keys())

    n_items = len(item_ids)
    model.eval()

    rows: list[dict[str, Any]] = []
    with torch.no_grad():
        for uid in user_ids:
            if uid not in user_index:
                continue
            uid_idx = user_index[uid]
            known_items: set[int] = set(matrix[uid_idx].indices) if exclude_known else set()
            candidates = [i for i in range(n_items) if i not in known_items]
            if not candidates:
                continue

            user_idx_t = torch.full((len(candidates),), uid_idx, dtype=torch.long)
            item_idx_t = torch.tensor(candidates, dtype=torch.long)
            scores = torch.sigmoid(model(user_idx_t, item_idx_t)).numpy()

            top_positions = np.argsort(scores)[::-1][:n]
            for rank, pos in enumerate(top_positions, start=1):
                rows.append(
                    {
                        "user_id": uid,
                        "item_id": item_ids[candidates[pos]],
                        "rank": rank,
                        "score": float(scores[pos]),
                    }
                )

    return RecommendationResult(recommendations=pd.DataFrame(rows))


register_recommender(
    RecommenderSpec(
        key="ncf",
        family="deep",
        fitter=_fit_ncf,
        recommend_fn=_recommend_ncf,
        similar_items_fn=None,
        required_params=(),
        optional_params=(
            "embedding_dim",
            "mlp_layers",
            "epochs",
            "batch_size",
            "learning_rate",
            "negative_samples",
            "n",
            "seed",
        ),
        param_metadata=(
            RecommenderParamSpec(
                name="embedding_dim",
                type="int",
                default=8,
                help="Dimensionality of the user/item GMF and MLP embeddings.",
            ),
            RecommenderParamSpec(
                name="mlp_layers",
                type="list",
                default=[32, 16, 8],
                help="Hidden layer sizes of the MLP tower.",
            ),
            RecommenderParamSpec(
                name="epochs", type="int", default=20, help="Number of training epochs."
            ),
            RecommenderParamSpec(
                name="batch_size", type="int", default=256, help="Mini-batch size for training."
            ),
            RecommenderParamSpec(
                name="learning_rate",
                type="float",
                default=0.01,
                help="Adam optimizer learning rate.",
            ),
            RecommenderParamSpec(
                name="negative_samples",
                type="int",
                default=4,
                help="Number of negative examples sampled per positive interaction.",
            ),
            RecommenderParamSpec(
                name="n", type="int", default=None, help="Number of recommendations per user."
            ),
            RecommenderParamSpec(
                name="seed", type="int", default=0, help="Random seed for reproducible training."
            ),
        ),
        requires_extra="torch",
        handles_cold_start_users=False,
        handles_cold_start_items=False,
        description="Neural Collaborative Filtering (GMF + MLP, He et al. 2017) -- "
        "requires the optional torch dependency. Deterministic given seed.",
    )
)


# ===================================================================
# two_tower (deep, requires torch)
# ===================================================================


def _align_user_features(
    user_features: pd.DataFrame,
    user_id_col: str,
    interactions: InteractionMatrix,
) -> pd.DataFrame:
    """Reindex *user_features* to ``interactions.user_ids`` order -- the user-side sibling of
    ``_align_item_features``, used only by the two-tower model's optional user-feature input.

    Users in ``interactions.user_ids`` missing a row in *user_features* get an all-NaN row (the
    caller degrades this to a zero feature vector); rows in *user_features* for users not in
    ``interactions.user_index`` are dropped. Raises :class:`InvalidRecommenderParamsError` if
    *user_id_col* has duplicate values.
    """
    duplicated = user_features[user_id_col].duplicated()
    if duplicated.any():
        dupes = sorted(user_features.loc[duplicated, user_id_col].unique().tolist())
        raise InvalidRecommenderParamsError(
            f"user_features has duplicate {user_id_col!r} value(s): {dupes!r}; "
            "each user must appear at most once."
        )
    return user_features.set_index(user_id_col).reindex(interactions.user_ids)


def _fit_two_tower_impl(
    interactions: InteractionMatrix,
    item_features: pd.DataFrame | None,
    user_features: pd.DataFrame | None,
    params: dict[str, Any],
) -> FittedRecommender:
    import torch  # noqa: PLC0415  (lazy: torch is not a hard dependency)
    import torch.nn as nn  # noqa: PLC0415  (lazy: torch is not a hard dependency)
    import torch.nn.functional as F  # noqa: PLC0415  (lazy: torch is not a hard dependency)

    embedding_dim = int(params.get("user_embedding_dim", 16))
    item_embedding_dim = int(params.get("item_embedding_dim", 16))
    if embedding_dim != item_embedding_dim:
        raise InvalidRecommenderParamsError(
            "two_tower requires user_embedding_dim == item_embedding_dim "
            f"(dot-product scoring needs a shared embedding space); got "
            f"user_embedding_dim={embedding_dim!r}, "
            f"item_embedding_dim={item_embedding_dim!r}."
        )
    user_tower_layers = list(params.get("user_tower_layers", [32]))
    item_tower_layers = list(params.get("item_tower_layers", [32]))
    loss = str(params.get("loss", "bce"))
    if loss not in {"bce", "softmax_cross_entropy", "bpr_loss"}:
        raise InvalidRecommenderParamsError(
            f"unknown loss {loss!r} for two_tower; expected one of "
            "{'bce', 'softmax_cross_entropy', 'bpr_loss'}."
        )
    negative_sampling_ratio = int(params.get("negative_sampling_ratio", 4))
    epochs = int(params.get("epochs", 10))
    batch_size = int(params.get("batch_size", 64))
    learning_rate = float(params.get("learning_rate", 0.01))
    seed = int(params.get("seed", 0))
    item_id_col = str(params.get("item_id_col", "item_id"))
    user_id_col = str(params.get("user_id_col", "user_id"))
    use_user_id_embedding = bool(params.get("use_user_id_embedding", True))
    use_item_id_embedding = bool(params.get("use_item_id_embedding", True))

    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)

    if item_features is not None:
        aligned_items = _align_item_features(item_features, item_id_col, interactions)
        item_numeric_cols = aligned_items.select_dtypes(include="number").columns.tolist()
        if item_numeric_cols:
            item_feat_tensor = torch.tensor(
                aligned_items[item_numeric_cols].fillna(0.0).to_numpy(dtype=np.float32)
            )
            item_feature_dim = len(item_numeric_cols)
        else:
            item_feat_tensor = None
            item_feature_dim = 0
    else:
        item_feat_tensor = None
        item_feature_dim = 0

    if user_features is not None:
        aligned_users = _align_user_features(user_features, user_id_col, interactions)
        user_numeric_cols = aligned_users.select_dtypes(include="number").columns.tolist()
        if user_numeric_cols:
            user_feat_tensor = torch.tensor(
                aligned_users[user_numeric_cols].fillna(0.0).to_numpy(dtype=np.float32)
            )
            user_feature_dim = len(user_numeric_cols)
        else:
            user_feat_tensor = None
            user_feature_dim = 0
    else:
        user_feat_tensor = None
        user_feature_dim = 0

    if not use_user_id_embedding and user_features is None:
        raise InvalidRecommenderParamsError("use_user_id_embedding=False requires user_features")
    if not use_item_id_embedding and item_features is None:
        raise InvalidRecommenderParamsError("use_item_id_embedding=False requires item_features")

    class _Tower(nn.Module):
        def __init__(self, n_ids, feature_dim, hidden_layers, output_dim, use_id_embedding=True):
            super().__init__()
            self.use_id_embedding = use_id_embedding
            if use_id_embedding:
                self.id_embedding = nn.Embedding(n_ids, output_dim)
                input_dim = output_dim + feature_dim
            else:
                if feature_dim == 0:
                    raise InvalidRecommenderParamsError(
                        "two_tower tower requires either id embedding or features"
                    )
                input_dim = feature_dim
            layers: list[nn.Module] = []
            prev_dim = input_dim
            for h in hidden_layers:
                layers.append(nn.Linear(prev_dim, h))
                layers.append(nn.ReLU())
                prev_dim = h
            layers.append(nn.Linear(prev_dim, output_dim))
            self.mlp = nn.Sequential(*layers)

        def forward(
            self, ids: torch.LongTensor, features: torch.Tensor | None = None
        ) -> torch.Tensor:
            if self.use_id_embedding:
                emb = self.id_embedding(ids)
                x = torch.cat([emb, features], dim=-1) if features is not None else emb
                return self.mlp(x)
            assert features is not None
            return self.mlp(features)

    user_tower = _Tower(
        interactions.n_users,
        user_feature_dim,
        user_tower_layers,
        embedding_dim,
        use_user_id_embedding,
    )
    item_tower = _Tower(
        interactions.n_items,
        item_feature_dim,
        item_tower_layers,
        embedding_dim,
        use_item_id_embedding,
    )

    matrix = interactions.matrix
    pos_rows, pos_cols = matrix.nonzero()
    n_pos = len(pos_rows)
    rng = np.random.default_rng(seed)

    # Precompute each user's unseen-item complement once (not per positive example) and sample
    # negatives directly from it. This guarantees every sampled negative is a genuine non-
    # interaction -- unlike rejection sampling with a fixed attempt budget, which (confirmed via
    # simulation against this module's own test fixture) forces an already-known item back in as
    # a mislabeled "negative" ~8% of the time once attempts are exhausted, silently corrupting
    # the training signal for anything but very sparse/low-K interaction sets.
    user_known: dict[int, set[int]] = {}
    user_complement: dict[int, np.ndarray] = {}
    all_items_arr = np.arange(interactions.n_items, dtype=np.int64)
    for u_idx in range(interactions.n_users):
        known = set(matrix[u_idx].indices)
        user_known[u_idx] = known
        if known:
            complement = np.array(
                [i for i in range(interactions.n_items) if i not in known], dtype=np.int64
            )
        else:
            complement = all_items_arr
        # Degenerate case: user has interacted with every item in the catalog, so there is no
        # valid negative to sample. Fall back to the full catalog (unavoidable -- there is
        # nothing left to be a true negative) rather than raising or hanging.
        user_complement[u_idx] = complement if len(complement) > 0 else all_items_arr

    optimizer = torch.optim.Adam(
        list(user_tower.parameters()) + list(item_tower.parameters()),
        lr=learning_rate,
    )

    K = negative_sampling_ratio
    final_loss = 0.0
    for _epoch in range(epochs):
        pairs: list[tuple[int, int, list[int]]] = []
        for i in range(n_pos):
            u_idx = int(pos_rows[i])
            i_idx = int(pos_cols[i])
            complement = user_complement[u_idx]
            negatives = rng.choice(complement, size=K, replace=True).tolist()
            pairs.append((u_idx, i_idx, negatives))

        pairs = [pairs[i] for i in rng.permutation(len(pairs))]
        n_pairs = len(pairs)
        epoch_loss = 0.0
        n_batches = 0

        for start in range(0, n_pairs, batch_size):
            end = min(start + batch_size, n_pairs)
            batch = pairs[start:end]

            u_batch = torch.tensor([p[0] for p in batch], dtype=torch.long)
            pos_batch = torch.tensor([p[1] for p in batch], dtype=torch.long)
            neg_batch = torch.tensor([p[2] for p in batch], dtype=torch.long)

            u_feat = user_feat_tensor[u_batch] if user_feat_tensor is not None else None
            pos_feat = item_feat_tensor[pos_batch] if item_feat_tensor is not None else None
            neg_flat = neg_batch.reshape(-1)
            neg_feat = item_feat_tensor[neg_flat] if item_feat_tensor is not None else None

            user_emb = user_tower(u_batch, u_feat)
            pos_item_emb = item_tower(pos_batch, pos_feat)
            neg_item_emb = item_tower(neg_flat, neg_feat).reshape(len(batch), -1, embedding_dim)

            pos_score = (user_emb * pos_item_emb).sum(dim=-1)
            neg_score = (user_emb.unsqueeze(1) * neg_item_emb).sum(dim=-1)

            if loss == "bce":
                all_scores = torch.cat([pos_score.unsqueeze(1), neg_score], dim=1).reshape(-1)
                all_labels = torch.cat(
                    [
                        torch.ones_like(pos_score).unsqueeze(1),
                        torch.zeros_like(neg_score),
                    ],
                    dim=1,
                ).reshape(-1)
                batch_loss = nn.BCEWithLogitsLoss()(all_scores, all_labels)
            elif loss == "bpr_loss":
                diff = pos_score.unsqueeze(1) - neg_score
                batch_loss = -F.logsigmoid(diff).mean()
            else:  # softmax_cross_entropy
                logits = torch.cat([pos_score.unsqueeze(1), neg_score], dim=1)
                target = torch.zeros(len(batch), dtype=torch.long)
                batch_loss = nn.CrossEntropyLoss()(logits, target)

            optimizer.zero_grad()
            batch_loss.backward()
            optimizer.step()

            epoch_loss += batch_loss.item()
            n_batches += 1

        final_loss = epoch_loss / max(n_batches, 1)

    user_tower.eval()
    item_tower.eval()

    with torch.no_grad():
        all_item_ids_t = torch.arange(interactions.n_items, dtype=torch.long)
        item_embeddings = item_tower(all_item_ids_t, item_feat_tensor).numpy()

    return FittedRecommender(
        algorithm="two_tower",
        algorithm_family="deep",
        n_users=interactions.n_users,
        n_items=interactions.n_items,
        fit_stats={
            "n_interactions": interactions.n_interactions,
            "sparsity": 1.0 - interactions.density,
            "embedding_dim": embedding_dim,
            "epochs": epochs,
            "loss": loss,
            "final_loss": final_loss,
            "item_feature_dim": item_feature_dim,
            "user_feature_dim": user_feature_dim,
        },
        model={
            "user_tower": user_tower,
            "item_embeddings": item_embeddings,
            "user_feature_tensor": user_feat_tensor,
            "item_ids": interactions.item_ids,
            "matrix": interactions.matrix,
            "user_index": interactions.user_index,
            "item_index": interactions.item_index,
            "embedding_dim": embedding_dim,
            "use_user_id_embedding": use_user_id_embedding,
            "use_item_id_embedding": use_item_id_embedding,
        },
    )


def _recommend_two_tower(
    recommender: FittedRecommender,
    user_ids: list[Any] | None,
    n: int,
    exclude_known: bool,
) -> RecommendationResult:
    """Recommend top-N items by raw dot-product score between the user-tower embedding and
    precomputed item-tower embeddings.

    Ranking MUST use a raw dot product here, not cosine similarity: every one of the three loss
    variants (bce / bpr_loss / softmax_cross_entropy) trains on
    ``(user_emb * item_emb).sum(-1)`` -- an unnormalized dot product whose value depends on
    embedding magnitude, not just direction. An earlier version of this function ranked via
    ``sklearn.neighbors.NearestNeighbors(metric="cosine")`` instead, which silently re-ranks
    items by a *different* scoring function than the one the model was actually optimized
    against whenever item-embedding norms vary (confirmed empirically: on this module's own test
    fixture, item-embedding norms differ enough that 2 of 5 users' top-ranked item flips between
    the two scoring functions). Plain numpy top-N keeps ranking consistent with training and
    is the same pattern ``_recommend_ncf`` uses."""
    import torch  # noqa: PLC0415  (lazy: torch is not a hard dependency)

    model_dict = recommender.model
    user_tower = model_dict["user_tower"]
    item_embeddings = model_dict["item_embeddings"]
    user_feature_tensor = model_dict["user_feature_tensor"]
    item_ids = model_dict["item_ids"]
    matrix = model_dict["matrix"]
    user_index = model_dict["user_index"]
    use_user_id_embedding = model_dict.get("use_user_id_embedding", True)

    if user_ids is None:
        user_ids = list(user_index.keys())

    user_tower.eval()
    rows: list[dict[str, Any]] = []
    with torch.no_grad():
        for uid in user_ids:
            if uid not in user_index:
                continue
            uid_idx = user_index[uid]
            if use_user_id_embedding:
                uid_t = torch.tensor([uid_idx], dtype=torch.long)
                u_feat = user_feature_tensor[uid_t] if user_feature_tensor is not None else None
                user_embedding = user_tower(uid_t, u_feat).numpy()[0]
            else:
                if user_feature_tensor is None:
                    raise InvalidRecommenderParamsError(
                        "use_user_id_embedding=False requires user_features"
                    )
                user_embedding = user_tower(
                    torch.zeros(1, dtype=torch.long), user_feature_tensor[uid_idx : uid_idx + 1]
                ).numpy()[0]

            scores = item_embeddings @ user_embedding
            known_items: set[int] = set(matrix[uid_idx].indices) if exclude_known else set()

            order = np.argsort(scores)[::-1]
            rank = 0
            for item_idx in order:
                item_idx = int(item_idx)
                if item_idx in known_items:
                    continue
                rank += 1
                rows.append(
                    {
                        "user_id": uid,
                        "item_id": item_ids[item_idx],
                        "rank": rank,
                        "score": float(scores[item_idx]),
                    }
                )
                if rank >= n:
                    break

    return RecommendationResult(recommendations=pd.DataFrame(rows))


def _fit_two_tower(
    interactions: InteractionMatrix,
    item_features: pd.DataFrame | None,
    params: dict[str, Any],
) -> FittedRecommender:
    """Fitter shim satisfying the shared 3-argument Fitter callable type (Story 2) so
    'two_tower' also works through the generic RecommendFit node with item-features only
    (no user_features port exists on that generic node). Full item + user side-feature
    support is available via the dedicated ef.recommend.fit_two_tower() wrapper / the
    dedicated RecommendFitTwoTower node (Story 11), both of which call
    _fit_two_tower_impl directly with a real user_features argument."""
    return _fit_two_tower_impl(interactions, item_features, None, params)


register_recommender(
    RecommenderSpec(
        key="two_tower",
        family="deep",
        fitter=_fit_two_tower,
        recommend_fn=_recommend_two_tower,
        similar_items_fn=None,
        required_params=(),
        optional_params=(
            "user_embedding_dim",
            "item_embedding_dim",
            "user_tower_layers",
            "item_tower_layers",
            "loss",
            "negative_sampling_ratio",
            "epochs",
            "batch_size",
            "learning_rate",
            "seed",
            "item_id_col",
            "user_id_col",
            "use_user_id_embedding",
            "use_item_id_embedding",
            "n",
        ),
        param_metadata=(
            RecommenderParamSpec(
                name="user_embedding_dim",
                type="int",
                default=16,
                help="Output embedding dimensionality of the user tower.",
            ),
            RecommenderParamSpec(
                name="item_embedding_dim",
                type="int",
                default=16,
                help="Output embedding dimensionality of the item tower "
                "(must equal user_embedding_dim).",
            ),
            RecommenderParamSpec(
                name="user_tower_layers",
                type="list",
                default=[32],
                help="Hidden layer sizes of the user encoder tower.",
            ),
            RecommenderParamSpec(
                name="item_tower_layers",
                type="list",
                default=[32],
                help="Hidden layer sizes of the item encoder tower.",
            ),
            RecommenderParamSpec(
                name="loss",
                type="str",
                default="bce",
                help="Training loss used to contrast positive vs. sampled negative pairs.",
                choices=("bce", "softmax_cross_entropy", "bpr_loss"),
            ),
            RecommenderParamSpec(
                name="negative_sampling_ratio",
                type="int",
                default=4,
                help="Number of negative items sampled per positive interaction.",
            ),
            RecommenderParamSpec(
                name="epochs", type="int", default=10, help="Number of training epochs."
            ),
            RecommenderParamSpec(
                name="batch_size", type="int", default=64, help="Mini-batch size for training."
            ),
            RecommenderParamSpec(
                name="learning_rate",
                type="float",
                default=0.01,
                help="Adam optimizer learning rate.",
            ),
            RecommenderParamSpec(
                name="seed", type="int", default=0, help="Random seed for reproducible training."
            ),
            RecommenderParamSpec(
                name="item_id_col",
                type="str",
                default="item_id",
                help="Column in item_features identifying each item.",
            ),
            RecommenderParamSpec(
                name="user_id_col",
                type="str",
                default="user_id",
                help="Column in user_features identifying each user.",
            ),
            RecommenderParamSpec(
                name="use_user_id_embedding",
                type="bool",
                default=True,
                help="Whether the user tower learns an id embedding. True (id-only, or id+features "
                "mixed): user ids are embedded. False (metadata-only): user features alone drive "
                "the tower and user_features must be provided.",
            ),
            RecommenderParamSpec(
                name="use_item_id_embedding",
                type="bool",
                default=True,
                help="Whether the item tower learns an id embedding. True (id-only, or id+features "
                "mixed): item ids are embedded. False (metadata-only): item features alone drive "
                "the tower and item_features must be provided.",
            ),
            RecommenderParamSpec(
                name="n", type="int", default=None, help="Number of recommendations per user."
            ),
        ),
        requires_extra="torch",
        handles_cold_start_users=False,
        handles_cold_start_items=False,
        description="Two-tower retrieval model (separate user/item encoder towers, dot-product "
        "scoring) -- requires the optional torch dependency. Optionally consumes item-side "
        "features via the generic node; full item+user side features via "
        "ef.recommend.fit_two_tower(). Deterministic given seed.",
    )
)


# ===================================================================
# GRU4Rec (sequential)
# ===================================================================


def _fit_gru4rec(sequences: SequenceDataset, params: dict[str, Any]) -> FittedRecommender:
    """Fit a GRU4Rec next-item recommender on a :class:`SequenceDataset`.

    Each session sequence ``seq`` is split into input ``seq[:-1]`` and target ``seq[1:]``.
    Batches are padded to the longest sequence in the batch using ``n_items`` as the pad
    index (item indices from ``build_sequences`` live in ``[0, n_items)``), and the
    ``CrossEntropyLoss`` ignores those padding positions via ``ignore_index=n_items``.
    """
    import torch  # noqa: PLC0415  (lazy: torch is not a hard dependency)
    import torch.nn as nn  # noqa: PLC0415  (lazy: torch is not a hard dependency)

    class _GRU4Rec(nn.Module):
        """GRU-based next-item recommender (Hidasi et al., 2015).

        Embeds each item index, runs a GRU over the session's item sequence, and projects the
        hidden state at every timestep to logits over the real item catalog. The embedding
        table is sized ``n_items + 1`` so index ``n_items`` can serve as a padding token; the
        final linear layer still emits ``n_items`` logits (real items only).
        """

        def __init__(self, n_items: int, embedding_dim: int, hidden_dim: int, num_layers: int):
            super().__init__()
            self.embedding = nn.Embedding(n_items + 1, embedding_dim)
            self.gru = nn.GRU(embedding_dim, hidden_dim, num_layers, batch_first=True)
            self.fc = nn.Linear(hidden_dim, n_items)

        def forward(self, item_seq: torch.LongTensor) -> torch.Tensor:
            emb = self.embedding(item_seq)  # (batch, seq_len, emb_dim)
            gru_out, _ = self.gru(emb)  # (batch, seq_len, hidden_dim)
            logits = self.fc(gru_out)  # (batch, seq_len, n_items)
            return logits

    embedding_dim = int(params.get("embedding_dim", 32))
    hidden_dim = int(params.get("hidden_dim", 64))
    num_layers = int(params.get("num_layers", 1))
    epochs = int(params.get("epochs", 10))
    batch_size = int(params.get("batch_size", 64))
    learning_rate = float(params.get("learning_rate", 0.001))
    seed = int(params.get("seed", 0))

    n_items = len(sequences.item_ids)
    pad_idx = n_items

    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)

    model = _GRU4Rec(n_items, embedding_dim, hidden_dim, num_layers)
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)
    criterion = nn.CrossEntropyLoss(ignore_index=pad_idx)

    final_loss = 0.0
    for _epoch in range(epochs):
        order = torch.randperm(len(sequences.sequences))
        epoch_loss = 0.0
        n_batches = 0
        for start in range(0, len(sequences.sequences), batch_size):
            batch_idx = order[start : start + batch_size].tolist()
            batch_seqs = [sequences.sequences[i] for i in batch_idx]
            batch_seqs = [s for s in batch_seqs if len(s) > 1]
            if not batch_seqs:
                continue
            max_len = max(len(s) for s in batch_seqs)
            inputs = [s[:-1] for s in batch_seqs]
            targets = [s[1:] for s in batch_seqs]
            input_t = torch.tensor(
                [s + [pad_idx] * (max_len - 1 - len(s)) for s in inputs], dtype=torch.long
            )
            target_t = torch.tensor(
                [t + [pad_idx] * (max_len - 1 - len(t)) for t in targets], dtype=torch.long
            )
            logits = model(input_t)  # (batch, max_len-1, n_items)
            batch_loss = criterion(logits.reshape(-1, n_items), target_t.reshape(-1))
            optimizer.zero_grad()
            batch_loss.backward()
            optimizer.step()
            epoch_loss += batch_loss.item()
            n_batches += 1
        final_loss = epoch_loss / max(n_batches, 1)

    model.eval()

    return FittedRecommender(
        algorithm="gru4rec",
        algorithm_family="sequential",
        n_users=len(sequences.session_ids),
        n_items=n_items,
        fit_stats={
            "n_sessions": len(sequences.sequences),
            "n_items": n_items,
            "max_seq_len": sequences.max_seq_len,
            "embedding_dim": embedding_dim,
            "hidden_dim": hidden_dim,
            "epochs": epochs,
            "final_loss": final_loss,
        },
        model={
            "model": model,
            "sequences": sequences,
            "session_ids": sequences.session_ids,
            "item_ids": sequences.item_ids,
            "item_index": sequences.item_index,
            "max_seq_len": sequences.max_seq_len,
            "pad_idx": pad_idx,
        },
    )


def _recommend_gru4rec(
    recommender: FittedRecommender,
    user_ids: list[Any] | None,
    n: int,
    exclude_known: bool,
) -> RecommendationResult:
    """Recommend top-N next items per session using the fitted GRU4Rec model.

    Each session's last ``max_seq_len`` item indices are fed through the model in eval mode
    under ``torch.no_grad()``; the logits at the final timestep score every item. Sessions
    with no history (cold-start) are skipped.
    """
    import torch  # noqa: PLC0415  (lazy: torch is not a hard dependency)

    model_dict = recommender.model
    torch_model = model_dict["model"]
    sequences = model_dict["sequences"]
    session_ids = model_dict["session_ids"]
    item_ids = model_dict["item_ids"]
    max_seq_len = model_dict["max_seq_len"]

    if user_ids is None:
        user_ids = list(session_ids)

    session_to_seq = dict(zip(sequences.session_ids, sequences.sequences, strict=True))

    torch_model.eval()
    rows: list[dict[str, Any]] = []
    with torch.no_grad():
        for session_id in user_ids:
            if session_id not in session_to_seq:
                continue
            seq = session_to_seq[session_id]
            input_seq = seq[-max_seq_len:]
            input_t = torch.tensor([input_seq], dtype=torch.long)
            logits = torch_model(input_t)[0, -1, :]  # (n_items,)
            scores = logits.numpy()

            known_items: set[Any] = set()
            if exclude_known:
                known_items = {item_ids[i] for i in input_seq}

            order = np.argsort(scores)[::-1]
            rank = 0
            for item_idx in order:
                item_idx = int(item_idx)
                item_id = item_ids[item_idx]
                if item_id in known_items:
                    continue
                rank += 1
                rows.append(
                    {
                        "user_id": session_id,
                        "item_id": item_id,
                        "rank": rank,
                        "score": float(scores[item_idx]),
                    }
                )
                if rank >= n:
                    break

    recommendations = pd.DataFrame(rows, columns=["user_id", "item_id", "rank", "score"])
    return RecommendationResult(recommendations=recommendations)


register_recommender(
    RecommenderSpec(
        key="gru4rec",
        family="sequential",
        fitter=None,
        recommend_fn=_recommend_gru4rec,
        similar_items_fn=None,
        sequence_fitter=_fit_gru4rec,
        required_params=(),
        optional_params=(
            "embedding_dim",
            "hidden_dim",
            "num_layers",
            "epochs",
            "batch_size",
            "learning_rate",
            "seed",
        ),
        param_metadata=(
            RecommenderParamSpec(
                name="embedding_dim", type="int", default=32, help="Item embedding dimension."
            ),
            RecommenderParamSpec(
                name="hidden_dim", type="int", default=64, help="GRU hidden dimension."
            ),
            RecommenderParamSpec(
                name="num_layers", type="int", default=1, help="Number of GRU layers."
            ),
            RecommenderParamSpec(name="epochs", type="int", default=10, help="Training epochs."),
            RecommenderParamSpec(
                name="batch_size", type="int", default=64, help="Mini-batch size."
            ),
            RecommenderParamSpec(
                name="learning_rate", type="float", default=0.001, help="Adam learning rate."
            ),
            RecommenderParamSpec(name="seed", type="int", default=0, help="Random seed."),
        ),
        requires_extra="torch",
        handles_cold_start_users=False,
        handles_cold_start_items=False,
        description="Session-based sequential recommender using a GRU (GRU4Rec). Requires torch.",
    )
)
