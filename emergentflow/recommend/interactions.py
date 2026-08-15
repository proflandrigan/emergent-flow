"""
emergentflow.recommend.interactions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
InteractionMatrix: the sparse user-item interaction representation the recommend family's fit
archetypes consume (Epic 15, Story 2). Wraps a scipy CSR sparse matrix plus bidirectional
user/item id<->index maps and metadata. The raw sparse matrix is never serialized -- inspectable
via a tidy summary dict (n_users, n_items, n_interactions, density, implicit flag) on the
result-payload contract, mirroring how FittedStatsModel/FittedModel degrade their live model
field.

Interaction matrices are sparse by construction and that is load-bearing: a 100k-user x
50k-item matrix is 5 billion entries dense but typically <0.1% non-zero. Converting to dense is a
correctness bug for any non-toy dataset (see docs/adr/0021-recommender-systems-architecture.md).
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from scipy import sparse

from .errors import InvalidRecommenderParamsError


@dataclass
class InteractionMatrix:
    """A sparse user-item interaction matrix plus the id<->index maps needed to interpret it.

    Attributes
    ----------
    matrix: scipy CSR sparse matrix, shape ``(n_users, n_items)``. Never densified.
    user_ids: row index position -> original user id, in row order.
    item_ids: column index position -> original item id, in column order.
    user_index: original user id -> row index (the inverse of ``user_ids``).
    item_index: original item id -> column index (the inverse of ``item_ids``).
    implicit: whether values represent implicit feedback (counts/binary presence) rather than
        explicit ratings.
    """

    matrix: sparse.csr_matrix
    user_ids: list[Any]
    item_ids: list[Any]
    user_index: dict[Any, int] = field(default_factory=dict)
    item_index: dict[Any, int] = field(default_factory=dict)
    implicit: bool = True

    def __post_init__(self) -> None:
        if not self.user_index:
            self.user_index = {uid: i for i, uid in enumerate(self.user_ids)}
        if not self.item_index:
            self.item_index = {iid: i for i, iid in enumerate(self.item_ids)}

    @property
    def n_users(self) -> int:
        return self.matrix.shape[0]

    @property
    def n_items(self) -> int:
        return self.matrix.shape[1]

    @property
    def n_interactions(self) -> int:
        return int(self.matrix.nnz)

    @property
    def density(self) -> float:
        total = self.n_users * self.n_items
        return float(self.n_interactions / total) if total else 0.0

    def summary(self) -> dict[str, Any]:
        """A tidy, JSON-native summary -- the inspectable surface (the raw matrix never
        serializes on the result-payload contract)."""
        return {
            "n_users": self.n_users,
            "n_items": self.n_items,
            "n_interactions": self.n_interactions,
            "density": self.density,
            "implicit": self.implicit,
        }

    @classmethod
    def from_dataframe(
        cls,
        df: pd.DataFrame,
        *,
        user_col: str,
        item_col: str,
        value_col: str | None = None,
        implicit: bool = True,
    ) -> InteractionMatrix:
        """Build an InteractionMatrix from a tidy events/ratings DataFrame.

        The canonical constructor (Epic 15, Story 2). *df* must already be free of duplicate
        ``(user, item)`` pairs and any filtering/cold-start decisions -- that validation lives in
        the shared ``_prepare_interactions`` gate (Story 3), not here. This constructor assumes
        clean input and only assembles the sparse matrix and index maps. When ``value_col`` is
        ``None``, every present interaction gets an implicit value of ``1.0``. Does not mutate
        *df*. User and item ids are sorted for deterministic row/column ordering.
        """

        def _sorted_ids(series: pd.Series) -> list[Any]:
            unique = series.unique().tolist()
            types = {type(v) for v in unique}
            if len(types) > 1:
                raise InvalidRecommenderParamsError(
                    f"{series.name} ids have mixed types ({sorted(t.__name__ for t in types)!r}); "
                    "all user/item ids must share a single comparable type."
                )
            return sorted(unique)

        user_ids = _sorted_ids(df[user_col])
        item_ids = _sorted_ids(df[item_col])
        user_index = {uid: i for i, uid in enumerate(user_ids)}
        item_index = {iid: i for i, iid in enumerate(item_ids)}

        rows = df[user_col].map(user_index).to_numpy()
        cols = df[item_col].map(item_index).to_numpy()
        values = (
            df[value_col].to_numpy(dtype=float)
            if value_col is not None
            else np.ones(len(df), dtype=float)
        )

        matrix = sparse.csr_matrix((values, (rows, cols)), shape=(len(user_ids), len(item_ids)))

        return cls(
            matrix=matrix,
            user_ids=user_ids,
            item_ids=item_ids,
            user_index=user_index,
            item_index=item_index,
            implicit=implicit,
        )


_VALID_AGG = frozenset({"sum", "mean", "max", "last"})
_VALID_COLD_START = frozenset({"error", "warn-and-skip", "include"})


def _prepare_interactions(
    df: pd.DataFrame,
    *,
    user_col: str,
    item_col: str,
    value_col: str | None = None,
    implicit: bool = True,
    agg: str = "sum",
    min_user_interactions: int = 0,
    min_item_interactions: int = 0,
    cold_start_mode: str = "warn-and-skip",
) -> InteractionMatrix:
    """Validate and normalise a raw events/ratings DataFrame into a deduplicated InteractionMatrix.

    The single shared validation gate for the recommend family (Epic 15, Story 3). See the
    module-level docstring of ``emergentflow.recommend.interactions`` for the full contract.

    ``min_user_interactions``/``min_item_interactions`` filtering (``cold_start_mode=
    "warn-and-skip"``) is applied to a fixed point: dropping low-count items can knock a
    previously-fine user's remaining interaction count below ``min_user_interactions`` (and
    vice versa), so counts are recomputed and the drop repeated until neither threshold is
    violated by what remains. ``cold_start_mode="error"`` only inspects the pre-filter counts
    and raises if *any* user/item would need dropping -- it never partially filters, so no
    cascade can occur there.

    Never mutates *df*.
    """
    columns = set(df.columns)

    if user_col not in columns:
        raise InvalidRecommenderParamsError(
            f"column {user_col!r} is not in the input frame; "
            f"available columns: {sorted(columns)!r}."
        )
    if item_col not in columns:
        raise InvalidRecommenderParamsError(
            f"column {item_col!r} is not in the input frame; "
            f"available columns: {sorted(columns)!r}."
        )
    if value_col is not None and value_col not in columns:
        raise InvalidRecommenderParamsError(
            f"column {value_col!r} is not in the input frame; "
            f"available columns: {sorted(columns)!r}."
        )

    if agg not in _VALID_AGG:
        raise InvalidRecommenderParamsError(
            f"invalid agg {agg!r}; expected one of {sorted(_VALID_AGG)!r}."
        )
    if cold_start_mode not in _VALID_COLD_START:
        raise InvalidRecommenderParamsError(
            f"invalid cold_start_mode {cold_start_mode!r}; "
            f"expected one of {sorted(_VALID_COLD_START)!r}."
        )

    resolved = df.copy(deep=False)

    if value_col is not None:
        deduped = resolved.groupby([user_col, item_col], as_index=False)[value_col].agg(agg)
        resolved_value_col = value_col
    else:
        deduped = resolved.groupby([user_col, item_col], as_index=False).size()
        deduped.rename(columns={"size": "__interaction_count__"}, inplace=True)
        resolved_value_col = "__interaction_count__"

    if min_user_interactions > 0 or min_item_interactions > 0:
        if cold_start_mode == "error":
            item_counts = deduped[item_col].value_counts()
            user_counts = deduped[user_col].value_counts()
            low_items = item_counts[item_counts < min_item_interactions]
            low_users = user_counts[user_counts < min_user_interactions]
            if not low_items.empty or not low_users.empty:
                parts = []
                if not low_users.empty:
                    parts.append(
                        f"{len(low_users)} user(s) below "
                        f"min_user_interactions={min_user_interactions}"
                    )
                if not low_items.empty:
                    parts.append(
                        f"{len(low_items)} item(s) below "
                        f"min_item_interactions={min_item_interactions}"
                    )
                raise InvalidRecommenderParamsError(
                    f"cold-start filter would drop {'; '.join(parts)}."
                )
        elif cold_start_mode == "warn-and-skip":
            dropped_users: set[Any] = set()
            dropped_items: set[Any] = set()
            while True:
                item_counts = deduped[item_col].value_counts()
                user_counts = deduped[user_col].value_counts()
                low_items = item_counts[item_counts < min_item_interactions]
                low_users = user_counts[user_counts < min_user_interactions]
                if low_items.empty and low_users.empty:
                    break
                dropped_items.update(low_items.index)
                dropped_users.update(low_users.index)
                if not low_items.empty:
                    deduped = deduped[~deduped[item_col].isin(low_items.index)]
                if not low_users.empty:
                    deduped = deduped[~deduped[user_col].isin(low_users.index)]

            if dropped_users or dropped_items:
                parts = []
                if dropped_users:
                    parts.append(
                        f"{len(dropped_users)} user(s) below "
                        f"min_user_interactions={min_user_interactions}"
                    )
                if dropped_items:
                    parts.append(
                        f"{len(dropped_items)} item(s) below "
                        f"min_item_interactions={min_item_interactions}"
                    )
                warnings.warn(
                    f"dropping {'; '.join(parts)} (cold_start_mode='warn-and-skip').",
                    UserWarning,
                    stacklevel=2,
                )

    return InteractionMatrix.from_dataframe(
        deduped,
        user_col=user_col,
        item_col=item_col,
        value_col=resolved_value_col,
        implicit=implicit,
    )
