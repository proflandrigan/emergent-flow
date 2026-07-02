"""
emergentflow.ml.registry
~~~~~~~~~~~~~~~~~~~~~~~~
Estimator allow-list registry (Epic 8, Story 2 / ADR 0016).

Maps a curated ``estimator_key`` (e.g. ``"RandomForestClassifier"``, ``"KMeans"``) to an
:class:`EstimatorSpec` describing the sklearn class to fit, its archetype (which of the
three fixed adapter shapes it uses), its accepted constructor kwargs (with defaults), and
(optionally) an inspectable-summary builder.

This module defines the registry *mechanism* only. The actual curated catalog of
estimator entries is registered as data by importing ``emergentflow.ml.catalog`` for its
side effect, mirroring how ``emergentflow.types.catalog`` registers type tokens into
``emergentflow.types.registry``.

The catalog is pinned to this curated allow-list, never to ``sklearn.utils.all_estimators()``
at runtime (ADR 0016, decision 5) — so the node set stays deterministic and version-stable.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from emergentflow.ml.errors import UnknownEstimatorError

__all__ = [
    "Archetype",
    "KwargSpec",
    "EstimatorSpec",
    "register_estimator",
    "get_estimator_spec",
    "known_estimator_keys",
    "keys_for_archetype",
]

#: The three fixed adapter shapes locked by ADR 0016 subsection 3. ("apply" is not an
#: archetype an estimator is *registered under* -- it is the shared consumer side, backed
#: by ``ef.ml.apply_estimator`` for every archetype below.)
Archetype = Literal["fit", "fit_transform", "cluster_detect"]


@dataclass(frozen=True)
class KwargSpec:
    """One curated, allow-listed constructor kwarg for an estimator.

    ``default`` is the value used to construct the estimator when the caller does not
    override it via ``fit_estimator(..., params={...})``.

    ``choices``, when set, curates a JSON-native string enum for a kwarg whose real
    constructor value isn't JSON-native (e.g. ``SelectKBest.score_func``, which sklearn
    requires to be a callable). ``default`` and any caller-supplied override must then be one
    of ``choices``' keys; the adapter resolves the string to ``choices[value]`` before
    constructing the estimator. Left ``None`` for kwargs whose curated default is already the
    literal constructor value (the common case).
    """

    default: Any
    help: str = ""
    choices: dict[str, Any] | None = None


@dataclass(frozen=True)
class EstimatorSpec:
    """A single curated allow-list entry mapping an estimator key to how to fit it.

    Attributes
    ----------
    key: the curated estimator identifier used as the ``estimator`` param value on
        archetype nodes (e.g. ``"RandomForestClassifier"``).
    import_path: dotted import path of the sklearn class (e.g.
        ``"sklearn.ensemble.RandomForestClassifier"``), recorded for documentation /
        future catalog generation (Story 7); not used to import at registration time.
    sklearn_class: the live sklearn class itself, used to construct instances.
    archetype: which of the three fixed adapter shapes this estimator uses.
    task: ``"classification"`` | ``"regression"`` for ``archetype="fit"`` estimators;
        ``None`` for unsupervised archetypes.
    description: a curated, hand-written one-line summary of the estimator (Epic 8, Story 7).
        Takes priority over the raw sklearn docstring first line in the generated catalog
        entry (see ``emergentflow.ml.generator``). Left ``""`` (the default) for entries that
        have not yet been curated, in which case the generator falls back to the docstring.
    accepted_kwargs: curated allow-list of constructor kwargs -> :class:`KwargSpec`.
        Keys not present here are rejected by the adapter as unknown params.
    summary_builder: optional inspectable-summary builder for this estimator's family;
        left ``None`` for entries registered before Story 3 builds per-family summaries.
    """

    key: str
    import_path: str
    sklearn_class: type
    archetype: Archetype
    task: str | None = None
    description: str = ""
    accepted_kwargs: dict[str, KwargSpec] = field(default_factory=dict)
    summary_builder: Callable[[Any], dict[str, Any]] | None = None


_REGISTRY: dict[str, EstimatorSpec] = {}


def register_estimator(spec: EstimatorSpec) -> EstimatorSpec:
    """Register *spec* under ``spec.key`` in the module-level allow-list registry.

    Raises ``ValueError`` if ``spec.key`` is already registered (each key is
    registered exactly once, at import time, by ``emergentflow.ml.catalog``).
    Returns *spec* unchanged so it can be used as a decorator-style call site.
    """
    if spec.key in _REGISTRY:
        raise ValueError(f"estimator key {spec.key!r} is already registered.")
    _REGISTRY[spec.key] = spec
    return spec


def get_estimator_spec(key: str) -> EstimatorSpec:
    """Look up *key* in the allow-list registry.

    Raises :class:`~emergentflow.ml.errors.UnknownEstimatorError` if *key* is not a
    curated, registered estimator.
    """
    try:
        return _REGISTRY[key]
    except KeyError:
        raise UnknownEstimatorError(
            f"unknown estimator {key!r}; expected one of {known_estimator_keys()!r}."
        ) from None


def known_estimator_keys() -> list[str]:
    """Return every registered estimator key, sorted for deterministic output."""
    return sorted(_REGISTRY)


def keys_for_archetype(archetype: Archetype) -> list[str]:
    """Every registered estimator key whose archetype is *archetype*, sorted.

    Shared by every archetype node's ``estimator`` dropdown (``choices=`` hint), so the
    fit/fit_transform/cluster_detect filter logic has exactly one implementation.
    """
    return sorted(k for k, spec in _REGISTRY.items() if spec.archetype == archetype)
