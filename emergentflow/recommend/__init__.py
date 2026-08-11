"""
emergentflow.recommend
~~~~~~~~~~~~~~~~~~~~~~~
The ``ef.recommend`` family: recommender systems (Epic 15). A parallel seam to ``ef.ml`` and
``ef.stats`` -- see docs/adr/0021-recommender-systems-architecture.md for why recommenders are
not routed through the sklearn estimator adapter. Three wrapper functions
(``fit``/``recommend``/``similar_items``) are the single seam every recommender node's ``codegen``
and ``execute`` both route through, so ADR-0002 equivalence holds by construction exactly as it
does for ``emergentflow.stats.fit_model``.

No algorithms are registered by this module. The curated catalog of actual algorithms
(popularity, SVD, ALS, ...) is registered as data by a future ``emergentflow.recommend.catalog``
module (Epic 15, Story 4 onward), imported here for its side effect once it exists -- mirroring
``emergentflow.stats.catalog`` / ``emergentflow.ml.catalog``. Until that catalog lands, calling
``fit`` with any algorithm key raises ``UnknownAlgorithmError`` (there is nothing registered yet).
"""

from __future__ import annotations

import importlib.util
import json
import math
import time
from pathlib import Path
from typing import Any

import joblib  # type: ignore[import-untyped]
import numpy as np
import pandas as pd

from emergentflow import __version__
from emergentflow.api import public_op
from emergentflow.errors import ModelPersistenceError
from emergentflow.ir.common import ArtifactRef
from emergentflow.recommend.errors import (
    InvalidRecommenderParamsError,
    MissingOptionalDependencyError,
)
from emergentflow.recommend.interactions import InteractionMatrix, _prepare_interactions
from emergentflow.recommend.metrics import (
    _auc_at_k,
    _average_precision_at_k,
    _hit,
    _mrr_at_k,
    _ndcg_at_k,
    _precision_at_k,
    _recall_at_k,
)
from emergentflow.recommend.models import (
    EvalResult,
    FittedRecommender,
    RecommendationResult,
    SequenceDataset,
)
from emergentflow.recommend.registry import RecommenderSpec, get_recommender_spec
from emergentflow.recommend.sequences import build_sequences as _build_sequences
from emergentflow.recommend.transforms import (
    encode_categorical_features as _encode_categorical_features,
)
from emergentflow.recommend.transforms import (
    weight_interactions_by_recency as _weight_interactions_by_recency,
)

__all__ = [
    "SequenceDataset",
    "build_sequences",
    "compare",
    "encode_categorical_features",
    "evaluate",
    "fit",
    "fit_sequence",
    "fit_two_tower",
    "hybrid_switching",
    "hybrid_weighted",
    "prepare_interactions",
    "random_split",
    "recommend",
    "similar_items",
    "temporal_split",
    "save_model",
    "load_model",
    "weight_interactions_by_recency",
]

#: Pip extra -> probe modules whose absence means the extra is not installed, mirroring
#: ``emergentflow.stats._EXTRA_PROBE_MODULES``. No registered algorithm uses these yet (Stories
#: 8/10/11 will), but the mapping is defined now so ``fit``'s ``requires_extra`` check is correct
#: as soon as the first gated algorithm registers.
_EXTRA_PROBE_MODULES: dict[str, tuple[str, ...]] = {
    "emergentflow[recommend]": ("implicit",),
    "torch": ("torch",),
}


def _require_extra(extra: str) -> None:
    """Raise MissingOptionalDependencyError(extra) unless all of *extra*'s probe modules import."""
    probes = _EXTRA_PROBE_MODULES.get(extra)
    if not probes or any(importlib.util.find_spec(probe) is None for probe in probes):
        raise MissingOptionalDependencyError(extra)


def _validate_params(spec: RecommenderSpec, params: dict[str, Any]) -> dict[str, Any]:
    """Validate *params* against *spec*'s required/optional param allow-list; return a copy.

    The shared params gate every ``fit`` call passes through, mirroring
    ``emergentflow.stats.spec._prepare_model_spec``'s unknown/missing-field checks. Raises
    :class:`InvalidRecommenderParamsError` for an unknown param key or a missing required one.
    """
    allowed = set(spec.required_params) | set(spec.optional_params)
    unknown = sorted(set(params) - allowed)
    if unknown:
        raise InvalidRecommenderParamsError(
            f"unknown param(s) {unknown!r} for algorithm {spec.key!r}; "
            f"allowed params are {sorted(allowed)!r}."
        )
    missing = [p for p in spec.required_params if p not in params]
    if missing:
        raise InvalidRecommenderParamsError(
            f"algorithm {spec.key!r} requires param(s) {missing!r}."
        )
    return dict(params)


