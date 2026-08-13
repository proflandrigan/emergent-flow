"""Unit tests for the MRR@K, ranking AUC and NDCG@K metric helpers in
``emergentflow.recommend.metrics``."""

from emergentflow.recommend.metrics import _auc_at_k, _mrr_at_k, _ndcg_at_k


def test_mrr_empty_and_zero_k_return_zero():
    assert _mrr_at_k([], {1, 2}, 5) == 0.0
    assert _mrr_at_k([1, 2, 3], set(), 5) == 0.0
    assert _mrr_at_k([1, 2, 3], {1, 2}, 0) == 0.0
    assert _mrr_at_k([1, 2, 3], {1, 2}, -1) == 0.0


def test_mrr_relevant_at_rank_one():
    assert _mrr_at_k([1, 2, 3], {1}, 5) == 1.0


def test_mrr_relevant_at_rank_two():
    assert _mrr_at_k([1, 2, 3], {2}, 5) == 0.5


def test_mrr_relevant_absent():
    assert _mrr_at_k([1, 2, 3], {9}, 5) == 0.0


def test_mrr_relevant_beyond_k():
    assert _mrr_at_k([1, 2, 3], {3}, 2) == 0.0


def test_auc_empty_and_zero_k_return_zero():
    assert _auc_at_k([], {1, 2}, 5) == 0.0
    assert _auc_at_k([1, 2, 3], set(), 5) == 0.0
    assert _auc_at_k([1, 2, 3], {1, 2}, 0) == 0.0
    assert _auc_at_k([1, 2, 3], {1, 2}, -1) == 0.0


def test_auc_all_relevant_first_is_one():
    assert _auc_at_k([1, 2, 3, 4], {1, 2}, 5) == 1.0


def test_auc_all_nonrelevant_first_is_zero():
    assert _auc_at_k([1, 2, 3, 4], {3, 4}, 5) == 0.0


def test_auc_perfectly_interleaved_is_half():
    assert _auc_at_k([1, 2, 3, 4], {1, 4}, 5) == 0.5


def test_auc_no_relevant_in_topk_is_zero():
    assert _auc_at_k([1, 2, 3, 4], {9}, 5) == 0.0


def test_ndcg_perfect_short_list_is_one():
    # Every recommended item is relevant, but the relevant set has MORE items than
    # the recommended list. IDCG must not overshoot the achievable positions: a
    # perfect (short) recommendation should score 1.0, not be penalised for
    # relevant items the list simply never had room for.
    assert _ndcg_at_k([1], {1, 2, 3}, 10) == 1.0
    assert _ndcg_at_k([1, 2], {1, 2, 3, 4, 5}, 10) == 1.0


def test_ndcg_matches_full_length_when_list_fills_k():
    # When the recommended list is at least as long as k, the result is the standard
    # NDCG@k over the whole relevant set (regression guard for the pre-fix path).
    assert _ndcg_at_k([1, 2, 3], {1, 2, 3}, 3) == 1.0
    assert _ndcg_at_k([1, 5, 3], {1, 2, 9}, 3) > 0.0
    assert _ndcg_at_k([1, 2, 3], {1, 2, 3, 4}, 3) == 1.0


def test_ndcg_empty_and_zero_k_return_zero():
    assert _ndcg_at_k([], {1, 2}, 5) == 0.0
    assert _ndcg_at_k([1, 2, 3], set(), 5) == 0.0
    assert _ndcg_at_k([1, 2, 3], {1, 2}, 0) == 0.0
    assert _ndcg_at_k([1, 2, 3], {1, 2}, -1) == 0.0
