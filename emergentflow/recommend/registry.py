"""
emergentflow.recommend.registry
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Algorithm allow-list registry for the Epic 15 recommender-systems families.

Maps a curated ``algorithm`` key (e.g. ``"popularity"``) to a :class:`RecommenderSpec` describing
its archetype family, its required/optional structured params, whether it needs an optional
dependency extra, its cold-start handling, and -- crucially -- its own ``fitter``/``recommend_fn``/
``similar_items_fn`` callables. Recommenders share no common library interface across archetypes
(baseline heuristics, content-based similarity, collaborative filtering, and deep models are all
implemented differently), so each entry brings its own logic for all three ``ef.recommend.*``
verbs; uniformity comes from the shared ``FittedRecommender``/``RecommendationResult``
representations and the shared ``ef.recommend.fit``/``recommend``/``similar_items`` routing, not
from a single generic adapter (mirroring ``emergentflow.stats.registry``, one level deeper because
recommenders need three routed verbs instead of one).

The curated catalog of actual algorithms (popularity, SVD, ALS, ...) is registered as data by a
future ``emergentflow.recommend.catalog`` module (Epic 15, Story 4 onward) imported for its side
effect -- mirroring ``emergentflow.stats.catalog`` / ``emergentflow.ml.catalog``. No algorithms are
registered by this module itself.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from emergentflow.recommend.errors import UnknownAlgorithmError

if TYPE_CHECKING:
    import pandas as pd

    from emergentflow.recommend.interactions import InteractionMatrix
    from emergentflow.recommend.models import (
        FittedRecommender,
        RecommendationResult,
        SequenceDataset,
    )

__all__ = [
    "RecommenderFamily",
    "RecommenderParamSpec",
    "RecommenderSpec",
    "register_recommender",
    "get_recommender_spec",
    "known_recommender_keys",
    "keys_for_family",
]

#: The five fixed recommender archetypes (see docs/adr/0021-recommender-systems-architecture.md).
RecommenderFamily = Literal["baseline", "content", "collaborative", "deep", "sequential"]

#: A fitter takes the interaction matrix, an optional item-features frame (used only by the
#: content-based family; other families receive ``None``), and an already-validated params dict,
#: and returns a FittedRecommender. Validation is done upstream by the ``ef.recommend.fit``
#: wrapper, so a fitter may assume its params are well-formed for its algorithm.
Fitter = Callable[["InteractionMatrix", "pd.DataFrame | None", dict[str, Any]], "FittedRecommender"]

#: A recommend_fn takes the fitted recommender, an optional list of user ids (None means "all
#: users"), the number of recommendations per user, and whether to exclude items already seen in
#: the training interactions, and returns a RecommendationResult.
RecommendFn = Callable[["FittedRecommender", "list[Any] | None", int, bool], "RecommendationResult"]

#: A similar_items_fn takes the fitted recommender, a list of item ids, and the number of similar
#: items per item, and returns a RecommendationResult. Not every algorithm supports item-item
#: similarity (see RecommenderSpec.similar_items_fn).
SimilarItemsFn = Callable[["FittedRecommender", "list[Any]", int], "RecommendationResult"]

#: A sequence_fitter takes a SequenceDataset and an already-validated params dict, and returns
#: a FittedRecommender. Used by session-based (sequential) recommender algorithms, which consume
#: ordered per-session item sequences rather than a user-item interaction matrix -- see
#: ``RecommendSpec.sequence_fitter``.
SequenceFitter = Callable[["SequenceDataset", dict[str, Any]], "FittedRecommender"]


@dataclass(frozen=True)
class RecommenderParamSpec:
    """Curated UI/validation metadata for one recommender algorithm param.

    Additive to the ``required_params``/``optional_params`` name tuples (which stay the
    authoritative allow-list ``ef.recommend.fit`` validates against): this carries the
    type/default/help/choices the Epic 4 config UI renders. ``required`` mirrors whether the
    param name appears in ``RecommenderSpec.required_params``.
    """

    name: str
    type: str  # "int" | "float" | "str" | "bool" | "list" | "any"
    default: Any = None
    help: str = ""
    choices: tuple[str, ...] | None = None
    required: bool = False


@dataclass(frozen=True)
class RecommenderSpec:
    """One curated allow-list entry mapping an algorithm key to how to fit/recommend/similar it.

    Attributes
    ----------
    key: curated algorithm identifier used as the ``algorithm`` param (e.g. ``"popularity"``).
    family: which of the four fixed archetypes this algorithm belongs to.
    fitter: the per-algorithm callable that fits the model and returns a ``FittedRecommender``
        (heterogeneity lives here; see module docstring).
    recommend_fn: the per-algorithm callable that generates top-N recommendations for users.
    similar_items_fn: the per-algorithm callable that finds similar items, or ``None`` if this
        algorithm does not support item-item similarity (e.g. most baselines).
    sequence_fitter: the per-algorithm callable that fits a session-based (sequential)
        recommender from a ``SequenceDataset`` and returns a ``FittedRecommender``, or ``None``
        for non-sequential algorithms (which are fit via ``fitter`` instead).
    required_params: structured-param keys that MUST be present (validated by the ``ef.recommend
        .fit`` wrapper).
    optional_params: additional structured-param keys this algorithm accepts.
    param_metadata: curated per-param type/default/help/choices metadata (one entry per name in
        ``required_params + optional_params``), additive to those name tuples -- see
        :class:`RecommenderParamSpec`. Left ``()`` for entries registered before this metadata
        existed.
    requires_extra: pip extra target (e.g. ``"emergentflow[recommend]"``) needed to run this
        algorithm, or ``None`` for base-install algorithms. ``ef.recommend.fit`` raises
        ``MissingOptionalDependencyError`` when it is set but the extra is absent.
    handles_cold_start_users: whether this algorithm can produce recommendations for a user with
        no interaction history (content-based/hybrid: yes; pure collaborative filtering: no).
    handles_cold_start_items: whether this algorithm can recommend an item with no interaction
        history (content-based: yes; pure collaborative filtering: no).
    description: curated one-line summary for the generated catalog (a future story's generator).
    """

    key: str
    family: RecommenderFamily
    recommend_fn: RecommendFn
    fitter: Fitter | None = None
    similar_items_fn: SimilarItemsFn | None = None
    sequence_fitter: SequenceFitter | None = None
    required_params: tuple[str, ...] = ()
    optional_params: tuple[str, ...] = ()
    param_metadata: tuple[RecommenderParamSpec, ...] = ()
    requires_extra: str | None = None
    handles_cold_start_users: bool = False
    handles_cold_start_items: bool = False
    description: str = ""


_REGISTRY: dict[str, RecommenderSpec] = {}


def register_recommender(spec: RecommenderSpec) -> RecommenderSpec:
    """Register *spec* under ``spec.key``; raise ``ValueError`` on a duplicate key."""
    if spec.key in _REGISTRY:
        raise ValueError(f"algorithm key {spec.key!r} is already registered.")
    _REGISTRY[spec.key] = spec
    return spec


def get_recommender_spec(key: str) -> RecommenderSpec:
    """Look up *key*; raise :class:`UnknownAlgorithmError` if not curated."""
    try:
        return _REGISTRY[key]
    except KeyError:
        raise UnknownAlgorithmError(
            f"unknown algorithm {key!r}; expected one of {known_recommender_keys()!r}."
        ) from None


def known_recommender_keys() -> list[str]:
    """Every registered algorithm key, sorted for deterministic output."""
    return sorted(_REGISTRY)


def keys_for_family(family: RecommenderFamily) -> list[str]:
    """Every registered algorithm key whose family is *family*, sorted."""
    return sorted(k for k, spec in _REGISTRY.items() if spec.family == family)
