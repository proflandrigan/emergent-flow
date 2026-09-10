"""
emergentflow.causal.errors
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Typed errors for the causal-inference family (issue #164 Gap 1).

Rooted at :class:`CausalError` (a :class:`ValueError` subclass) so every causal-family
failure is catchable with one except clause while staying compatible with existing
``pytest.raises(ValueError)``-style tests, mirroring ``emergentflow.stats.errors.StatsError``.
"""

from __future__ import annotations

__all__ = [
    "CausalError",
    "InvalidTreatmentError",
    "UnknownMethodError",
    "MissingOptionalDependencyError",
]


class CausalError(ValueError):
    """Base class for all causal-inference-family errors."""


class InvalidTreatmentError(CausalError):
    """Raised when a treatment column is not binary (not exactly 0/1 values)."""


class UnknownMethodError(CausalError):
    """Raised when a method key is not a known causal estimator method."""


class MissingOptionalDependencyError(CausalError):
    """Raised when a causal op needs an optional dependency group that is not installed.

    The ``extra`` argument is the pip install target; the message tells the user exactly
    how to install it, so a base-install use never surfaces an opaque ``ImportError``.
    """

    def __init__(self, extra: str) -> None:
        self.extra = extra
        super().__init__(
            f"this feature requires the optional dependency group {extra!r}; "
            f"install it with `pip install {extra}`."
        )
