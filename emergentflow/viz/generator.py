"""
emergentflow.viz.generator
~~~~~~~~~~~~~~~~~~~~~~~~~~~
A pure generator mapping curated ``ChartSpec`` allow-list entries to catalog-entry dicts
(Epic 12, Story 8 -- the ``emergentflow.ml.generator`` analog for the chart registry).

Turns the chart registry into JSON-native data the canvas palette can render with zero
per-chart-type UI code: no I/O, no global state, deterministic given the same input list
(mirrors ``emergentflow.ml.generator.generate_estimator_catalog_entries``).
"""

from __future__ import annotations

from typing import Any

from emergentflow.viz.registry import ChartSpec

#: Chart keys whose whole-key form is an acronym (title-casing word-by-word would mangle
#: it, e.g. "ecdf".capitalize() -> "Ecdf" instead of "ECDF").
_ACRONYMS = frozenset({"ecdf"})


def _humanize(key: str) -> str:
    """``"density_heatmap"`` -> ``"Density Heatmap"``; ``"ecdf"`` -> ``"ECDF"``."""
    if key in _ACRONYMS:
        return key.upper()
    return " ".join(word.capitalize() for word in key.split("_"))


def generate_chart_catalog_entries(specs: list[ChartSpec]) -> list[dict[str, Any]]:
    """Map curated *specs* to JSON-native catalog-entry dicts, sorted by ``key``.

    Pure: output depends only on *specs*. Each entry has keys ``key``, ``node_type``,
    ``label``, ``category``, ``description``, ``px_function``, ``encodings``, ``options``
    (the latter two as sorted lists, since ``ChartSpec`` stores them as tuples and JSON has no
    tuple type).
    """
    entries = [
        {
            "key": spec.key,
            "node_type": "viz.plot",
            "label": _humanize(spec.key),
            "category": "Visualization",
            "description": spec.description,
            "px_function": spec.px_function,
            "encodings": sorted(spec.encodings),
            "options": sorted(spec.options),
        }
        for spec in specs
    ]
    return sorted(entries, key=lambda e: e["key"])
