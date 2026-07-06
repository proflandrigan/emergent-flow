"""
emergentflow.viz
~~~~~~~~~~~~~~~~~
Visualization operations (Epic 12): one ``viz.plot`` archetype over a curated, generated chart
catalog, each returning a JSON-native ``PlotSpec`` (``fig.to_json()``-derived). Mirrors the
Epic 8 estimator-adapter move -- breadth as data over one archetype -- so ADR-0002 equivalence and
the ``@public_op`` inspectable contract hold by construction across the whole chart surface.

See ``docs/stats-viz-design.md``.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from emergentflow.api import public_op
from emergentflow.viz.errors import (
    InvalidEncodingError,
    UnknownChartError,
    VizError,
)
from emergentflow.viz.models import PlotSpec
from emergentflow.viz.registry import ChartSpec, known_chart_keys
from emergentflow.viz.spec import _prepare_chart_spec

__all__ = [
    "PlotSpec",
    "ChartSpec",
    "VizError",
    "UnknownChartError",
    "InvalidEncodingError",
    "known_chart_keys",
    "plot",
]


@public_op(name="ef.viz.plot")
def plot(
    df: pd.DataFrame,
    *,
    chart: str,
    encoding: dict[str, Any] | None = None,
    options: dict[str, Any] | None = None,
) -> PlotSpec:
    """Build a curated, allow-listed plotly chart and return a JSON-native ``PlotSpec``.

    The single seam every viz node routes through (Epic 12, Story 2). ``chart`` is validated
    against the chart allow-list registry and ``encoding``/``options`` against the shared
    ``_prepare_chart_spec`` gate (raising :class:`~emergentflow.viz.errors.UnknownChartError` /
    :class:`~emergentflow.viz.errors.InvalidEncodingError`). The resolved chart's
    ``plotly.express`` function is called with the validated encoding + option kwargs, and the
    figure is serialized to a JSON-native ``PlotSpec`` (no live plotly ``Figure`` escapes). Because
    both ``compile_to_code``'s emitted code and ``execute`` reach a chart only through this
    function, ADR-0002 equivalence holds by construction. Never mutates ``df``.
    """
    import plotly.express as px

    chart_spec, resolved_encoding, resolved_options = _prepare_chart_spec(
        df, chart, encoding or {}, options or {}
    )
    px_fn = getattr(px, chart_spec.px_function)
    fig = px_fn(df, **resolved_encoding, **resolved_options)
    return PlotSpec.from_figure(chart, fig)


# Register the curated seed chart catalog as an import-time side effect (mirrors
# emergentflow.stats importing its catalog, and emergentflow.types.catalog).
from emergentflow.viz import catalog  # noqa: E402, F401
