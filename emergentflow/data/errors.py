"""
emergentflow.data.errors
~~~~~~~~~~~~~~~~~~~~~~~~~
Typed errors for the Epic 16 data-ingestion loaders + client seams.

Rooted at :class:`DataError` (a :class:`ValueError` subclass) so every data-family
failure is catchable with one except clause while staying compatible with existing
``pytest.raises(ValueError)``-style tests, mirroring
``emergentflow.stats.errors.StatsError`` and
``emergentflow.recommend.errors.RecommendError``.
"""

from __future__ import annotations

__all__ = [
    "DataError",
    "DataLoadError",
    "SchemaContractError",
    "MissingOptionalDependencyError",
]


class DataError(ValueError):
    """Base class for all data-ingestion-family errors."""


class DataLoadError(DataError):
    """Raised when a loader cannot produce a tidy frame: a non-2xx HTTP response,
    an unparseable payload, a missing sheet, or a schema-on-load contract mismatch."""


class SchemaContractError(DataLoadError):
    """Raised specifically when a loader's optional ``expect_columns`` /
    ``expect_dtypes`` contract is violated."""


class MissingOptionalDependencyError(DataError):
    """Raised when a node needs an optional dependency group that is not installed.

    The ``extra`` argument is the pip install target (e.g. ``"emergentflow[cloud]"``); the
    message tells the user exactly how to install it, so a base-install use of a
    cloud-backed loader never surfaces an opaque ``ImportError``.
    """

    def __init__(self, extra: str) -> None:
        self.extra = extra
        super().__init__(
            f"this feature requires the optional dependency group {extra!r}; "
            f"install it with `pip install {extra}`."
        )
