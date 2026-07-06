"""
emergentflow.viz.models
~~~~~~~~~~~~~~~~~~~~~~~~
The inspectable representation for a rendered plot (Epic 12, Story 2).

``PlotSpec`` is a thin, JSON-native wrapper over a plotly figure's JSON. It is the terminal render
payload every viz node emits; the Results tab renders it. No live plotly ``Figure`` ever escapes:
``from_figure`` serializes via ``fig.to_json()`` (plotly's encoder, which handles numpy) and parses
back to plain dict/list/scalar data, so a ``PlotSpec`` rides the result-payload contract untouched.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass
class PlotSpec:
    """A rendered plot as JSON-native plotly figure data (Epic 12 viz representation).

    Attributes
    ----------
    chart: the curated chart key that produced this figure (e.g. ``"scatter"``).
    spec: the plotly figure JSON (``{"data": [...], "layout": {...}}``), JSON-native.
    """

    chart: str
    spec: dict[str, Any]

    @classmethod
    def from_figure(cls, chart: str, fig: Any) -> PlotSpec:
        """Build a JSON-native PlotSpec from a live plotly ``Figure`` without letting it escape.

        ``fig.to_json()`` uses plotly's JSON encoder (numpy-aware); ``json.loads`` yields pure
        JSON-native data, so the resulting ``spec`` round-trips the result-payload contract.
        """
        return cls(chart=chart, spec=json.loads(fig.to_json()))