@public_op(name="ef.recommend.encode_categorical_features")
def encode_categorical_features(
    df: pd.DataFrame,
    *,
    columns: list[str],
    id_col: str,
    strategy: str = "onehot",
    drop_first: bool = False,
) -> pd.DataFrame:
    """Encode categorical columns in a user- or item-feature frame while preserving its id column.

    The dedicated transform for preparing raw categorical user/item feature frames before
    wiring them into the two-tower seam (Epic 15, Story 11), which only consumes numeric
    columns. ``strategy='onehot'`` produces one indicator column per category level (named
    ``category_value``); ``strategy='ordinal'`` produces one numeric column per input column
    (keeping the original names). ``drop_first`` (one-hot only) drops one level per input
    column to avoid collinearity. The id column is preserved untouched as the first column of
    the returned frame. Raises
    :class:`~emergentflow.recommend.errors.InvalidRecommenderParamsError` if ``id_col`` or any
    of ``columns`` is absent from *df*, or ``strategy`` is not ``'onehot'``/``'ordinal'``.
    Never mutates *df*.
    """
    return _encode_categorical_features(
        df, columns=columns, id_col=id_col, strategy=strategy, drop_first=drop_first
    )


@public_op(name="ef.recommend.weight_interactions_by_recency")
def weight_interactions_by_recency(
    df: pd.DataFrame,
    *,
    timestamp_col: str,
    user_col: str,
    item_col: str,
    value_col: str = "weight",
    decay: str = "exponential",
    half_life_days: float = 30.0,
    reference_time: pd.Timestamp | str | None = None,
) -> pd.DataFrame:
    """Return a copy of *df* with an added numeric *value_col* that decays with event age.

    The single seam every recency-weighting node routes through (Epic 15), producing a
    ``value_col`` suitable for ``prepare_interactions``. Weights decay exponentially with event
    age measured against *reference_time* (defaulting to the newest timestamp in *df*): an event
    *half_life_days* old is weighted ``0.5``. Raises
    :class:`~emergentflow.recommend.errors.InvalidRecommenderParamsError` if ``timestamp_col``,
    ``user_col``, or ``item_col`` is absent from *df*, ``decay`` is not ``'exponential'``,
    ``half_life_days`` is not positive, or ``timestamp_col`` contains null/NaT values (recency
    is undefined for a missing timestamp). Never mutates *df*.
    """
    return _weight_interactions_by_recency(
        df,
        timestamp_col=timestamp_col,
        user_col=user_col,
        item_col=item_col,
        value_col=value_col,
        decay=decay,
        half_life_days=half_life_days,
        reference_time=reference_time,
    )


@public_op(name="ef.recommend.build_sequences")
def build_sequences(
    df: pd.DataFrame,
    *,
    user_col: str,
    item_col: str,
    session_col: str | None = None,
    timestamp_col: str | None = None,
    max_seq_len: int = 50,
    min_seq_len: int = 2,
) -> SequenceDataset:
    """Build a SequenceDataset from an event DataFrame.

    The single seam every sequential-recommender data-prep node routes through (Epic 15).
    Each session becomes one chronologically-ordered sequence of item indices; when
    ``session_col`` is None, each user is treated as one session. Sequences are sorted by
    ``timestamp_col`` when provided, truncated to the last ``max_seq_len`` items, and
    sequences shorter than ``min_seq_len`` are dropped. Item indices are deterministic
    (sorted item ids) and lie in ``[0, n_items)``. Raises
    :class:`~emergentflow.recommend.errors.InvalidRecommenderParamsError` if ``user_col``/
    ``item_col`` (or ``session_col``/``timestamp_col`` when provided) are absent from *df*,
    or ``max_seq_len < min_seq_len``/``min_seq_len < 2``. Never mutates *df*.
    """
    return _build_sequences(
        df,
        user_col=user_col,
        item_col=item_col,
        session_col=session_col,
        timestamp_col=timestamp_col,
        max_seq_len=max_seq_len,
        min_seq_len=min_seq_len,
    )


@public_op(name="ef.recommend.fit")
def fit(
    interactions: InteractionMatrix,
    *,
    algorithm: str,
    item_features: pd.DataFrame | None = None,
    params: dict[str, Any] | None = None,
) -> FittedRecommender:
    """Fit a curated, allow-listed recommender algorithm and return an inspectable
    FittedRecommender.

    The single seam every recommender-fit node routes through (Epic 15, Story 2). ``algorithm`` is
    validated against the allow-list registry (raising
    :class:`~emergentflow.recommend.errors.UnknownAlgorithmError` via
    :func:`~emergentflow.recommend.registry.get_recommender_spec`); ``params`` keys are validated
    against that algorithm's required/optional allow-list, raising
    :class:`~emergentflow.recommend.errors.InvalidRecommenderParamsError` for unknown or missing
    keys. An algorithm requiring an optional dependency extra that is absent raises
    :class:`~emergentflow.recommend.errors.MissingOptionalDependencyError`. ``item_features`` is
    only consumed by content-based-family fitters; other families ignore it. The resolved
    algorithm's own ``fitter`` assembles the backend call and builds the ``FittedRecommender``.
    Because both ``compile_to_code``'s emitted code and ``execute`` reach a recommender only
    through this function, ADR-0002 equivalence holds by construction. Never mutates
    ``interactions`` or ``item_features``.
    """
    spec = get_recommender_spec(algorithm)
    resolved_params = _validate_params(spec, params or {})
    if spec.requires_extra is not None:
        _require_extra(spec.requires_extra)
    if spec.fitter is None:
        raise InvalidRecommenderParamsError(
            f"algorithm {algorithm!r} must be fit via ef.recommend.fit_sequence(...)."
        )
    return spec.fitter(interactions, item_features, resolved_params)


