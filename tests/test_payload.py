"""Tests for the result-payload contract (ADR 0013, §A6; ADR 0002).

Exercises ``to_payload`` against the real artifact shapes that flow out of
``cm.execute``: scalars, oversized strings, JSON containers, ``pandas.DataFrame``
(small, truncated, and NaN-bearing), a ``@dataclass`` with a nested DataFrame
(mirroring ``colonymind.stats.AnovaResult``), and an arbitrary unsupported
object. No torch, no network.
"""

from __future__ import annotations

import dataclasses
import json
import math

import pandas as pd

from colonymind.server.payload import MAX_HEAD_ROWS, MAX_TEXT_CHARS, to_payload


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
