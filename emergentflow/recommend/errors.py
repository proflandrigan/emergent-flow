"""
emergentflow.recommend.errors
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Typed errors for the Epic 15 recommender-systems archetypes + wrapper seams.

Rooted at :class:`RecommendError` (a :class:`ValueError` subclass) so every recommend-family
failure is catchable with one except clause while staying compatible with existing
``pytest.raises(ValueError)``-style tests, mirroring ``emergentflow.stats.errors.StatsError`` and
``emergentflow.ml.errors.MLAdapterError``.
"""

from __future__ import annotations

__all__ = [
    "RecommendError",
    "UnknownAlgorithmError",
    "InvalidRecommenderParamsError",
    "MissingOptionalDependencyError",
]


class RecommendError(ValueError):
    """Base class for all recommend-family (algorithm archetype / wrapper) errors."""


class UnknownAlgorithmError(RecommendError):
    """Raised when an algorithm key is not present in the curated allow-list registry."""


class InvalidRecommenderParamsError(RecommendError):
    """Raised when a recommender's structured params are invalid (unknown/missing param,
    a column reference not present on the input data, etc.)."""


class MissingOptionalDependencyError(RecommendError):
    """Raised when a node needs an optional dependency group that is not installed.

    The ``extra`` argument is the pip install target (e.g. ``"emergentflow[recommend]"``); the
    message tells the user exactly how to install it, so a base-install use of an
    ``implicit``-backed or ``torch``-backed node never surfaces an opaque ``ImportError``.
    """

    def __init__(self, extra: str) -> None:
        self.extra = extra
        super().__init__(
            f"this feature requires the optional dependency group {extra!r}; "
            f"install it with `pip install {extra}`."
        )
