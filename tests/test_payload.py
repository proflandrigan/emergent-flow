"""Tests for the result-payload contract (ADR 0013, §A6; ADR 0002).

Exercises ``to_payload`` against the real artifact shapes that flow out of
``ef.execute``: scalars, oversized strings, JSON containers, ``pandas.DataFrame``
(small, truncated, and NaN-bearing), a ``@dataclass`` with a nested DataFrame
(mirroring ``emergentflow.stats.AnovaResult``), and an arbitrary unsupported
object. No torch, no network.
"""

from __future__ import annotations

import dataclasses
import json
import math

import numpy as np
import pandas as pd
import pytest

from emergentflow.server.payload import MAX_HEAD_ROWS, MAX_IMAGE_BYTES, MAX_TEXT_CHARS, to_payload


def test_scalar_kinds() -> None:
    for value in (None, True, 3, 1.5, "hi"):
        payload = to_payload(value)
        assert payload["kind"] == "scalar"
        assert payload["value"] == value


def test_long_string_is_text_and_truncated() -> None:
    text = "x" * (MAX_TEXT_CHARS + 100)
    payload = to_payload(text)
    assert payload["kind"] == "text"
    assert payload["truncated"] is True
    assert len(payload["value"]) == MAX_TEXT_CHARS
    assert payload["length"] == MAX_TEXT_CHARS + 100


def test_json_container() -> None:
    value = {"a": [1, 2]}
    payload = to_payload(value)
    assert payload["kind"] == "json"
    assert payload["value"] == value


def test_dataframe_table_shape() -> None:
    df = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
    payload = to_payload(df)
    assert payload["kind"] == "table"
    assert payload["columns"] == ["a", "b"]
    assert len(payload["dtypes"]) == 2
    assert payload["shape"] == [3, 2]
    assert payload["truncated"] is False
    assert len(payload["head"]) == 3


def test_dataframe_truncates_to_head() -> None:
    df = pd.DataFrame({"x": range(60)})
    payload = to_payload(df)
    assert payload["truncated"] is True
    assert len(payload["head"]) == MAX_HEAD_ROWS
    assert payload["shape"][0] == 60


def test_dataframe_datetime_timedelta_describe_is_json_safe() -> None:
    df = pd.DataFrame(
        {
            "ts": pd.date_range("2020-01-01", periods=3),
            "td": pd.to_timedelta(["1 days", "2 days", "3 days"]),
            "val": [1.0, 2.0, 3.0],
        }
    )
    payload = to_payload(df)
    json.dumps(payload)
    desc = payload["describe"]
    assert "ts" in desc
    assert "td" in desc
    assert "val" in desc
    # Timestamp values must be ISO strings, not pd.Timestamp objects
    assert isinstance(desc["ts"]["mean"], str)
    assert desc["ts"]["mean"] == "2020-01-02T00:00:00"
    # Timedelta values must be ISO strings, not pd.Timedelta objects
    assert isinstance(desc["td"]["mean"], str)
    assert desc["td"]["mean"] == "P2DT0H0M0S"
    # Numeric column stats remain numbers
    assert isinstance(desc["val"]["mean"], float)
    assert desc["val"]["mean"] == 2.0
    # std for a single-valued timedelta is NaN -> None
    assert desc["ts"]["std"] is None


def test_dataframe_nan_is_json_safe() -> None:
    df = pd.DataFrame({"x": [1.0, float("nan"), 3.0]})
    payload = to_payload(df)
    json.dumps(payload)
    nan_cells = [row["x"] for row in payload["head"] if row["x"] is None]
    assert len(nan_cells) == 1
    remaining = [row["x"] for row in payload["head"] if row["x"] is not None]
    assert all(not math.isnan(x) for x in remaining)


def test_dataclass_record_with_nested_dataframe() -> None:
    @dataclasses.dataclass
    class FakeAnovaResult:
        f_statistic: float
        summary: pd.DataFrame

    result = FakeAnovaResult(f_statistic=4.2, summary=pd.DataFrame({"x": [1, 2]}))
    payload = to_payload(result)
    assert payload["kind"] == "record"
    assert payload["type"] == "FakeAnovaResult"
    assert payload["fields"]["f_statistic"]["kind"] == "scalar"
    assert payload["fields"]["summary"]["kind"] == "table"


def test_unsupported_object() -> None:
    class Opaque:
        pass

    payload = to_payload(Opaque())
    assert payload["kind"] == "unsupported"
    assert payload["type"] == "Opaque"
    assert "repr" in payload


def test_payload_always_json_serializable() -> None:
    df = pd.DataFrame({"x": range(60), "y": [float("nan")] * 60})

    @dataclasses.dataclass
    class Nested:
        value: float
        frame: pd.DataFrame

    samples = [
        None,
        True,
        3,
        1.5,
        "hi",
        "x" * (MAX_TEXT_CHARS + 1),
        {"a": [1, 2]},
        df,
        Nested(value=1.0, frame=df),
        object(),
    ]
    for sample in samples:
        json.dumps(to_payload(sample))


def test_nonfinite_scalar_is_valid_json() -> None:
    # json.dumps(allow_nan=True) would emit the bare token `NaN`, which Python's
    # own loads accepts but a browser's JSON.parse rejects -- the contract's real
    # consumer. NaN/Inf must serialize to a spec-valid `null`.
    for bad in (float("nan"), float("inf"), float("-inf")):
        payload = to_payload(bad)
        assert payload == {"kind": "scalar", "value": None}
        assert "NaN" not in json.dumps(payload)
        assert "Infinity" not in json.dumps(payload)


