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
