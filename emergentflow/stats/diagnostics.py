"""
emergentflow.stats.diagnostics
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Diagnostic allow-list registry for the Epic 12 statistics "diagnostic" archetype (Story 6).

Maps a curated ``diagnostic`` key (e.g. ``"vif"``) to a :class:`DiagnosticSpec` describing
whether it needs a raw DataFrame and/or an already-fitted ``FittedStatsModel``, its structured
spec fields, and its own ``fn`` callable that computes the tidy diagnostic frame. This is the
diagnostic-archetype analog of ``emergentflow.stats.registry`` (the fit-model allow-list) --
a separate, parallel registry because the diagnostic archetype's port shape (DataFrame and/or
StatsModel in, plain DataFrame out) differs from fit-model's (DataFrame in, StatsModel out).

The curated seed catalog is registered as data by importing
``emergentflow.stats.diagnostics_catalog`` for its side effect, mirroring
``emergentflow.stats.catalog``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from emergentflow.stats.errors import UnknownDiagnosticError

if TYPE_CHECKING:
    import pandas as pd

    from emergentflow.stats.models import FittedStatsModel

__all__ = [
    "DiagnosticSpec",
    "register_diagnostic",
    "get_diagnostic_spec",
    "known_diagnostic_keys",
]

#: (df, model, resolved_spec) -> tidy diagnostic DataFrame (schema: DIAGNOSTIC_COLUMNS).
#: Validation is done upstream by ``_prepare_diagnostic_spec``, so a fn may assume its inputs are
#: well-formed for its own ``needs_frame``/``needs_model`` contract.
DiagnosticFn = Callable[["pd.DataFrame | None", "FittedStatsModel | None", dict[str, Any]], Any]


@dataclass(frozen=True)
class DiagnosticSpec:
    """One curated allow-list entry mapping a diagnostic key to how to compute + validate it.

    Attributes
    ----------
    key: curated diagnostic identifier used as the ``diagnostic`` param (e.g. ``"vif"``).
    fn: the callable that computes the tidy diagnostic frame from ``(df, model, spec)``.
    needs_frame: whether this diagnostic requires a raw DataFrame input.
    needs_model: whether this diagnostic requires an already-fitted StatsModel input.
        Exactly one of ``needs_frame``/``needs_model`` is ``True`` for every seed entry in this
        catalog (see module docstring for why "either one" is deferred).
    required_spec_fields: structured-spec keys that MUST be present.
    optional_spec_fields: additional structured-spec keys this diagnostic accepts.
    description: curated one-line summary for the generated catalog.
    """

    key: str
    fn: DiagnosticFn
    needs_frame: bool
    needs_model: bool
    required_spec_fields: tuple[str, ...] = ()
    optional_spec_fields: tuple[str, ...] = ()
    description: str = ""


_REGISTRY: dict[str, DiagnosticSpec] = {}


def register_diagnostic(spec: DiagnosticSpec) -> DiagnosticSpec:
    """Register *spec* under ``spec.key``; raise ``ValueError`` on a duplicate key."""
    if spec.key in _REGISTRY:
        raise ValueError(f"diagnostic key {spec.key!r} is already registered.")
    _REGISTRY[spec.key] = spec
    return spec


def get_diagnostic_spec(key: str) -> DiagnosticSpec:
    """Look up *key*; raise :class:`UnknownDiagnosticError` if not curated/registered."""
    try:
        return _REGISTRY[key]
    except KeyError:
        raise UnknownDiagnosticError(
            f"unknown diagnostic {key!r}; expected one of {known_diagnostic_keys()!r}."
        ) from None


def known_diagnostic_keys() -> list[str]:
    """Every registered diagnostic key, sorted for deterministic output."""
    return sorted(_REGISTRY)
