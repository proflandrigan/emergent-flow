"""
emergentflow.viz.catalog
~~~~~~~~~~~~~~~~~~~~~~~~~~
Full curated chart catalog for Emergent Flow's visualization archetype (Epic 12, Story 8).

Importing this module registers a curated, version-pinned set of chart allow-list entries into
``emergentflow.viz.registry`` as an import-time side effect, mirroring
``emergentflow.stats.catalog`` and ``emergentflow.types.catalog``.

The catalog is pinned to this curated allow-list (scatter, line, bar, histogram, box, violin,
strip, ecdf, density_heatmap, density_contour, scatter_matrix) and is never reflected from
the installed plotly.express version, so the chart set stays deterministic and version-stable.
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

register_chart(
    ChartSpec(
        key="line",
        px_function="line",
        encodings=(
            "x",
            "y",
            "color",
            "line_dash",
            "facet_row",
            "facet_col",
            "hover_data",
        ),
        options=("log_x", "log_y", "line_shape"),
        description="A line chart (plotly.express.line) over ordered/continuous x.",
    )
)

register_chart(
    ChartSpec(
        key="bar",
        px_function="bar",
        encodings=(
            "x",
            "y",
            "color",
            "facet_row",
            "facet_col",
            "hover_data",
        ),
        options=("barmode", "log_x", "log_y"),
        description="A bar chart (plotly.express.bar), grouped/stacked via 'barmode'.",
    )
)

register_chart(
    ChartSpec(
        key="histogram",
        px_function="histogram",
        encodings=(
            "x",
            "y",
            "color",
            "facet_row",
            "facet_col",
            "hover_data",
        ),
        options=("nbins", "barmode", "histnorm", "log_x", "log_y", "marginal"),
        description="A histogram (plotly.express.histogram) of a numeric or categorical column.",
    )
)

register_chart(
    ChartSpec(
        key="box",
        px_function="box",
        encodings=(
            "x",
            "y",
            "color",
            "facet_row",
            "facet_col",
            "hover_data",
        ),
        options=("points", "notched", "log_x", "log_y"),
        description="A box plot (plotly.express.box) summarizing a distribution per group.",
    )
)

register_chart(
    ChartSpec(
        key="violin",
        px_function="violin",
        encodings=(
            "x",
            "y",
            "color",
            "facet_row",
            "facet_col",
            "hover_data",
        ),
        options=("box", "points", "log_x", "log_y"),
        description="A violin plot (plotly.express.violin) showing distribution shape per group.",
    )
)

register_chart(
    ChartSpec(
        key="strip",
        px_function="strip",
        encodings=(
            "x",
            "y",
            "color",
            "facet_row",
            "facet_col",
            "hover_data",
        ),
        options=("log_x", "log_y"),
        description="A strip plot (plotly.express.strip) of individual points per group.",
    )
)

register_chart(
    ChartSpec(
        key="ecdf",
        px_function="ecdf",
        encodings=(
            "x",
            "color",
            "facet_row",
            "facet_col",
            "hover_data",
        ),
        options=("log_x", "ecdfnorm"),
        description="An empirical cumulative distribution plot (plotly.express.ecdf).",
    )
)

register_chart(
    ChartSpec(
        key="density_heatmap",
        px_function="density_heatmap",
        encodings=(
            "x",
            "y",
            "z",
            "facet_row",
            "facet_col",
        ),
        options=("nbinsx", "nbinsy", "histfunc", "log_x", "log_y"),
        description="A 2-D binned density heatmap (plotly.express.density_heatmap).",
    )
)

register_chart(
    ChartSpec(
        key="density_contour",
        px_function="density_contour",
        encodings=(
            "x",
            "y",
            "z",
            "color",
            "facet_row",
            "facet_col",
        ),
        options=("nbinsx", "nbinsy", "histfunc", "log_x", "log_y"),
        description="A 2-D density contour plot (plotly.express.density_contour).",
    )
)

register_chart(
    ChartSpec(
        key="scatter_matrix",
        px_function="scatter_matrix",
        encodings=(
            "dimensions",
            "color",
            "symbol",
            "hover_data",
        ),
        options=("opacity",),
        description="A scatter-plot matrix / pair plot across several numeric dimensions "
        "(plotly.express.scatter_matrix).",
    )
)
