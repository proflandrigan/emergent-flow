"""Tests for emergentflow.clean.text_dates (Epic 16, Story 8).

Covers ``ef.clean.clean_text`` and ``ef.clean.parse_dates``: thin wrappers over pandas' ``.str``
/``.dt`` accessors and ``pandas.to_datetime``, neither of which mutate their input.
"""

from __future__ import annotations

import pandas as pd
import pytest

from emergentflow.api import is_inspectable
from emergentflow.clean import (
    CleanError,
    ColumnCollisionError,
    UnknownColumnError,
    clean_text,
    parse_dates,
)


def _text_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "name": ["  Alice  ", "BOB", "carol dee"],
            "tags": ["a,b", "c", "d,e,f"],
            "code": ["id-123", "id-456", "id-789"],
        }
    )


def _date_df() -> pd.DataFrame:
    return pd.DataFrame({"when": ["2024-01-15", "2024-06-30", "2023-12-01"], "n": [1, 2, 3]})


# --- clean_text ---


def test_clean_text_trim_and_lower() -> None:
    result = clean_text(_text_df(), columns=["name"], operations=[{"op": "trim"}, {"op": "lower"}])
    assert list(result["name"]) == ["alice", "bob", "carol dee"]


def test_clean_text_is_non_mutating() -> None:
    df = _text_df()
    snapshot = df.copy()
    clean_text(df, columns=["name"], operations=[{"op": "trim"}, {"op": "lower"}])
    pd.testing.assert_frame_equal(df, snapshot)


def test_clean_text_upper_and_title() -> None:
    upper_result = clean_text(_text_df(), columns=["name"], operations=[{"op": "upper"}])
    assert list(upper_result["name"]) == ["  ALICE  ", "BOB", "CAROL DEE"]

    title_result = clean_text(_text_df(), columns=["name"], operations=[{"op": "title"}])
    assert list(title_result["name"]) == ["  Alice  ", "Bob", "Carol Dee"]


def test_clean_text_regex_replace() -> None:
    result = clean_text(
        _text_df(),
        columns=["name"],
        operations=[{"op": "replace", "pattern": r"\s+", "replacement": "_"}],
    )
    assert list(result["name"]) == ["_Alice_", "BOB", "carol_dee"]


def test_clean_text_literal_replace() -> None:
    result = clean_text(
        _text_df(),
        columns=["name"],
        operations=[
            {"op": "replace", "pattern": "carol dee", "replacement": "CAROL", "regex": False}
        ],
    )
    assert list(result["name"]) == ["  Alice  ", "BOB", "CAROL"]


def test_clean_text_extract() -> None:
    result = clean_text(
        _text_df(), columns=["code"], operations=[{"op": "extract", "pattern": r"id-(\d+)"}]
    )
    assert list(result["code"]) == ["123", "456", "789"]


def test_clean_text_split_to_list() -> None:
    result = clean_text(_text_df(), columns=["tags"], operations=[{"op": "split", "sep": ","}])
    assert result["tags"].iloc[0] == ["a", "b"]


def test_clean_text_suffix_creates_new_columns() -> None:
    result = clean_text(_text_df(), columns=["name"], operations=[{"op": "trim"}], suffix="_clean")
    assert list(result["name"]) == ["  Alice  ", "BOB", "carol dee"]
    assert list(result["name_clean"]) == ["Alice", "BOB", "carol dee"]


def test_clean_text_suffix_collision() -> None:
    df = _text_df().assign(name_clean="preexisting")
    with pytest.raises(ColumnCollisionError, match="already exist"):
        clean_text(df, columns=["name"], operations=[{"op": "trim"}], suffix="_clean")


def test_clean_text_unknown_column() -> None:
    with pytest.raises(UnknownColumnError):
        clean_text(_text_df(), columns=["nope"], operations=[{"op": "trim"}])


