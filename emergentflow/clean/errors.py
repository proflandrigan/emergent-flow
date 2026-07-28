"""
emergentflow.clean.errors
~~~~~~~~~~~~~~~~~~~~~~~~~
Typed errors for the clean family.

Rooted at :class:`CleanError` (a :class:`ValueError` subclass) so every clean-family
failure is catchable with one except clause while staying compatible with existing
``pytest.raises(ValueError)``-style tests, mirroring ``emergentflow.stats.errors.StatsError``
and ``emergentflow.timeseries.errors.TimeseriesError``.
"""

from __future__ import annotations

__all__ = [
    "CleanError",
    "UnknownColumnError",
    "ColumnCollisionError",
    "MissingOptionalDependencyError",
]


class CleanError(ValueError):
    """Base error for every ef.clean data-transform operation."""


class UnknownColumnError(CleanError):
    """Raised when an operation names a column that is not present in the input frame."""


class ColumnCollisionError(CleanError):
    """Raised when an operation would create a column that already exists in the output
    frame, rather than silently overwriting it."""


class MissingOptionalDependencyError(CleanError):
    """Raised when a clean-family op needs an optional dependency group that is not installed."""

    def __init__(self, extra: str) -> None:
        self.extra = extra
        super().__init__(
            f"this feature requires the optional dependency group {extra!r}; "
            f"install it with `pip install {extra}`."
        )
