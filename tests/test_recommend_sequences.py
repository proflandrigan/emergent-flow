"""Tests for ``ef.recommend.build_sequences`` and ``SequenceDataset`` (Epic 15)."""

from __future__ import annotations

import pandas as pd
import pytest

from emergentflow.recommend import SequenceDataset, build_sequences
from emergentflow.recommend.errors import InvalidRecommenderParamsError


def _events() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "user_id": ["u1", "u1", "u1", "u1", "u2", "u2", "u3", "u3"],
            "item_id": ["b", "a", "c", "h", "d", "e", "f", "g"],
            "session_id": ["s1", "s1", "s2", "s2", "s3", "s3", "s4", "s4"],
            "ts": [3, 1, 2, 8, 5, 4, 6, 7],
        }
    )


def test_build_sequences_without_session_column_one_sequence_per_user() -> None:
    ds = build_sequences(_events(), user_col="user_id", item_col="item_id")

    assert isinstance(ds, SequenceDataset)
    # u1, u2, u3 -> three sessions (one per user); every user has >= min_seq_len items.
    assert len(ds.sequences) == 3
    assert ds.session_ids == ["u1", "u2", "u3"]
    assert [len(s) for s in ds.sequences] == [4, 2, 2]


def test_build_sequences_with_session_column_one_sequence_per_session() -> None:
    ds = build_sequences(
        _events(), user_col="user_id", item_col="item_id", session_col="session_id"
    )

    assert len(ds.sequences) == 4
    assert ds.session_ids == ["s1", "s2", "s3", "s4"]
    assert [len(s) for s in ds.sequences] == [2, 2, 2, 2]


def test_timestamp_sorting_changes_order() -> None:
    raw = build_sequences(
        _events(), user_col="user_id", item_col="item_id", session_col="session_id"
    )
    sorted_ds = build_sequences(
        _events(),
        user_col="user_id",
        item_col="item_id",
        session_col="session_id",
        timestamp_col="ts",
    )

    # s1 contains items b, a in raw order; chronologically (ts 1, 3) it is a, b.
    raw_s1 = raw.sequences[raw.session_ids.index("s1")]
    sorted_s1 = sorted_ds.sequences[sorted_ds.session_ids.index("s1")]
    assert raw_s1 != sorted_s1
    assert sorted_s1 == [raw.item_index["a"], raw.item_index["b"]]


def test_max_seq_len_truncates_longer_sequences() -> None:
    df = pd.DataFrame(
        {
            "user_id": ["u1"] * 5,
            "item_id": ["i1", "i2", "i3", "i4", "i5"],
        }
    )
    ds = build_sequences(df, user_col="user_id", item_col="item_id", max_seq_len=3)

    assert len(ds.sequences[0]) == 3
    # Keeps the LAST max_seq_len items.
    assert ds.sequences[0] == [ds.item_index["i3"], ds.item_index["i4"], ds.item_index["i5"]]


def test_min_seq_len_drops_short_sequences() -> None:
    df = pd.DataFrame(
        {
            "user_id": ["u1", "u1", "u1", "u2", "u2"],
            "item_id": ["a", "b", "c", "d", "e"],
        }
    )
    ds = build_sequences(df, user_col="user_id", item_col="item_id", min_seq_len=3)

    assert ds.session_ids == ["u1"]
    assert len(ds.sequences) == 1


def test_missing_columns_raise() -> None:
    df = _events()
    with pytest.raises(InvalidRecommenderParamsError):
        build_sequences(df, user_col="nope", item_col="item_id")
    with pytest.raises(InvalidRecommenderParamsError):
        build_sequences(df, user_col="user_id", item_col="nope")
    with pytest.raises(InvalidRecommenderParamsError):
        build_sequences(df, user_col="user_id", item_col="item_id", session_col="nope")
    with pytest.raises(InvalidRecommenderParamsError):
        build_sequences(df, user_col="user_id", item_col="item_id", timestamp_col="nope")


def test_item_indices_deterministic_and_in_range() -> None:
    ds = build_sequences(_events(), user_col="user_id", item_col="item_id")

    assert ds.item_ids == sorted(_events()["item_id"].unique().tolist())
    assert ds.item_index == {item_id: i for i, item_id in enumerate(ds.item_ids)}
    for seq in ds.sequences:
        for idx in seq:
            assert 0 <= idx < len(ds.item_ids)


def test_summary_is_json_native() -> None:
    ds = build_sequences(_events(), user_col="user_id", item_col="item_id")
    summary = ds.summary()

    assert summary == {
        "n_sessions": 3,
        "n_items": 8,
        "max_seq_len": 50,
        "mean_seq_len": 8 / 3,
    }
    assert isinstance(summary["n_sessions"], int)
    assert isinstance(summary["n_items"], int)
    assert isinstance(summary["max_seq_len"], int)
    assert isinstance(summary["mean_seq_len"], float)
