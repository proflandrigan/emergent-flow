"""
emergentflow.reports
~~~~~~~~~~~~~~~~~~~
Automated-reporting operations (Epic 1, Story 8).

Thin wrapper over ``ydata-profiling``: each public operation defers entirely to
the underlying, trusted library — no reimplementation, no hidden transformation —
and validates its inputs at the boundary (fail fast, clear typed errors).

The HTML produced by ``ydata-profiling`` embeds the report's generation
timestamp, so the output is **not byte-reproducible** between calls even for
identical input data. Tests must assert structural properties of the HTML
(e.g. it is a non-empty string containing an ``<html`` tag, or that a given
title appears in it) rather than asserting byte-for-byte equality.

See ``docs/public-api-conventions.md`` and ``docs/sdk-design-philosophy.md``.
"""

from __future__ import annotations

import pandas as pd
from ydata_profiling import ProfileReport

from emergentflow.api import public_op

__all__ = ["generate_html_summary"]


@public_op(name="ef.reports.generate_html_summary")
def generate_html_summary(
    df: pd.DataFrame,
    *,
    title: str = "Emergent Flow Data Summary",
) -> str:
    """Generate a self-contained HTML profiling report for ``df``.

    Thin wrapper over ``ydata_profiling.ProfileReport`` (``minimal=True``). Returns
    the report as an HTML string; the input ``df`` is not mutated.
    """
    if df.empty:
        raise ValueError("cannot profile an empty DataFrame.")

    profile = ProfileReport(df, title=title, minimal=True, progress_bar=False)
    return profile.to_html()
