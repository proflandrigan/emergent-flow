"""
Tests for ``ef.recommend.encode_categorical_features`` (Epic 15, Story 11 feature-frame
transform): one-hot and ordinal encoding, ``drop_first`` behaviour, error cases, and the
no-mutation guarantee.
"""

from __future__ import annotations

import pandas as pd
import pytest

from emergentflow.recommend import encode_categorical_features, weight_interactions_by_recency
from emergentflow.recommend.errors import InvalidRecommenderParamsError


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "user_id": [1, 2, 3, 4],
            "gender": ["M", "F", "F", "M"],
            "country": ["US", "US", "CA", "MX"],
        }
    )


def test_onehot_encodes_two_columns_and_preserves_id() -> None:
    df = _frame()
    result = encode_categorical_features(df, columns=["gender", "country"], id_col="user_id")

    assert list(result.columns)[0] == "user_id"
    assert result["user_id"].tolist() == [1, 2, 3, 4]
    assert "gender_M" in result.columns
    assert "gender_F" in result.columns
    assert "country_US" in result.columns
    assert "country_CA" in result.columns
    assert "country_MX" in result.columns
    # every encoded column is numeric (float)
    for col in result.columns:
        if col != "user_id":
            assert pd.api.types.is_numeric_dtype(result[col])


def test_ordinal_encodes_single_column_and_preserves_id() -> None:
    df = _frame()
    result = encode_categorical_features(
        df, columns=["country"], id_col="user_id", strategy="ordinal"
    )

    assert list(result.columns) == ["user_id", "country"]
    assert result["user_id"].tolist() == [1, 2, 3, 4]
    assert pd.api.types.is_numeric_dtype(result["country"])
    # US -> 2.0, CA -> 0.0, MX -> 1.0 (alphabetical ordinal order)
    assert result["country"].tolist() == [2.0, 2.0, 0.0, 1.0]


def test_drop_first_reduces_onehot_columns_by_one_per_input_column() -> None:
    df = _frame()
    full = encode_categorical_features(df, columns=["gender", "country"], id_col="user_id")
    dropped = encode_categorical_features(
        df, columns=["gender", "country"], id_col="user_id", drop_first=True
    )

    n_columns_full = len(full.columns) - 1  # minus id_col
    n_columns_dropped = len(dropped.columns) - 1
    assert n_columns_dropped == n_columns_full - 2


def test_unknown_strategy_raises() -> None:
    df = _frame()
    with pytest.raises(InvalidRecommenderParamsError):
        encode_categorical_features(df, columns=["gender"], id_col="user_id", strategy="target")


def test_missing_id_col_raises() -> None:
    df = _frame()
    with pytest.raises(InvalidRecommenderParamsError):
        encode_categorical_features(df, columns=["gender"], id_col="nope")


def test_missing_column_in_columns_raises() -> None:
    df = _frame()
    with pytest.raises(InvalidRecommenderParamsError):
        encode_categorical_features(df, columns=["gender", "nope"], id_col="user_id")


def test_input_frame_not_mutated() -> None:
    df = _frame()
    original = df.copy(deep=True)
    encode_categorical_features(df, columns=["gender", "country"], id_col="user_id")
    pd.testing.assert_frame_equal(df, original)


def _recency_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "user_id": [1, 1, 2, 3],
            "item_id": [10, 20, 30, 40],
            "timestamp": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-05", "2026-01-10"]),
        }
    )


def test_recent_event_gets_higher_weight_than_older_event() -> None:
    df = _recency_frame()
    result = weight_interactions_by_recency(
        df, timestamp_col="timestamp", user_col="user_id", item_col="item_id"
    )

    # default reference_time is the max timestamp (2026-01-10); older events decay more.
    assert result.loc[0, "weight"] < result.loc[1, "weight"] < result.loc[3, "weight"]
    assert result["weight"].max() <= 1.0
    assert (result["weight"] > 0).all()


def test_half_life_days_sets_half_weight_for_one_day_old_event() -> None:
    df = pd.DataFrame(
        {
            "user_id": [1],
            "item_id": [10],
            "timestamp": pd.to_datetime(["2026-01-09"]),
        }
    )
    result = weight_interactions_by_recency(
        df,
        timestamp_col="timestamp",
        user_col="user_id",
        item_col="item_id",
        half_life_days=1.0,
    )
    # reference_time defaults to max timestamp (2026-01-09), so age == 0 -> weight == 1.0.
    # Instead pass an explicit reference_time one day later to exercise the half-life.
    assert abs(result.loc[0, "weight"] - 1.0) < 1e-9

    result = weight_interactions_by_recency(
        df,
        timestamp_col="timestamp",
        user_col="user_id",
        item_col="item_id",
        half_life_days=1.0,
        reference_time="2026-01-10",
    )
    assert abs(result.loc[0, "weight"] - 0.5) < 1e-9


def test_reference_time_overrides_default_max_timestamp() -> None:
    df = _recency_frame()
    explicit = weight_interactions_by_recency(
        df,
        timestamp_col="timestamp",
        user_col="user_id",
        item_col="item_id",
        reference_time="2026-01-10",
    )
    default = weight_interactions_by_recency(
        df, timestamp_col="timestamp", user_col="user_id", item_col="item_id"
    )
    pd.testing.assert_series_equal(explicit["weight"], default["weight"])

    earlier = weight_interactions_by_recency(
        df,
        timestamp_col="timestamp",
        user_col="user_id",
        item_col="item_id",
        reference_time="2026-01-05",
    )
    # an earlier reference time makes every event younger, so weights are higher.
    assert (earlier["weight"] > default["weight"]).all()


def test_unknown_decay_raises() -> None:
    df = _recency_frame()
    with pytest.raises(InvalidRecommenderParamsError):
        weight_interactions_by_recency(
            df,
            timestamp_col="timestamp",
            user_col="user_id",
            item_col="item_id",
            decay="linear",
        )


def test_non_positive_half_life_raises() -> None:
    df = _recency_frame()
    with pytest.raises(InvalidRecommenderParamsError):
        weight_interactions_by_recency(
            df,
            timestamp_col="timestamp",
            user_col="user_id",
            item_col="item_id",
            half_life_days=0.0,
        )


def test_missing_columns_raise() -> None:
    df = _recency_frame()
    with pytest.raises(InvalidRecommenderParamsError):
        weight_interactions_by_recency(
            df, timestamp_col="nope", user_col="user_id", item_col="item_id"
        )
    with pytest.raises(InvalidRecommenderParamsError):
        weight_interactions_by_recency(
            df, timestamp_col="timestamp", user_col="nope", item_col="item_id"
        )
    with pytest.raises(InvalidRecommenderParamsError):
        weight_interactions_by_recency(
            df, timestamp_col="timestamp", user_col="user_id", item_col="nope"
        )


def test_recency_input_frame_not_mutated() -> None:
    df = _recency_frame()
    original = df.copy(deep=True)
    weight_interactions_by_recency(
        df, timestamp_col="timestamp", user_col="user_id", item_col="item_id"
    )
    pd.testing.assert_frame_equal(df, original)
