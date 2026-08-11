"""
emergentflow.recommend.sequences
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Session/sequence-shaped interaction data for sequential recommenders (Epic 15).

Provides :func:`build_sequences`, the builder transform that turns a tidy event DataFrame
into a :class:`~emergentflow.recommend.models.SequenceDataset`: one chronologically-ordered
item-index sequence per session.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from emergentflow.recommend.errors import InvalidRecommenderParamsError
from emergentflow.recommend.models import SequenceDataset

__all__ = ["build_sequences"]


def build_sequences(
    df: pd.DataFrame,
    *,
    user_col: str,
    item_col: str,
    session_col: str | None = None,
    timestamp_col: str | None = None,
    max_seq_len: int = 50,
    min_seq_len: int = 2,
) -> SequenceDataset:
    """Build a SequenceDataset from an event DataFrame.

    Each session becomes one sequence of item indices. If ``session_col`` is None,
    each user is treated as one session. Sequences are sorted by ``timestamp_col`` when
    provided. Sequences shorter than ``min_seq_len`` are dropped.

    Parameters
    ----------
    df: tidy event DataFrame with user and item columns (and optionally session/
        timestamp columns).
    user_col: column identifying the user.
    item_col: column identifying the item.
    session_col: optional column identifying the session; when None, each user is treated
        as one session.
    timestamp_col: optional column used to order events within a session chronologically.
    max_seq_len: maximum sequence length; longer sequences are truncated to the last
        ``max_seq_len`` items.
    min_seq_len: minimum sequence length; sequences shorter than this are dropped.

    Returns
    -------
    SequenceDataset: one sequence per session, items mapped to deterministic sorted
        indices in ``[0, n_items)``.

    Raises
    ------
    InvalidRecommenderParamsError
        If ``user_col``/``item_col`` (or ``session_col``/``timestamp_col`` when provided)
        are absent from *df*, or ``max_seq_len < min_seq_len``/``min_seq_len < 2``.
    """
    required = [user_col, item_col]
    if session_col is not None:
        required.append(session_col)
    if timestamp_col is not None:
        required.append(timestamp_col)
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise InvalidRecommenderParamsError(
            f"column(s) {missing!r} are not in the input frame; "
            f"available columns: {sorted(df.columns)!r}."
        )
    if not (max_seq_len >= min_seq_len >= 2):
        raise InvalidRecommenderParamsError(
            f"require max_seq_len >= min_seq_len >= 2; got max_seq_len={max_seq_len!r}, "
            f"min_seq_len={min_seq_len!r}."
        )

    item_ids = sorted(df[item_col].unique().tolist())
    item_index = {item_id: i for i, item_id in enumerate(item_ids)}

    group_col = session_col if session_col is not None else user_col

    sequences: list[list[int]] = []
    session_ids: list[Any] = []
    for session_id, group in df.groupby(group_col, sort=False):
        if timestamp_col is not None:
            group = group.sort_values(timestamp_col, kind="stable")
        seq = [item_index[item] for item in group[item_col].tolist()]
        seq = seq[-max_seq_len:]
        if len(seq) >= min_seq_len:
            sequences.append(seq)
            session_ids.append(session_id)

    return SequenceDataset(
        sequences=sequences,
        session_ids=session_ids,
        item_ids=item_ids,
        item_index=item_index,
        max_seq_len=max_seq_len,
    )
