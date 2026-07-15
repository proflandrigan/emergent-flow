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
from emergentflow.recommend.models import FittedRecommender, RecommendationResult
from emergentflow.recommend.registry import RecommenderSpec, register_recommender

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
    for uid in user_ids:
        rng = np.random.default_rng(seed)
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
        seg = user_to_segment.get(uid)
        scores = segment_scores.get(seg, global_scores)
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
            "user_ids": interactions.user_ids,
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

    max_components = min(matrix.shape) - 1
    n_components = max(1, min(n_components, max_components)) if max_components > 0 else 1

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
        requires_extra="emergentflow[recommend]",
        handles_cold_start_users=False,
        handles_cold_start_items=False,
        description="Implicit-feedback Bayesian Personalized Ranking via "
        "implicit.bpr.BayesianPersonalizedRanking -- requires the "
        "emergentflow[recommend] extra. Deterministic given seed.",
    )
)
