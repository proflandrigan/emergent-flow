"""Tests for the chart-catalog-entry generator (emergentflow.viz.generator).

Tests ``generate_chart_catalog_entries`` with hand-constructed ``ChartSpec`` fixtures (not the
live seed catalog) for determinism and independence from future allow-list growth.
"""

from __future__ import annotations

from emergentflow.viz.generator import generate_chart_catalog_entries
from emergentflow.viz.registry import ChartSpec


def _make_spec(
    key: str = "scatter",
    px_function: str = "scatter",
    encodings: tuple[str, ...] = ("x", "y"),
    options: tuple[str, ...] = ("log_x",),
    description: str = "A scatter plot.",
) -> ChartSpec:
    return ChartSpec(
        key=key,
        px_function=px_function,
        encodings=encodings,
        options=options,
        description=description,
    )


def test_node_type_is_viz_plot():
    specs = [_make_spec()]
    entries = generate_chart_catalog_entries(specs)
    assert entries[0]["node_type"] == "viz.plot"


def test_output_sorted_by_key():
    specs = [
        _make_spec(key="zlast", px_function="zlast"),
        _make_spec(key="alpha", px_function="alpha"),
    ]
    entries = generate_chart_catalog_entries(specs)
    keys = [e["key"] for e in entries]
    assert keys == ["alpha", "zlast"]


def test_label_humanizes_snake_case():
    specs = [_make_spec(key="density_heatmap", px_function="density_heatmap")]
    entries = generate_chart_catalog_entries(specs)
    assert entries[0]["label"] == "Density Heatmap"


def test_label_uppercases_known_acronym():
    specs = [_make_spec(key="ecdf", px_function="ecdf")]
    entries = generate_chart_catalog_entries(specs)
    assert entries[0]["label"] == "ECDF"


def test_category_is_visualization():
    specs = [_make_spec()]
    entries = generate_chart_catalog_entries(specs)
    assert entries[0]["category"] == "Visualization"


def test_description_passthrough():
    specs = [_make_spec(description="A curated one-liner.")]
    entries = generate_chart_catalog_entries(specs)
    assert entries[0]["description"] == "A curated one-liner."


def test_px_function_passthrough():
    specs = [_make_spec(px_function="scatter_matrix")]
    entries = generate_chart_catalog_entries(specs)
    assert entries[0]["px_function"] == "scatter_matrix"


def test_encodings_and_options_are_sorted_lists():
    specs = [_make_spec(encodings=("y", "x", "color"), options=("log_y", "log_x"))]
    entries = generate_chart_catalog_entries(specs)
    assert entries[0]["encodings"] == ["color", "x", "y"]
    assert entries[0]["options"] == ["log_x", "log_y"]
    assert isinstance(entries[0]["encodings"], list)
    assert isinstance(entries[0]["options"], list)


def test_entry_keys_present():
    specs = [_make_spec()]
    entries = generate_chart_catalog_entries(specs)
    assert set(entries[0]) == {
        "key",
        "node_type",
        "label",
        "category",
        "description",
        "px_function",
        "encodings",
        "options",
    }


def test_deterministic():
    specs = [_make_spec()]
    assert generate_chart_catalog_entries(specs) == generate_chart_catalog_entries(specs)
