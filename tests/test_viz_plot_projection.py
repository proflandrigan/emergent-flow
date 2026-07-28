"""Tests for ``ef.viz.plot_projection`` (Epic 16)."""

from __future__ import annotations

import pandas as pd
import pytest

from emergentflow.viz import PlotSpec, plot_projection


def _projection_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "component_1": [1.0, 2.0, 3.0, 4.0],
            "component_2": [4.0, 3.0, 2.0, 1.0],
            "label": ["a", "a", "b", "b"],
        }
    )


def test_plot_projection_returns_plotspec_with_defaults():
    df = _projection_df()
    result = plot_projection(df)
    assert isinstance(result, PlotSpec)
    assert result.chart == "scatter"


def test_plot_projection_colored_by_label():
    df = _projection_df()
    result = plot_projection(df, color_col="label")
    assert isinstance(result, PlotSpec)
    # two distinct colors/traces for the two label values
    assert len(result.spec["data"]) == 2


def test_plot_projection_custom_x_y():
    df = _projection_df().rename(columns={"component_1": "pc1", "component_2": "pc2"})
    result = plot_projection(df, x_col="pc1", y_col="pc2")
    assert isinstance(result, PlotSpec)


def test_unknown_x_col_raises():
    df = _projection_df()
    with pytest.raises(ValueError):
        plot_projection(df, x_col="nope")


def test_unknown_color_col_raises():
    df = _projection_df()
    with pytest.raises(ValueError):
        plot_projection(df, color_col="nope")