@public_op(name="ef.recommend.fit_sequence")
def fit_sequence(
    sequences: SequenceDataset,
    *,
    algorithm: str,
    params: dict[str, Any] | None = None,
) -> FittedRecommender:
    """Fit a curated sequential recommender algorithm."""
    spec = get_recommender_spec(algorithm)
    resolved_params = _validate_params(spec, params or {})
    if spec.requires_extra is not None:
        _require_extra(spec.requires_extra)
    if spec.sequence_fitter is None:
        raise InvalidRecommenderParamsError(
            f"algorithm {algorithm!r} is not a sequence model; use ef.recommend.fit(...) instead."
        )
    return spec.sequence_fitter(sequences, resolved_params)


@public_op(name="ef.recommend.fit_two_tower")
def fit_two_tower(
    interactions: InteractionMatrix,
    *,
    item_features: pd.DataFrame | None = None,
    user_features: pd.DataFrame | None = None,
    params: dict[str, Any] | None = None,
) -> FittedRecommender:
    """Fit the two-tower deep recommender (Epic 15, Story 11) -- a dedicated seam alongside
    ``fit()`` because two-tower is the only algorithm that consumes BOTH item-feature and
    user-feature side inputs; the shared ``Fitter`` callable type (Story 2) used by every other
    algorithm only carries one optional DataFrame (``item_features``), so two-tower keeps its
    own seam here rather than widening that type for every existing fitter. Mirrors ``fit()``'s
    algorithm-key lookup / param validation / optional-extra gating exactly, then calls
    ``catalog._fit_two_tower_impl`` directly with the extra ``user_features`` argument. Because
    both the compiled code (via the dedicated ``RecommendFitTwoTower`` node) and ``execute``
    reach this only through this function, ADR-0002 equivalence holds by construction. Never
    mutates ``interactions``, ``item_features``, or ``user_features``.

    ``item_features`` (optional) is one row per item keyed by an ``item_id`` column (or the
    ``item_id_col`` param) plus numeric feature columns; ``user_features`` is the same keyed by a
    ``user_id`` column (``user_id_col``). Only numeric columns feed the towers -- non-numeric
    columns are ignored; multi-hot indicator columns from ``ef.clean.encode_lists`` are a natural
    fit. Each id may appear at most once per feature frame.
    """
    from emergentflow.recommend.catalog import _fit_two_tower_impl  # noqa: PLC0415

    spec = get_recommender_spec("two_tower")
    resolved_params = _validate_params(spec, params or {})
    if spec.requires_extra is not None:
        _require_extra(spec.requires_extra)
    return _fit_two_tower_impl(interactions, item_features, user_features, resolved_params)


@public_op(name="ef.recommend.recommend")
def recommend(
    recommender: FittedRecommender,
    *,
    user_ids: list[Any] | None = None,
    n: int = 10,
    exclude_known: bool = True,
) -> RecommendationResult:
    """Generate top-N recommendations from a fitted recommender.

    The single seam every recommend node routes through (Epic 15, Story 2). ``user_ids=None``
    means "every user the recommender was fit on". ``exclude_known`` drops items already present
    in the training interactions for a user (the default recommender-systems convention).
    Dispatches to the resolved algorithm's own ``recommend_fn`` (looked up by
    ``recommender.algorithm``).
    """
    spec = get_recommender_spec(recommender.algorithm)
    return spec.recommend_fn(recommender, user_ids, n, exclude_known)


@public_op(name="ef.recommend.similar_items")
def similar_items(
    recommender: FittedRecommender,
    *,
    item_ids: list[Any],
    n: int = 10,
) -> RecommendationResult:
    """Return the N most similar items to each given item, for algorithms that support it.

    The single seam every similar-items node routes through (Epic 15, Story 2). Raises
    :class:`~emergentflow.recommend.errors.InvalidRecommenderParamsError` if the fitted
    recommender's algorithm does not support item-item similarity (its registry entry's
    ``similar_items_fn`` is ``None``).
    """
    spec = get_recommender_spec(recommender.algorithm)
    if spec.similar_items_fn is None:
        raise InvalidRecommenderParamsError(
            f"algorithm {recommender.algorithm!r} does not support item-item similarity."
        )
    return spec.similar_items_fn(recommender, item_ids, n)


_VALID_EVAL_METRICS = frozenset(
    {
        "precision_at_k",
        "recall_at_k",
        "ndcg_at_k",
        "map_at_k",
        "hit_rate",
        "coverage",
        "diversity",
        "novelty",
        "mrr_at_k",
        "auc_at_k",
    }
)


