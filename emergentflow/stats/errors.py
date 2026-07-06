"""
emergentflow.stats.errors
~~~~~~~~~~~~~~~~~~~~~~~~~~
Typed errors for the Epic 12 statistics model archetypes + wrapper seams.

Rooted at :class:`StatsError` (a :class:`ValueError` subclass) so every stats-family failure is
catchable with one except clause while staying compatible with existing
``pytest.raises(ValueError)``-style tests, mirroring ``emergentflow.ml.errors.MLAdapterError``.
"""

from __future__ import annotations

__all__ = [
    "StatsError",
    "UnknownModelError",
    "InvalidModelSpecError",
    "MissingOptionalDependencyError",
]


class StatsError(ValueError):
    """Base class for all stats-family (model archetype / wrapper) errors."""


class UnknownModelError(StatsError):
    """Raised when a model key is not present in the curated model allow-list registry."""


class InvalidModelSpecError(StatsError):
    """Raised when a structured model spec is invalid (missing/unknown columns, missing
    required fields for the family, incompatible family/link, etc.)."""


class MissingOptionalDependencyError(StatsError):
    """Raised when a node needs an optional dependency group that is not installed.

    The ``extra`` argument is the pip install target (e.g. ``"emergentflow[bayes]"``); the
    message tells the user exactly how to install it, so a base-install use of a Bayesian node
    never surfaces an opaque ``ImportError`` (Epic 12 Story 1's hard optional-dependency boundary).
    """

    def __init__(self, extra: str) -> None:
        self.extra = extra
        super().__init__(
            f"this feature requires the optional dependency group {extra!r}; "
            f"install it with `pip install {extra}`."
        )
