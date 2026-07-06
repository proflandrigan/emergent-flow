"""
emergentflow.viz.catalog
~~~~~~~~~~~~~~~~~~~~~~~~~~
Seed chart catalog for Emergent Flow's visualization archetype (Epic 12, Story 2).

Importing this module registers a small, curated set of chart allow-list entries into
``emergentflow.viz.registry`` as an import-time side effect, mirroring
``emergentflow.stats.catalog`` and ``emergentflow.types.catalog``.

This is a SEED set (scatter) so the ``ef.viz.plot`` seam and its tests have a representative chart
to exercise. It is deliberately NOT the full curated chart catalog -- line/bar/histogram/box/violin/
ECDF/density-heatmap/etc. are widened in Epic 12 Story 8 as a reviewed allow-list change.
"""

from __future__ import annotations

from emergentflow.viz.registry import ChartSpec, register_chart

register_chart(
    ChartSpec(
        key="scatter",
        px_function="scatter",
        encodings=(
            "x",
            "y",
            "color",
            "size",
            "symbol",
            "facet_row",
            "facet_col",
            "hover_data",
        ),
        options=("trendline", "opacity", "log_x", "log_y", "marginal_x", "marginal_y"),
        description="A 2-D scatter plot (plotly.express.scatter), optional OLS/lowess trendline.",
    )
)