@public_op(name="ef.recommend.evaluate")
def evaluate(
    recommender: FittedRecommender,
    test_interactions: InteractionMatrix,
    *,
    k: int = 10,
    metrics: list[str] | None = None,
) -> EvalResult:
    """Score a fitted recommender's top-k recommendations against held-out interactions.

    The single seam every ``recommend.evaluate`` node routes through (Epic 15, Story 12). For
    each user present in ``test_interactions`` (i.e. with at least one held-out interaction),
    generates top-``k`` recommendations via the existing :func:`recommend` wrapper
    (``exclude_known=True``, so items already seen in the recommender's own training
    interactions are excluded) and scores them against that user's held-out item set. Users the
    recommender cannot score for (absent from the fitted recommender's training user index) are
    still scored -- ``recommend()`` handles unknown/cold-start users per the algorithm's own
    cold-start behavior.

    ``metrics`` selects the subset of ``{"precision_at_k", "recall_at_k", "ndcg_at_k",
    "map_at_k", "hit_rate", "coverage", "diversity", "novelty", "mrr_at_k", "auc_at_k"}`` to
    compute; ``None`` (the default) computes all ten. Raises
    :class:`~emergentflow.recommend.errors.InvalidRecommenderParamsError` for an unknown metric
    name or ``k <= 0``.

    Three of the ten metrics are system-level (computed once across all users, never per-user):
    coverage = fraction of catalog items appearing in any user's top-k; diversity = 1 -- mean
    pairwise cosine similarity of users' top-k item sets; novelty = mean ``-log2(popularity)`` of
    recommended items, popularity measured within ``test_interactions``. These appear only in
    ``aggregate``, not in ``per_user``.

    Returns an :class:`EvalResult` with a tidy per-user metrics frame and an aggregate dict
    (``mean_<metric>`` for the four per-user metrics, plus ``hit_rate`` -- the mean of the
    per-user ``hit`` column -- and ``map_at_k`` -- the mean of the per-user
    ``average_precision`` column). Never mutates ``recommender`` or ``test_interactions``.
    """
    if k <= 0:
        raise InvalidRecommenderParamsError(f"k must be positive; got {k!r}.")
    requested = set(metrics) if metrics is not None else set(_VALID_EVAL_METRICS)
    unknown = requested - _VALID_EVAL_METRICS
    if unknown:
        raise InvalidRecommenderParamsError(
            f"unknown metric(s) {sorted(unknown)!r}; expected a subset of "
            f"{sorted(_VALID_EVAL_METRICS)!r}."
        )

    test_users = [
        uid
        for uid in test_interactions.user_ids
        if test_interactions.matrix.getrow(test_interactions.user_index[uid]).nnz > 0
    ]

    rows: list[dict[str, Any]] = []
    if test_users:
        result = recommend(recommender, user_ids=test_users, n=k, exclude_known=True)
        recs_by_user: dict[Any, list[Any]] = {uid: [] for uid in test_users}
        for uid, item_id, rank in zip(
            result.recommendations["user_id"],
            result.recommendations["item_id"],
            result.recommendations["rank"],
            strict=True,
        ):
            recs_by_user[uid].append((int(rank), item_id))
        for uid in recs_by_user:
            recs_by_user[uid] = [
                item_id for _, item_id in sorted(recs_by_user[uid], key=lambda pair: pair[0])
            ]

        for uid in test_users:
            row_idx = test_interactions.user_index[uid]
            relevant = {
                test_interactions.item_ids[col]
                for col in test_interactions.matrix.getrow(row_idx).indices
            }
            recommended = recs_by_user[uid]
            row: dict[str, Any] = {"user_id": uid}
            if "precision_at_k" in requested:
                row["precision_at_k"] = _precision_at_k(recommended, relevant, k)
            if "recall_at_k" in requested:
                row["recall_at_k"] = _recall_at_k(recommended, relevant, k)
            if "ndcg_at_k" in requested:
                row["ndcg_at_k"] = _ndcg_at_k(recommended, relevant, k)
            if "hit_rate" in requested:
                row["hit"] = _hit(recommended, relevant, k)
            if "map_at_k" in requested:
                row["average_precision"] = _average_precision_at_k(recommended, relevant, k)
            if "mrr_at_k" in requested:
                row["mrr_at_k"] = _mrr_at_k(recommended, relevant, k)
            if "auc_at_k" in requested:
                row["auc_at_k"] = _auc_at_k(recommended, relevant, k)
            rows.append(row)

    per_user = pd.DataFrame(rows) if rows else pd.DataFrame(columns=["user_id"])

    aggregate: dict[str, Any] = {}
    if "precision_at_k" in requested:
        aggregate["mean_precision_at_k"] = float(per_user["precision_at_k"].mean()) if rows else 0.0
    if "recall_at_k" in requested:
        aggregate["mean_recall_at_k"] = float(per_user["recall_at_k"].mean()) if rows else 0.0
    if "ndcg_at_k" in requested:
        aggregate["mean_ndcg_at_k"] = float(per_user["ndcg_at_k"].mean()) if rows else 0.0
    if "hit_rate" in requested:
        aggregate["hit_rate"] = float(per_user["hit"].mean()) if rows else 0.0
    if "map_at_k" in requested:
        aggregate["map_at_k"] = float(per_user["average_precision"].mean()) if rows else 0.0
    if "mrr_at_k" in requested:
        aggregate["mean_mrr_at_k"] = float(per_user["mrr_at_k"].mean()) if rows else 0.0
    if "auc_at_k" in requested:
        aggregate["mean_auc_at_k"] = float(per_user["auc_at_k"].mean()) if rows else 0.0

    if "coverage" in requested:
        if test_users and test_interactions.n_items > 0:
            recommended_union: set[Any] = set()
            for items in recs_by_user.values():
                recommended_union.update(items[:k])
            aggregate["coverage"] = len(recommended_union) / test_interactions.n_items
        else:
            aggregate["coverage"] = 0.0

    if "diversity" in requested:
        user_sets = (
            [set(items[:k]) for items in recs_by_user.values() if items] if test_users else []
        )
        if len(user_sets) >= 2:
            similarities: list[float] = []
            for i in range(len(user_sets)):
                for j in range(i + 1, len(user_sets)):
                    a, b = user_sets[i], user_sets[j]
                    denom = math.sqrt(len(a)) * math.sqrt(len(b))
                    similarities.append(len(a & b) / denom if denom > 0 else 0.0)
            aggregate["diversity"] = 1.0 - (sum(similarities) / len(similarities))
        else:
            aggregate["diversity"] = 0.0

    if "novelty" in requested:
        n_users_total = test_interactions.n_users
        novelty_scores: list[float] = []
        if test_users and n_users_total > 0:
            for items in recs_by_user.values():
                for item_id in items[:k]:
                    col = test_interactions.item_index.get(item_id)
                    if col is None:
                        popularity = 0.0
                    else:
                        popularity = test_interactions.matrix.getcol(col).nnz / n_users_total
                    popularity = max(popularity, 1.0 / n_users_total)
                    novelty_scores.append(-math.log2(popularity))
        aggregate["novelty"] = sum(novelty_scores) / len(novelty_scores) if novelty_scores else 0.0

    return EvalResult(algorithm=recommender.algorithm, k=k, per_user=per_user, aggregate=aggregate)


