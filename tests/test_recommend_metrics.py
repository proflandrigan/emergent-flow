"""Unit tests for the MRR@K and ranking AUC metric helpers in
``emergentflow.recommend.metrics``."""

from emergentflow.recommend.metrics import _auc_at_k, _mrr_at_k


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
