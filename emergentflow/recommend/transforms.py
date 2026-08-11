"""
emergentflow.recommend.transforms
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Feature-frame transforms for the recommender family (Epic 15).

The two-tower deep recommender consumes user/item feature DataFrames but only uses numeric
columns. This module provides a dedicated transform that encodes categorical columns into
numeric indicator/ordinal columns while preserving the frame's id column, so users can wire
raw categorical feature frames straight into the two-tower seam.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder

from emergentflow.recommend.errors import InvalidRecommenderParamsError

__all__ = ["encode_categorical_features", "weight_interactions_by_recency"]

_VALID_STRATEGIES = frozenset({"onehot", "ordinal"})


def encode_categorical_features(
    df: pd.DataFrame,
    *,
    columns: list[str],
    id_col: str,
    strategy: str = "onehot",
    drop_first: bool = False,
) -> pd.DataFrame:
    """Encode categorical columns in a user- or item-feature frame while preserving its id column.

    Parameters
    ----------
    df: DataFrame with one row per entity and an id column.
    columns: categorical columns to encode.
    id_col: column to keep untouched (e.g. 'user_id' or 'item_id').
    strategy: 'onehot' or 'ordinal'. Target encoding is out of scope for this task.
    drop_first: only used when strategy='onehot'; drops one level to avoid collinearity.

    Returns
    -------
    A new DataFrame with the id column plus numeric encoded columns.
    """
    if id_col not in df.columns:
        raise InvalidRecommenderParamsError(
            f"id_col {id_col!r} is not in the input frame; "
            f"available columns: {sorted(df.columns)!r}."
        )
    missing = [col for col in columns if col not in df.columns]
    if missing:
        raise InvalidRecommenderParamsError(
            f"column(s) {missing!r} are not in the input frame; "
            f"available columns: {sorted(df.columns)!r}."
        )
    if strategy not in _VALID_STRATEGIES:
        raise InvalidRecommenderParamsError(
            f"unknown strategy {strategy!r}; expected one of {sorted(_VALID_STRATEGIES)!r}."
        )

    if strategy == "onehot":
        encoder: Any = OneHotEncoder(
            sparse_output=False, drop="first" if drop_first else None, dtype=float
        )
    else:
        encoder = OrdinalEncoder(dtype=float)

    encoded = encoder.fit_transform(df[columns])

    if strategy == "onehot":
        feature_names = encoder.get_feature_names_out(columns)
        encoded_df = pd.DataFrame(encoded, columns=feature_names, index=df.index)
    else:
        encoded_df = pd.DataFrame(encoded, columns=columns, index=df.index)

    return pd.concat([df[[id_col]], encoded_df], axis=1)


def weight_interactions_by_recency(
    df: pd.DataFrame,
    *,
    timestamp_col: str,
    user_col: str,
    item_col: str,
    value_col: str = "weight",
    decay: str = "exponential",
    half_life_days: float = 30.0,
    reference_time: pd.Timestamp | str | None = None,
) -> pd.DataFrame:
    """Return a copy of *df* with an added numeric *value_col* that decays with event age.

    Parameters
    ----------
    df: event DataFrame with timestamp, user, and item columns.
    timestamp_col: column of timestamps (datetime-like).
    user_col, item_col: retained untouched.
    value_col: name of the new weight column.
    decay: only "exponential" is supported in this task.
    half_life_days: number of days after which the weight halves.
    reference_time: timestamp to compute age against; defaults to the max timestamp in *df*.

    Returns
    -------
    A new DataFrame with the original columns plus *value_col* in (0, 1].
    """
    missing = [col for col in (timestamp_col, user_col, item_col) if col not in df.columns]
    if missing:
        raise InvalidRecommenderParamsError(
            f"column(s) {missing!r} are not in the input frame; "
            f"available columns: {sorted(df.columns)!r}."
        )
    if decay != "exponential":
        raise InvalidRecommenderParamsError(
            f"unknown decay {decay!r}; only 'exponential' is supported in this task."
        )
    if half_life_days <= 0:
        raise InvalidRecommenderParamsError(
            f"half_life_days must be positive; got {half_life_days!r}."
        )

    timestamps = pd.to_datetime(df[timestamp_col])
    computed_reference = (
        pd.to_datetime(reference_time) if reference_time is not None else timestamps.max()
    )
    age_days = (computed_reference - timestamps) / pd.Timedelta(days=1)
    weights = np.exp2(-age_days.to_numpy(dtype=float) / half_life_days)

    result = df.copy()
    result[value_col] = weights
    return result