def test_clean_text_unknown_operation() -> None:
    with pytest.raises(CleanError, match="unknown operation"):
        clean_text(_text_df(), columns=["name"], operations=[{"op": "bogus"}])


def test_clean_text_replace_missing_replacement() -> None:
    with pytest.raises(CleanError, match="replace"):
        clean_text(_text_df(), columns=["name"], operations=[{"op": "replace", "pattern": "x"}])


def test_clean_text_extract_missing_pattern() -> None:
    with pytest.raises(CleanError, match="extract"):
        clean_text(_text_df(), columns=["code"], operations=[{"op": "extract"}])


def test_clean_text_split_missing_sep() -> None:
    with pytest.raises(CleanError, match="split"):
        clean_text(_text_df(), columns=["tags"], operations=[{"op": "split"}])


def test_clean_text_empty_columns() -> None:
    with pytest.raises(CleanError):
        clean_text(_text_df(), columns=[], operations=[{"op": "trim"}])


def test_clean_text_empty_operations() -> None:
    with pytest.raises(CleanError):
        clean_text(_text_df(), columns=["name"], operations=[])


def test_clean_text_bad_regex_is_typed() -> None:
    with pytest.raises(CleanError):
        clean_text(_text_df(), columns=["code"], operations=[{"op": "extract", "pattern": "("}])


# --- parse_dates ---


def test_parse_dates_converts_dtype() -> None:
    result = parse_dates(_date_df(), columns=["when"])
    assert pd.api.types.is_datetime64_any_dtype(result["when"])


def test_parse_dates_is_non_mutating() -> None:
    df = _date_df()
    snapshot = df.copy()
    parse_dates(df, columns=["when"])
    pd.testing.assert_frame_equal(df, snapshot)


def test_parse_dates_extracts_components() -> None:
    result = parse_dates(
        _date_df(), columns=["when"], components=["year", "month", "quarter", "dayofweek"]
    )
    assert list(result["when_year"]) == [2024, 2024, 2023]
    for component in ("when_year", "when_month", "when_quarter", "when_dayofweek"):
        assert component in result.columns


def test_parse_dates_explicit_format() -> None:
    result = parse_dates(_date_df(), columns=["when"], format="%Y-%m-%d")
    assert pd.api.types.is_datetime64_any_dtype(result["when"])


def test_parse_dates_errors_coerce() -> None:
    df = pd.DataFrame({"when": ["2024-01-15", "not-a-date"]})
    result = parse_dates(df, columns=["when"], errors="coerce")
    assert pd.isna(result["when"].iloc[1])


def test_parse_dates_errors_raise() -> None:
    df = pd.DataFrame({"when": ["2024-01-15", "not-a-date"]})
    with pytest.raises(CleanError):
        parse_dates(df, columns=["when"])


def test_parse_dates_component_collision() -> None:
    df = _date_df().assign(when_year=0)
    with pytest.raises(ColumnCollisionError, match="already exist"):
        parse_dates(df, columns=["when"], components=["year"])


def test_parse_dates_unknown_column() -> None:
    with pytest.raises(UnknownColumnError):
        parse_dates(_date_df(), columns=["nope"])


def test_parse_dates_unknown_component() -> None:
    with pytest.raises(CleanError, match="unknown component"):
        parse_dates(_date_df(), columns=["when"], components=["bogus"])


def test_parse_dates_unknown_errors_token() -> None:
    with pytest.raises(CleanError, match="unknown errors"):
        parse_dates(_date_df(), columns=["when"], errors="bogus")


def test_parse_dates_empty_columns() -> None:
    with pytest.raises(CleanError):
        parse_dates(_date_df(), columns=[])


# --- shared ---


def test_text_dates_results_are_inspectable() -> None:
    text_result = clean_text(_text_df(), columns=["name"], operations=[{"op": "trim"}])
    date_result = parse_dates(_date_df(), columns=["when"])
    assert is_inspectable(text_result) is True
    assert is_inspectable(date_result) is True
