"""
emergentflow.viz.registry
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Chart allow-list registry for the Epic 12 visualization archetype (the Epic 8 estimator-registry
analog applied to charts).

Maps a curated ``chart`` key (e.g. ``"scatter"``) to a :class:`ChartSpec` carrying the
``plotly.express`` function name plus the encoding/option kwargs it accepts. The catalog is pinned
to this curated allow-list, never reflected from ``plotly.express`` at runtime, so the chart set
stays deterministic and version-stable. The px function is stored as a NAME (resolved at plot
time by ``ef.viz.plot``) so this module never imports plotly.

The curated catalog is registered as data by importing ``emergentflow.viz.catalog`` for its side
effect, mirroring ``emergentflow.stats.catalog`` / ``emergentflow.types.catalog``.
"""

from __future__ import annotations

from dataclasses import dataclass

from emergentflow.viz.errors import UnknownChartError

__all__ = [
    "ChartSpec",
    "register_chart",
    "get_chart_spec",
    "known_chart_keys",
]


@dataclass(frozen=True)
class ChartSpec:
    """One curated allow-list entry mapping a chart key to its plotly.express call surface.

    Attributes
    ----------
    key: the curated chart identifier used as the ``chart`` param (e.g. ``"scatter"``).
    px_function: the ``plotly.express`` function name (e.g. ``"scatter"``), resolved at plot time.
    encodings: accepted encoding kwarg names whose values are column references
        (x/y/color/size/symbol/facet_row/facet_col/hover_data).
    options: accepted non-column option kwarg names (trendline/opacity/log_x/log_y/marginal_*).
    description: curated one-line summary for the generated catalog (Story 8's generator).
    """

    key: str
    px_function: str
    encodings: tuple[str, ...] = ()
    options: tuple[str, ...] = ()
    description: str = ""


_REGISTRY: dict[str, ChartSpec] = {}


def register_chart(spec: ChartSpec) -> ChartSpec:
    """Register *spec* under ``spec.key``; raise ``ValueError`` on a duplicate key."""
    if spec.key in _REGISTRY:
        raise ValueError(f"chart key {spec.key!r} is already registered.")
    _REGISTRY[spec.key] = spec
    return spec


def get_chart_spec(key: str) -> ChartSpec:
    """Look up *key*; raise :class:`UnknownChartError` if not a curated, registered chart."""
    try:
        return _REGISTRY[key]
    except KeyError:
        raise UnknownChartError(
            f"unknown chart {key!r}; expected one of {known_chart_keys()!r}."
        ) from None


def known_chart_keys() -> list[str]:
    """Every registered chart key, sorted for deterministic output."""
    return sorted(_REGISTRY)
