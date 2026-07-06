"""
emergentflow.stats.registry
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Model allow-list registry for the Epic 12 statistics families.

Maps a curated ``model`` key (e.g. ``"OLS"``) to a :class:`ModelSpec` describing its archetype,
its required/optional structured-spec fields, whether it needs an optional dependency extra, and
-- crucially -- its own ``fitter`` callable. Unlike the sklearn estimator adapter (one generic
constructor for ~200 estimators), statistical models are heterogeneous, so each entry brings its
own fit logic; uniformity comes from the shared ``FittedStatsModel`` representation and the shared
``ef.stats.fit_model`` routing, not from a single generic constructor (see the stats/viz design
note).

The curated catalog itself is registered as data by importing ``emergentflow.stats.catalog`` for
its side effect, mirroring ``emergentflow.ml.catalog`` / ``emergentflow.types.catalog``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from emergentflow.stats.errors import UnknownModelError

if TYPE_CHECKING:
    import pandas as pd

    from emergentflow.stats.models import FittedStatsModel

__all__ = [
    "ModelArchetype",
    "ModelSpec",
    "register_model",
    "get_model_spec",
    "known_model_keys",
    "keys_for_archetype",
]

#: The three fixed model archetypes (see docs/stats-viz-design.md, Decision 2).
ModelArchetype = Literal["fit_model", "diagnostic", "bayesian_fit"]

#: A fitter takes a DataFrame and an already-validated structured spec dict and returns a
#: FittedStatsModel. Validation is done upstream by ``_prepare_model_spec`` (Story 3), so a
#: fitter may assume its spec is well-formed for its family.
Fitter = Callable[["pd.DataFrame", dict[str, Any]], "FittedStatsModel"]


@dataclass(frozen=True)
class ModelSpec:
    """One curated allow-list entry mapping a model key to how to fit + validate it.

    Attributes
    ----------
    key: curated model identifier used as the ``model`` param (e.g. ``"OLS"``).
    archetype: which fixed archetype this model uses.
    fitter: the per-family callable that assembles the backend call and returns a
        ``FittedStatsModel`` (heterogeneity lives here; see module docstring).
    required_spec_fields: structured-spec keys that MUST be present (validated by
        ``_prepare_model_spec``, Story 3).
    optional_spec_fields: additional structured-spec keys this model accepts.
    requires_extra: pip extra target (e.g. ``"emergentflow[bayes]"``) needed to run this model,
        or ``None`` for base-install models. ``fit_model`` raises
        ``MissingOptionalDependencyError`` when it is set but the extra is absent.
    description: curated one-line summary for the generated catalog (Story 8's generator).
    """

    key: str
    archetype: ModelArchetype
    fitter: Fitter
    required_spec_fields: tuple[str, ...] = ()
    optional_spec_fields: tuple[str, ...] = ()
    requires_extra: str | None = None
    description: str = ""


_REGISTRY: dict[str, ModelSpec] = {}


def register_model(spec: ModelSpec) -> ModelSpec:
    """Register *spec* under ``spec.key``; raise ``ValueError`` on a duplicate key."""
    if spec.key in _REGISTRY:
        raise ValueError(f"model key {spec.key!r} is already registered.")
    _REGISTRY[spec.key] = spec
    return spec


def get_model_spec(key: str) -> ModelSpec:
    """Look up *key*; raise :class:`UnknownModelError` if not a curated, registered model."""
    try:
        return _REGISTRY[key]
    except KeyError:
        raise UnknownModelError(
            f"unknown model {key!r}; expected one of {known_model_keys()!r}."
        ) from None


def known_model_keys() -> list[str]:
    """Every registered model key, sorted for deterministic output."""
    return sorted(_REGISTRY)


def keys_for_archetype(archetype: ModelArchetype) -> list[str]:
    """Every registered model key whose archetype is *archetype*, sorted."""
    return sorted(k for k, spec in _REGISTRY.items() if spec.archetype == archetype)