@public_op(name="ef.recommend.compare")
def compare(
    test_interactions: InteractionMatrix,
    *,
    recommenders: list[FittedRecommender],
    k: int = 10,
) -> pd.DataFrame:
    """Evaluate multiple fitted recommenders on the same held-out test set and rank them.

    The recommend-family analog to ``ef.ml.compare_models`` (Epic 15, Story 12). Unlike
    ``compare_models``, every candidate here arrives already fitted -- ``compare`` does not fit
    anything except the automatic popularity baseline described below. Calls the existing
    :func:`evaluate` wrapper once per recommender (all 10 metrics -- see ``evaluate``'s
    ``_VALID_EVAL_METRICS``), and returns a tidy comparison DataFrame: one row per recommender,
    with an ``algorithm`` column, an ``is_baseline`` bool column, and one column per evaluation
    metric (``mean_precision_at_k``, ``mean_recall_at_k``, ``mean_ndcg_at_k``, ``hit_rate``,
    ``map_at_k``, ``coverage``, ``diversity``, ``novelty``, ``mean_mrr_at_k``, ``mean_auc_at_k``).
    Sorted by ``mean_ndcg_at_k``
    descending -- the "baseline-to-beat" framing: the strongest recommender by ranking quality is
    always first.

    The baseline-to-beat framing: if none of ``recommenders`` has ``algorithm == "popularity"``,
    an extra popularity-baseline recommender is automatically fit (via the existing :func:`fit`
    wrapper) and appended as one more row with ``is_baseline=True``; every explicitly-supplied
    recommender gets ``is_baseline=False`` even if one of them happens to already be a popularity
    recommender. NOTE: the auto-fit baseline is trained on ``test_interactions`` itself (this
    function receives no separate training-interactions argument), so it is a rough contextual
    reference point, not trained on the same data as the other recommenders -- document this
    plainly so a caller isn't misled into thinking it's an apples-to-apples baseline.

    Raises :class:`~emergentflow.recommend.errors.InvalidRecommenderParamsError` if
    ``recommenders`` is empty. Never mutates ``test_interactions`` or ``recommenders``.
    """
    if not recommenders:
        raise InvalidRecommenderParamsError(
            f"compare requires at least 1 recommender; got {len(recommenders)}."
        )

    to_compare = list(recommenders)
    auto_baseline_index: int | None = None
    if not any(rec.algorithm == "popularity" for rec in to_compare):
        baseline = fit(test_interactions, algorithm="popularity", params={})
        auto_baseline_index = len(to_compare)
        to_compare = [*to_compare, baseline]

    rows: list[dict[str, Any]] = []
    for i, rec in enumerate(to_compare):
        result = evaluate(rec, test_interactions, k=k)
        row: dict[str, Any] = {
            "algorithm": rec.algorithm,
            "is_baseline": i == auto_baseline_index,
        }
        row.update(result.aggregate)
        rows.append(row)

    comparison = pd.DataFrame(rows)
    if "mean_ndcg_at_k" in comparison.columns:
        comparison = comparison.sort_values(
            "mean_ndcg_at_k", ascending=False, kind="stable"
        ).reset_index(drop=True)
    return comparison


_VALID_BLEND_STRATEGIES = frozenset({"weighted_sum", "rank_fusion", "cascade"})


