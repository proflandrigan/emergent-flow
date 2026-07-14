"""
emergentflow.timeseries.errors
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Typed errors for the timeseries family.
"""

from __future__ import annotations

__all__ = ["TimeseriesError"]


class TimeseriesError(Exception):
    """Base error for timeseries operations."""
