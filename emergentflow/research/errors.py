"""
emergentflow.research.errors
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Typed errors for the research family (reports, lineage, reproducibility, data-quality).

Rooted at :class:`ResearchError` (a :class:`ValueError` subclass) so every research-family
failure is catchable with one except clause while staying compatible with existing
``pytest.raises(ValueError)``-style tests, mirroring ``emergentflow.clean.errors.CleanError``.
"""

from __future__ import annotations

import pandas as pd

__all__ = [
    "DataQualityError",
    "MissingOptionalDependencyError",
    "ResearchError",
    "UnknownNodeError",
]


class ResearchError(ValueError):
    """Base error for every ef.research op (reports, lineage, reproducibility, quality)."""


class UnknownNodeError(ResearchError):
    """Raised when a node id does not exist in the given graph."""


class DataQualityError(ResearchError):
    """Raised by ``assert_data`` when one or more declared expectations fail.

    Carries the tidy violations frame as an attribute (rather than only formatting it into the
    message) so a caller -- the ``assert_data`` node's ``execute``, or the server's error path
    -- can surface the structured detail, not just the summary text.
    """

    def __init__(self, message: str, violations: pd.DataFrame) -> None:
        self.violations = violations
        super().__init__(message)


class MissingOptionalDependencyError(ResearchError):
    """Raised when a research-family op needs an optional dependency group that is not
    installed."""

    def __init__(self, extra: str) -> None:
        self.extra = extra
        super().__init__(
            f"this feature requires the optional dependency group {extra!r}; "
            f"install it with `pip install {extra}`."
        )
