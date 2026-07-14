"""
emergentflow.timeseries.errors
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Typed errors for the timeseries family.

Rooted at :class:`TimeseriesError` (a :class:`ValueError` subclass) so every timeseries-family
failure is catchable with one except clause while staying compatible with existing
``pytest.raises(ValueError)``-style tests, mirroring ``emergentflow.stats.errors.StatsError``.
"""

from __future__ import annotations

__all__ = ["TimeseriesError"]


class TimeseriesError(ValueError):
    """Base error for timeseries operations."""