@public_op(name="ef.recommend.hybrid_weighted")
def hybrid_weighted(
    recommenders: list[FittedRecommender],
    *,
    weights: list[float] | None = None,
    n: int = 10,
    blend_strategy: str = "weighted_sum",
    user_ids: list[Any] | None = None,
    exclude_known: bool = True,
) -> RecommendationResult:
    """Blend two or more fitted recommenders' recommendations into one ranked list.

    A composition layer (Epic 15, Story 9), not a new algorithm family -- each input
    recommender is scored by calling the existing `recommend()` wrapper (the same seam
    every other recommend node routes through), so ADR-0002 equivalence for each input
    recommender is untouched; this function only combines their already-produced outputs.

    ``weights``: one weight per recommender, in the same order as `recommenders`.
    `None` (the default) means equal weighting. ``blend_strategy``:
      - "weighted_sum": each item's per-recommender score is multiplied by that
        recommender's weight and summed across recommenders; ranked descending.
      - "rank_fusion": each item's per-recommender RANK (not raw score, which may not
        be comparable across algorithms with different scales) contributes
        `weight / (60 + rank)` (reciprocal rank fusion, a standard IR technique);
        summed across recommenders and ranked descending.
      - "cascade": recommenders are tried in descending-weight priority order; each
        recommender's ranked items are appended in order, skipping items already
        added by a higher-priority recommender, until `n` items are collected.

    Raises `InvalidRecommenderParamsError` if `recommenders` has fewer than 2 entries,
    `weights` (when given) doesn't have one entry per recommender, or `blend_strategy`
    is not one of the three values above. Never mutates `recommenders`.
    """
    if len(recommenders) < 2:
        raise InvalidRecommenderParamsError(
            f"hybrid_weighted requires at least 2 recommenders; got {len(recommenders)}."
        )
    if weights is None:
        weights = [1.0] * len(recommenders)
    if len(weights) != len(recommenders):
        raise InvalidRecommenderParamsError(
            f"weights must have one entry per recommender; got {len(weights)} "
            f"weight(s) for {len(recommenders)} recommender(s)."
        )
    if blend_strategy not in _VALID_BLEND_STRATEGIES:
        raise InvalidRecommenderParamsError(
            f"unknown blend_strategy {blend_strategy!r}; expected one of "
            f"{sorted(_VALID_BLEND_STRATEGIES)!r}."
        )

    # Over-fetch more candidates per recommender than the final `n` so blending has
    # enough overlap to work with; candidates unique to one recommender are still
    # eligible, just at a disadvantage under weighted_sum/rank_fusion.
    n_candidates = max(n * 5, 50)
    per_recommender_results = [
        recommend(rec, user_ids=user_ids, n=n_candidates, exclude_known=exclude_known)
        for rec in recommenders
    ]

    target_user_ids = user_ids
    if target_user_ids is None:
        seen_users: list[Any] = []
        seen_users_set: set[Any] = set()
        for result in per_recommender_results:
            for uid in result.recommendations["user_id"].tolist():
                if uid not in seen_users_set:
                    seen_users_set.add(uid)
                    seen_users.append(uid)
        target_user_ids = seen_users

    rows: list[dict[str, Any]] = []
    for uid in target_user_ids:
        user_frames = [
            result.recommendations[result.recommendations["user_id"] == uid]
            for result in per_recommender_results
        ]

        ranked: list[tuple[Any, float]]
        if blend_strategy == "cascade":
            priority = sorted(range(len(recommenders)), key=lambda i: -weights[i])
            seen_items: set[Any] = set()
            ranked = []
            for i in priority:
                for item_id, score in zip(
                    user_frames[i]["item_id"], user_frames[i]["score"], strict=True
                ):
                    if item_id in seen_items:
                        continue
                    seen_items.add(item_id)
                    ranked.append((item_id, float(score)))
                if len(ranked) >= n:
                    break
        else:
            item_scores: dict[Any, float] = {}
            for weight, frame in zip(weights, user_frames, strict=True):
                if blend_strategy == "weighted_sum":
                    for item_id, score in zip(frame["item_id"], frame["score"], strict=True):
                        item_scores[item_id] = item_scores.get(item_id, 0.0) + weight * float(score)
                else:  # rank_fusion
                    for item_id, rank in zip(frame["item_id"], frame["rank"], strict=True):
                        item_scores[item_id] = item_scores.get(item_id, 0.0) + weight / (
                            60 + int(rank)
                        )
            ranked = sorted(item_scores.items(), key=lambda kv: -kv[1])

        for rank, (item_id, score) in enumerate(ranked[:n], start=1):
            rows.append({"user_id": uid, "item_id": item_id, "rank": rank, "score": float(score)})

    return RecommendationResult(recommendations=pd.DataFrame(rows))


