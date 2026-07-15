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
from typing import Any

import numpy as np
import pandas as pd

from emergentflow.api import public_op
from emergentflow.recommend.errors import (
    InvalidRecommenderParamsError,
    MissingOptionalDependencyError,
)
from emergentflow.recommend.interactions import InteractionMatrix, _prepare_interactions
from emergentflow.recommend.models import FittedRecommender, RecommendationResult
from emergentflow.recommend.registry import RecommenderSpec, get_recommender_spec

__all__ = [
    "fit",
    "fit_two_tower",
    "hybrid_switching",
    "hybrid_weighted",
    "prepare_interactions",
    "random_split",
    "recommend",
    "similar_items",
    "temporal_split",
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
    return spec.fitter(interactions, item_features, resolved_params)


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


from emergentflow.recommend import catalog  # noqa: E402, F401
