"""
emergentflow.causal.registry
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Effect-estimator allow-list registry for the causal-inference family (issue #164 Gap 1).

Maps a curated ``method`` key (e.g. ``"aipw"``) to an :class:`EstimatorSpec` describing
which public op it belongs to, whether it needs an optional dependency extra, and -- most
importantly -- a ``fn`` that computes the tidy result frame given an already-validated set
of inputs. Like the stats allow-list (``emergentflow.stats.registry``), the estimators are
heterogeneous, so each entry carries its own computation; uniformity comes from the thin
public ops (``ef.causal.estimate_effect`` dispatches on ``method`` through this registry).

The curated catalog is registered as data by importing ``emergentflow.causal.catalog`` for
its side effect (mirroring ``emergentflow.ml.catalog`` / ``emergentflow.stats.catalog``).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from emergentflow.causal.errors import UnknownMethodError

#: The two public ops that dispatch through the estimator registry.
CausalArchetype = Literal["estimate_effect", "did"]


@dataclass(frozen=True)
class EstimatorSpec:
    """One curated allow-list entry mapping a method key to how it computes a result.

    Attributes
    ----------
    key: curated method identifier (e.g. ``"aipw"``).
    archetype: which public op this estimator belongs to.
    fn: the callable that computes the tidy result frame.
    requires_extra: pip extra target (e.g. ``"emergentflow[explain]"``) needed to run this
        estimator, or ``None`` for base-install estimators.
    description: curated one-line summary for the generated catalog.
    """

    key: str
    archetype: CausalArchetype
    fn: Callable[..., Any]
    requires_extra: str | None = None
    description: str = ""


_REGISTRY: dict[str, EstimatorSpec] = {}


def register_estimator(spec: EstimatorSpec) -> EstimatorSpec:
    """Register *spec*; raise ``ValueError`` on a duplicate key."""
    if spec.key in _REGISTRY:
        raise ValueError(f"estimator method {spec.key!r} is already registered.")
    _REGISTRY[spec.key] = spec
    return spec


def get_estimator_spec(key: str, archetype: CausalArchetype) -> EstimatorSpec:
    """Look up *key* restricted to *archetype*; raise :class:`UnknownMethodError` otherwise."""
    spec = _REGISTRY.get(key)
    if spec is None or spec.archetype != archetype:
        raise UnknownMethodError(
            f"unknown {archetype} method {key!r}; expected one of "
            f"{keys_for_archetype(archetype)!r}."
        )
    return spec


def known_method_keys() -> list[str]:
    """Every registered estimator method key, sorted for deterministic output."""
    return sorted(_REGISTRY)


def keys_for_archetype(archetype: CausalArchetype) -> list[str]:
    """Every registered method key for *archetype*, sorted."""
    return sorted(k for k, spec in _REGISTRY.items() if spec.archetype == archetype)