@public_op(name="ef.recommend.hybrid_switching")
def hybrid_switching(
    recommenders: list[FittedRecommender],
    interactions: InteractionMatrix,
    *,
    cold_start_threshold: int,
    n: int = 10,
    user_ids: list[Any] | None = None,
    exclude_known: bool = True,
) -> RecommendationResult:
    """Route each user to one of two fitted recommenders by their known-interaction
    count (Epic 15, Story 9): a composition layer, not a new algorithm family,
    addressing the cold-start problem directly.

    `recommenders` must have EXACTLY 2 entries: `recommenders[0]` is used for
    cold-start users (fewer than `cold_start_threshold` known interactions in
    `interactions`, including users entirely absent from it), `recommenders[1]` for
    warm users (`cold_start_threshold` or more known interactions). `interactions`
    is only used to look up each user's known-interaction count -- it is never
    refit here. `user_ids=None` means every user in `interactions`.

    Raises `InvalidRecommenderParamsError` if `recommenders` does not have exactly
    2 entries. Never mutates `recommenders` or `interactions`.
    """
    if len(recommenders) != 2:
        raise InvalidRecommenderParamsError(
            "hybrid_switching requires exactly 2 recommenders "
            f"([cold_start_recommender, warm_recommender]); got {len(recommenders)}."
        )
    cold_recommender, warm_recommender = recommenders

    target_user_ids = user_ids if user_ids is not None else list(interactions.user_index.keys())

    cold_users: list[Any] = []
    warm_users: list[Any] = []
    for uid in target_user_ids:
        if uid in interactions.user_index:
            count = interactions.matrix[interactions.user_index[uid]].nnz
        else:
            count = 0
        if count < cold_start_threshold:
            cold_users.append(uid)
        else:
            warm_users.append(uid)

    rows: list[dict[str, Any]] = []
    if cold_users:
        cold_result = recommend(
            cold_recommender, user_ids=cold_users, n=n, exclude_known=exclude_known
        )
        rows.extend(cold_result.recommendations.to_dict("records"))
    if warm_users:
        warm_result = recommend(
            warm_recommender, user_ids=warm_users, n=n, exclude_known=exclude_known
        )
        rows.extend(warm_result.recommendations.to_dict("records"))

    if not rows:
        combined = pd.DataFrame(columns=["user_id", "item_id", "rank", "score"])
    else:
        # Reorder to match target_user_ids (cold users were appended before warm
        # users above; this restores the caller's requested/observed user order).
        order = {uid: i for i, uid in enumerate(target_user_ids)}
        combined = pd.DataFrame(rows)
        combined["__order__"] = combined["user_id"].map(order)
        combined = (
            combined.sort_values(["__order__", "rank"], kind="stable")
            .drop(columns="__order__")
            .reset_index(drop=True)
        )

    return RecommendationResult(recommendations=combined)


@public_op(name="ef.recommend.prepare_interactions")
def prepare_interactions(
    df: pd.DataFrame,
    *,
    user_col: str,
    item_col: str,
    value_col: str | None = None,
    implicit: bool = True,
    agg: str = "sum",
    min_user_interactions: int = 0,
    min_item_interactions: int = 0,
    cold_start_mode: str = "warn-and-skip",
) -> InteractionMatrix:
    """Prepare a tidy events/ratings DataFrame into a validated, sparse InteractionMatrix.

    The single seam every ``prepare_interactions`` node routes through (Epic 15, Story 3),
    delegating to the shared ``_prepare_interactions`` validation gate (column existence,
    duplicate-pair aggregation, minimum-interaction filtering, cold-start handling). Because both
    ``compile_to_code``'s emitted code and ``execute`` reach this validation only through this
    function, ADR-0002 equivalence holds by construction. Never mutates ``df``.
    """
    return _prepare_interactions(
        df,
        user_col=user_col,
        item_col=item_col,
        value_col=value_col,
        implicit=implicit,
        agg=agg,
        min_user_interactions=min_user_interactions,
        min_item_interactions=min_item_interactions,
        cold_start_mode=cold_start_mode,
    )


@public_op(name="ef.recommend.temporal_split")
def temporal_split(
    df: pd.DataFrame,
    *,
    user_col: str,
    item_col: str,
    value_col: str | None = None,
    timestamp_col: str,
    test_ratio: float = 0.2,
    implicit: bool = True,
) -> tuple[InteractionMatrix, InteractionMatrix]:
    """Split events into (train, test) InteractionMatrix pairs by per-user recency.

    The standard recommender evaluation split (Epic 15, Story 3): each user's last
    ``test_ratio`` fraction of interactions (ordered by ``timestamp_col``) goes to test, the
    rest to train. Deterministic (no randomness involved). Raises
    :class:`~emergentflow.recommend.errors.InvalidRecommenderParamsError` if ``timestamp_col`` is
    not a column of *df* or ``test_ratio`` is not in ``(0, 1)``. Never mutates *df*. Each half is
    built via the shared ``_prepare_interactions`` gate with no minimum-interaction filtering
    (``cold_start_mode="include"``) -- splitting itself never drops users/items.
    """
    if timestamp_col not in df.columns:
        raise InvalidRecommenderParamsError(
            f"column {timestamp_col!r} is not in the input frame; "
            f"available columns: {sorted(df.columns)!r}."
        )
    if not 0.0 < test_ratio < 1.0:
        raise InvalidRecommenderParamsError(f"test_ratio must be in (0, 1); got {test_ratio!r}.")

    train_parts = []
    test_parts = []
    for _, group in df.groupby(user_col, sort=False):
        ordered = group.sort_values(timestamp_col, kind="stable")
        n_test = round(len(ordered) * test_ratio)
        if n_test > 0:
            test_parts.append(ordered.iloc[-n_test:])
            train_parts.append(ordered.iloc[:-n_test])
        else:
            train_parts.append(ordered)

    train_df = pd.concat(train_parts, ignore_index=True) if train_parts else df.iloc[0:0]
    test_df = pd.concat(test_parts, ignore_index=True) if test_parts else df.iloc[0:0]

    train = _prepare_interactions(
        train_df,
        user_col=user_col,
        item_col=item_col,
        value_col=value_col,
        implicit=implicit,
        cold_start_mode="include",
    )
    test = _prepare_interactions(
        test_df,
        user_col=user_col,
        item_col=item_col,
        value_col=value_col,
        implicit=implicit,
        cold_start_mode="include",
    )
    return train, test