def test_nonfinite_inside_json_container_is_nulled() -> None:
    payload = to_payload({"vals": [1.0, float("nan"), float("inf")]})
    assert payload["kind"] == "json"
    assert payload["value"] == {"vals": [1.0, None, None]}
    json.dumps(payload)  # spec-valid: no NaN/Infinity tokens


def test_duplicate_column_dataframe_does_not_crash() -> None:
    # to_json(orient="records") raises on duplicate column labels; because
    # to_payload runs after the per-node try/except in service.py, an unhandled
    # raise here would escape as a top-level 422 and wipe every node's results.
    df = pd.DataFrame([[1, 2], [3, 4]], columns=["a", "a"])
    payload = to_payload(df)
    assert payload["kind"] == "table"
    assert payload["shape"] == [2, 2]
    assert payload["columns"] == ["a", "a"]
    assert len(payload["head"]) == 2
    json.dumps(payload)  # still JSON-safe


def test_numpy_scalars_become_native_scalars() -> None:
    # numpy scalars are not Python int/bool subclasses, so without explicit
    # handling they'd fall to "unsupported". They must coerce to native scalars.
    assert to_payload(np.int64(7)) == {"kind": "scalar", "value": 7}
    assert to_payload(np.bool_(True)) == {"kind": "scalar", "value": True}
    f32 = to_payload(np.float32(1.5))
    assert f32["kind"] == "scalar" and f32["value"] == 1.5
    # native types survive the round trip
    assert isinstance(to_payload(np.int64(7))["value"], int)
    assert isinstance(to_payload(np.bool_(True))["value"], bool)


def test_numpy_nonfinite_scalar_is_nulled() -> None:
    payload = to_payload(np.float32("nan"))
    assert payload == {"kind": "scalar", "value": None}
    assert "NaN" not in json.dumps(payload)


def test_html_string_becomes_html_payload() -> None:
    out = to_payload("<!DOCTYPE html><html><body>hi</body></html>")
    assert out["kind"] == "html"
    assert out["truncated"] is False
    assert out["value"] == "<!DOCTYPE html><html><body>hi</body></html>"

    # case-insensitive match
    assert to_payload("<HTML>x</HTML>")["kind"] == "html"

    # leading whitespace tolerated
    assert to_payload("\n  <html></html>")["kind"] == "html"


def test_non_html_string_is_scalar() -> None:
    assert to_payload("<div>not a doc</div>")["kind"] == "scalar"
    assert to_payload("hello")["kind"] == "scalar"
    # Must NOT false-positive on strings that merely start with "<html" but are not documents.
    assert to_payload("<htmlparser>foo</htmlparser>")["kind"] == "scalar"
    assert to_payload("<html_escape is a PHP function>")["kind"] == "scalar"


def test_oversized_html_is_unsupported() -> None:
    oversized = "<!DOCTYPE html><html>" + "x" * MAX_IMAGE_BYTES
    out = to_payload(oversized)
    assert out["kind"] == "unsupported"
    assert str(MAX_IMAGE_BYTES) in out["repr"]


def test_series_becomes_single_column_table() -> None:
    s = pd.Series([1, 2, 3], name="x")
    out = to_payload(s)
    assert out["kind"] == "table"
    assert out["columns"] == ["x"]
    assert out["shape"] == [3, 1]
    assert out["truncated"] is False
    assert len(out["head"]) == 3


def test_series_with_named_index_preserves_labels() -> None:
    s = pd.Series([10, 20, 30], index=["a", "b", "c"], name="value")
    out = to_payload(s)
    assert out["kind"] == "table"
    # The named index must appear as a column so row labels are not silently dropped.
    assert "index" in out["columns"]
    assert "value" in out["columns"]
    # Row labels must survive serialization.
    labels = [row["index"] for row in out["head"]]
    assert labels == ["a", "b", "c"]


def test_figure_becomes_image_payload() -> None:
    matplotlib = pytest.importorskip("matplotlib")
    matplotlib.use("Agg")  # headless backend; no display needed
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], [1, 4, 9])
    try:
        out = to_payload(fig)
    finally:
        plt.close(fig)  # the test owns the figure; to_payload must NOT close it
    assert out["kind"] == "image"
    assert out["mime"] == "image/png"
    assert isinstance(out["data"], str) and len(out["data"]) > 0
    assert isinstance(out["width"], int) and out["width"] > 0
    assert isinstance(out["height"], int) and out["height"] > 0
    # data must be valid base64
    import base64

    base64.b64decode(out["data"])  # raises if invalid


def test_oversized_figure_is_unsupported(monkeypatch: pytest.MonkeyPatch) -> None:
    matplotlib = pytest.importorskip("matplotlib")
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    import emergentflow.server.payload as payload_mod

    monkeypatch.setattr(payload_mod, "MAX_IMAGE_BYTES", 10)  # any real PNG exceeds 10 bytes
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3])
    try:
        out = payload_mod.to_payload(fig)
    finally:
        plt.close(fig)
    assert out["kind"] == "unsupported"


def test_new_payload_kinds_are_json_serializable() -> None:
    html_out = to_payload("<!DOCTYPE html><html><body>hello</body></html>")
    json.dumps(html_out)

    s = pd.Series([10, 20, 30], name="val")
    series_out = to_payload(s)
    json.dumps(series_out)
