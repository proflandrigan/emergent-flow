"""
emergentflow.viz.errors
~~~~~~~~~~~~~~~~~~~~~~~~
Typed errors for the Epic 12 visualization archetype + wrapper seam.

Rooted at :class:`VizError` (a :class:`ValueError` subclass) so every viz-family failure is
catchable with one except clause, mirroring ``emergentflow.stats.errors.StatsError`` and
``emergentflow.ml.errors.MLAdapterError``.
"""

from __future__ import annotations

__all__ = ["VizError", "UnknownChartError", "InvalidEncodingError"]


class VizError(ValueError):
    """Base class for all viz-family (chart archetype / wrapper) errors."""


class UnknownChartError(VizError):
    """Raised when a chart key is not present in the curated chart allow-list registry."""


class InvalidEncodingError(VizError):
    """Raised when an encoding/option kwarg is not accepted by the chart, or references a
    column that is not in the input frame."""
