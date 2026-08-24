"""
emergentflow.recommend.metrics
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Ranking evaluation metrics for the Epic 15 recommender-systems family (Story 12.1). Small, pure,
module-private functions that score a list of recommended item ids (in rank order) against a set
of relevant (held-out) item ids. Every function returns ``0.0`` for degenerate inputs (``k <= 0``,
empty recommended list, empty relevant set) so callers never need to guard against ``NaN``.
"""

from __future__ import annotations

import math
from typing import Any


def _precision_at_k(recommended: list[Any], relevant: set[Any], k: int) -> float:
    """Fraction of the top-k recommended items that are relevant. 0.0 if k <= 0."""
    if k <= 0 or not recommended:
        return 0.0
    n_relevant = sum(1 for item in recommended[:k] if item in relevant)
    return n_relevant / k


def _recall_at_k(recommended: list[Any], relevant: set[Any], k: int) -> float:
    """Fraction of relevant items captured in the top-k recommended items.
    0.0 if ``relevant`` is empty (nothing to recall)."""
    if k <= 0 or not recommended or not relevant:
        return 0.0
    n_relevant = sum(1 for item in recommended[:k] if item in relevant)
    return n_relevant / len(relevant)


def _ndcg_at_k(recommended: list[Any], relevant: set[Any], k: int) -> float:
    """Normalized discounted cumulative gain at k, binary relevance.
    DCG = sum over i in [0, k) of (1 if recommended[i] in relevant else 0) / log2(i + 2).
    IDCG = DCG of the ideal ordering (all relevant items first, up to k).
    Duplicate recommended items are counted once (only the first occurrence of each
    relevant item contributes), so repeated relevant items do not inflate the score.
    Returns DCG / IDCG, or 0.0 if IDCG is 0 (no relevant items)."""
    if k <= 0 or not recommended:
        return 0.0
    n_positions = min(k, len(recommended))
    dcg = 0.0
    seen = set()
    for i in range(n_positions):
        if recommended[i] in relevant and recommended[i] not in seen:
            seen.add(recommended[i])
            dcg += 1.0 / math.log2(i + 2)
    # The ideal DCG is bounded by the number of positions actually scored
    # (``n_positions``): a short recommended list cannot place more than that many
    # relevant items, so scoring it against an IDCG built from the whole relevant
    # set (or k) would underrate an otherwise-perfect list whenever
    # ``len(recommended) < len(relevant)``.
    n_rel = min(len(relevant), n_positions)
    if n_rel == 0:
        return 0.0
    idcg = sum(1.0 / math.log2(i + 2) for i in range(n_rel))
    return dcg / idcg if idcg > 0 else 0.0


def _hit(recommended: list[Any], relevant: set[Any], k: int) -> float:
    """1.0 if any of the top-k recommended items is relevant, else 0.0."""
    if k <= 0 or not recommended or not relevant:
        return 0.0
    return 1.0 if any(item in relevant for item in recommended[:k]) else 0.0


def _average_precision_at_k(recommended: list[Any], relevant: set[Any], k: int) -> float:
    """Average precision at k: mean of precision@i for each i (1-indexed) where
    recommended[i-1] is relevant, i in [1, k]. Denominator is min(k, len(relevant)) if
    relevant is non-empty, else return 0.0 (no relevant items -> undefined AP, define as 0.0).
    Duplicate recommended items are counted once: only the first occurrence of each relevant
    item contributes a hit, so repeated relevant items do not inflate the precision sum."""
    if k <= 0 or not recommended or not relevant:
        return 0.0
    n_relevant_total = min(k, len(relevant))
    score = 0.0
    n_hits = 0
    seen = set()
    for i in range(min(k, len(recommended))):
        if recommended[i] in relevant and recommended[i] not in seen:
            seen.add(recommended[i])
            n_hits += 1
            score += n_hits / (i + 1)
    return score / n_relevant_total


def _mrr_at_k(recommended: list[Any], relevant: set[Any], k: int) -> float:
    """Mean reciprocal rank at k: 1.0 / rank of the first relevant item in the top-k
    recommended items (rank is 1-based). 0.0 if k <= 0, recommended is empty, relevant is
    empty, or no relevant item appears in the top-k."""
    if k <= 0 or not recommended or not relevant:
        return 0.0
    for i in range(min(k, len(recommended))):
        if recommended[i] in relevant:
            return 1.0 / (i + 1)
    return 0.0


def _auc_at_k(recommended: list[Any], relevant: set[Any], k: int) -> float:
    """Ranking AUC over the top-k recommended items: for every pair (rel_item, nonrel_item)
    both in the top-k, count 1 if the relevant item is ranked before the non-relevant item,
    0.5 if tied, 0 otherwise; divide by the total number of such pairs. 0.0 when the
    denominator is 0 (no relevant or no non-relevant items in the top-k, k <= 0, or empty
    input)."""
    if k <= 0 or not recommended or not relevant:
        return 0.0
    topk = recommended[:k]
    relevant_in_topk = [item for item in topk if item in relevant]
    nonrelevant_in_topk = [item for item in topk if item not in relevant]
    denominator = len(relevant_in_topk) * len(nonrelevant_in_topk)
    if denominator == 0:
        return 0.0
    score = 0.0
    for rel_item in relevant_in_topk:
        for nonrel_item in nonrelevant_in_topk:
            rel_rank = topk.index(rel_item)
            nonrel_rank = topk.index(nonrel_item)
            if rel_rank < nonrel_rank:
                score += 1.0
            elif rel_rank == nonrel_rank:
                score += 0.5
    return score / denominator
