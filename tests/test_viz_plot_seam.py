"""Seam tests for ``ef.viz.plot`` and the chart allow-list registry (Epic 12, Story 2).

Covers the single viz seam every chart node routes through: typed errors on bad chart/encoding,
determinism, no input-frame mutation, and the JSON-native ``PlotSpec`` contract (no live plotly
Figure ever escapes). The seed chart is ``"scatter"``; the fuller catalog is Story 8.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from emergentflow.api import PUBLIC_OPS, is_inspectable
from emergentflow.server.payload import to_payload
from emergentflow.viz import PlotSpec, known_chart_keys, plot
from emergentflow.viz.errors import InvalidEncodingError, UnknownChartError


def _make_df() -> pd.DataFrame:
    return pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0, 5.0], "b": [2.0, 4.0, 5.0, 4.0, 6.0]})


def test_plot_is_registered_public_op():
    assert "ef.viz.plot" in PUBLIC_OPS


def test_scatter_is_seed_chart():
    assert known_chart_keys() == ["scatter"]


def test_plot_returns_json_native_inspectable_plotspec():
    df = _make_df()
    ps = plot(df, chart="scatter", encoding={"x": "a", "y": "b"})
    assert isinstance(ps, PlotSpec)
    assert is_inspectable(ps)
    assert ps.chart == "scatter"
    # JSON-native: dumps must succeed and produce a plotly figure dict
    json.dumps(ps.spec)
    assert "data" in ps.spec and "layout" in ps.spec
    assert len(ps.spec["data"]) == 1


def test_plot_ols_trendline_adds_trace():
    df = _make_df()
    ps = plot(df, chart="scatter", encoding={"x": "a", "y": "b"}, options={"trendline": "ols"})
    assert len(ps.spec["data"]) == 2  # points + OLS trendline


def test_unknown_chart_key_raises():
    df = _make_df()
    with pytest.raises(UnknownChartError):
        plot(df, chart="not_a_chart", encoding={})


def test_unknown_encoding_kwarg_raises():
    df = _make_df()
    with pytest.raises(InvalidEncodingError):
        plot(df, chart="scatter", encoding={"zzz": "a"})


def test_unknown_option_kwarg_raises():
    df = _make_df()
    with pytest.raises(InvalidEncodingError):
        plot(df, chart="scatter", encoding={"x": "a", "y": "b"}, options={"zzz": 1})


def test_encoding_column_not_in_frame_raises():
    df = _make_df()
    with pytest.raises(InvalidEncodingError):
        plot(df, chart="scatter", encoding={"x": "missing", "y": "b"})


def test_dict_valued_encoding_column_not_in_frame_raises():
    # hover_data legitimately accepts a dict mapping column -> bool/format; a missing column
    # referenced as a dict key must be caught by the validation gate, not left to plotly to raise.
    df = _make_df()
    with pytest.raises(InvalidEncodingError):
        plot(df, chart="scatter", encoding={"x": "a", "y": "b", "hover_data": {"missing": True}})


def test_plot_is_deterministic():
    df = _make_df()
    a = plot(df, chart="scatter", encoding={"x": "a", "y": "b"}, options={"trendline": "ols"})
    b = plot(df, chart="scatter", encoding={"x": "a", "y": "b"}, options={"trendline": "ols"})
    assert a.spec == b.spec


def test_plot_does_not_mutate_input():
    df = _make_df()
    before = df.copy(deep=True)
    plot(df, chart="scatter", encoding={"x": "a", "y": "b"})
    pd.testing.assert_frame_equal(df, before)


def test_plotspec_round_trips_result_payload_untouched():
    df = _make_df()
    ps = plot(df, chart="scatter", encoding={"x": "a", "y": "b"})
    payload = to_payload(ps)
    assert payload["kind"] == "record"
    # spec is a plain JSON dict -> "json" kind; chart is a scalar string
    assert payload["fields"]["spec"]["kind"] == "json"
    # the whole payload must itself be JSON-serializable (no live Figure escaped)
    json.dumps(payload)