@public_op(name="ef.recommend.random_split")
def random_split(
    df: pd.DataFrame,
    *,
    user_col: str,
    item_col: str,
    value_col: str | None = None,
    test_ratio: float = 0.2,
    implicit: bool = True,
    seed: int = 0,
) -> tuple[InteractionMatrix, InteractionMatrix]:
    """Split events into (train, test) InteractionMatrix pairs by uniform random row sampling.

    A simpler alternative to :func:`temporal_split` when no timestamp column is available.
    Deterministic given ``seed``. Raises
    :class:`~emergentflow.recommend.errors.InvalidRecommenderParamsError` if ``test_ratio`` is
    not in ``(0, 1)``. Never mutates *df*. Each half is built via the shared
    ``_prepare_interactions`` gate with no minimum-interaction filtering
    (``cold_start_mode="include"``).
    """
    if not 0.0 < test_ratio < 1.0:
        raise InvalidRecommenderParamsError(f"test_ratio must be in (0, 1); got {test_ratio!r}.")

    rng = np.random.default_rng(seed)
    shuffled_index = rng.permutation(len(df))
    n_test = round(len(df) * test_ratio)
    test_positions = shuffled_index[:n_test]
    train_positions = shuffled_index[n_test:]

    train_df = df.iloc[train_positions].reset_index(drop=True)
    test_df = df.iloc[test_positions].reset_index(drop=True)

    train = _prepare_interactions(
        train_df,
        user_col=user_col,
        item_col=item_col,
        value_col=value_col,
        implicit=implicit,
        cold_start_mode="include",
    )
    test = _prepare_interactions(
        test_df,
        user_col=user_col,
        item_col=item_col,
        value_col=value_col,
        implicit=implicit,
        cold_start_mode="include",
    )
    return train, test


@public_op(name="ef.recommend.save_model")
def save_model(
    model: FittedRecommender,
    path: str | Path,
) -> ArtifactRef:
    """Serialize *model* to *path* using joblib and return an ArtifactRef.

    Writes two files:
      - ``<path>`` — the pickled model (via joblib).
      - ``<path>.meta.json`` — a sidecar with sdk version, algorithm,
        algorithm family, user/item counts, and fit stats.

    The sidecar enables ``load_model`` to version-check before deserializing.
    Loading a pickle is code execution (same trust model as
    ``ExecutionCache`` / ``ArtifactStore``).

    Parameters
    ----------
    model:
        The fitted recommender to save.
    path:
        Destination file path (e.g. ``"models/popularity_v3.joblib"``).
        Parent directories are created if missing.

    Returns
    -------
    ArtifactRef
        A reference to the saved artifact.

    Raises
    ------
    ModelPersistenceError
        If *model* is not a :class:`FittedRecommender`.
    """
    if not isinstance(model, FittedRecommender):
        raise ModelPersistenceError(
            f"save_model expects a FittedRecommender; got {type(model).__name__}."
        )

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    import sklearn

    joblib.dump(model, path)

    meta = {
        "sdk_version": __version__,
        "sklearn_version": sklearn.__version__,
        "algorithm": model.algorithm,
        "algorithm_family": model.algorithm_family,
        "n_users": model.n_users,
        "n_items": model.n_items,
        "fit_stats": model.fit_stats,
        "timestamp": time.time(),
    }
    meta_path = path.with_suffix(path.suffix + ".meta.json")
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    return ArtifactRef(uri=str(path), media_type="application/octet-stream")


@public_op(name="ef.recommend.load_model")
def load_model(
    ref_or_path: str | Path | ArtifactRef,
) -> FittedRecommender:
    """Deserialize a saved recommender from *ref_or_path*.

    Validates the sidecar's sklearn version against the current environment
    and raises :class:`ModelPersistenceError` on mismatch with a clear
    explanatory message.

    Parameters
    ----------
    ref_or_path:
        An ``ArtifactRef``, a file path string, or a ``Path``.

    Returns
    -------
    FittedRecommender
        The deserialized recommender.

    Raises
    ------
    ModelPersistenceError
        If the sidecar's sklearn version does not match the current
        environment's sklearn version, or if the loaded object is not a
        FittedRecommender.
    FileNotFoundError
        If the model file does not exist.
    """
    import sklearn

    path = Path(ref_or_path.uri) if isinstance(ref_or_path, ArtifactRef) else Path(ref_or_path)

    if not path.is_file():
        raise FileNotFoundError(f"Model file not found: {path}")

    meta_path = path.with_suffix(path.suffix + ".meta.json")
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        saved_sklearn_version = meta.get("sklearn_version")
        current_sklearn_version = sklearn.__version__
        if saved_sklearn_version and saved_sklearn_version != current_sklearn_version:
            raise ModelPersistenceError(
                f"Model was saved with sklearn v{saved_sklearn_version} but the current "
                f"environment has sklearn v{current_sklearn_version}. "
                f"Install the matching version: `pip install scikit-learn=={saved_sklearn_version}`"
            )

    model = joblib.load(path)
    if not isinstance(model, FittedRecommender):
        raise ModelPersistenceError(
            f"Loaded object is not a FittedRecommender; got {type(model).__name__}."
        )
    return model


from emergentflow.recommend import catalog  # noqa: E402, F401
