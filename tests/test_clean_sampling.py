"""Tests for emergentflow.clean.sampling (Epic 16, Story 9).

Covers ``ef.clean.sample_rows`` (a thin, reproducible wrapper over ``pandas.DataFrame.sample``,
always run) and ``ef.clean.fuzzy_join`` (a string-similarity keyed merge behind the optional
``[fuzzy]`` extra). Neither mutates its input.
"""

from __future__ import annotations

import pandas as pd
import pytest

from emergentflow.api import is_inspectable
from emergentflow.clean import CleanError, ColumnCollisionError, UnknownColumnError
from emergentflow.clean.sampling import fuzzy_join, sample_rows


def _df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "id": list(range(12)),
            "grp": ["a"] * 6 + ["b"] * 6,
            "value": [float(i) for i in range(12)],
        }
    )


def _left() -> pd.DataFrame:
    return pd.DataFrame({"name": ["Apple Inc", "Microsft Corp", "Zzzz Ltd"], "lid": [1, 2, 3]})


def _right() -> pd.DataFrame:
    return pd.DataFrame({"company": ["Apple Inc.", "Microsoft Corp"], "rid": [10, 20]})


# --- sample_rows ---


def test_sample_random_n() -> None:
    result = sample_rows(_df(), mode="random", n=4)
    assert result.shape[0] == 4


def test_sample_random_frac() -> None:
    result = sample_rows(_df(), mode="random", frac=0.5)
    assert result.shape[0] == 6


def test_sample_is_deterministic_for_a_given_seed() -> None:
    result_a = sample_rows(_df(), mode="random", n=4, seed=7)
    result_b = sample_rows(_df(), mode="random", n=4, seed=7)
    pd.testing.assert_frame_equal(result_a, result_b)


def test_sample_different_seeds_differ() -> None:
    result_a = sample_rows(_df(), mode="random", n=4, seed=1)
    result_b = sample_rows(_df(), mode="random", n=4, seed=2)
    assert set(result_a["id"]) != set(result_b["id"])


def test_sample_is_non_mutating() -> None:
    df = _df()
    snapshot = df.copy()
    sample_rows(df, mode="random", n=4, seed=1)
    pd.testing.assert_frame_equal(df, snapshot)


def test_sample_top_n_takes_first_rows() -> None:
    result = sample_rows(_df(), mode="top_n", n=3)
    assert list(result["id"]) == [0, 1, 2]


def test_sample_stratified_per_group_n() -> None:
    result = sample_rows(_df(), mode="stratified", by=["grp"], n=2, seed=3)
    assert result.shape[0] == 4
    assert result.groupby("grp").size().tolist() == [2, 2]


def test_sample_stratified_frac() -> None:
    result = sample_rows(_df(), mode="stratified", by=["grp"], frac=0.5, seed=3)
    assert result.shape[0] == 6
    assert result.groupby("grp").size().tolist() == [3, 3]


def test_sample_stratified_clamps_to_group_size() -> None:
    result = sample_rows(_df(), mode="stratified", by=["grp"], n=100, seed=3)
    assert result.shape[0] == 12


def test_sample_stratified_is_deterministic() -> None:
    result_a = sample_rows(_df(), mode="stratified", by=["grp"], n=2, seed=5)
    result_b = sample_rows(_df(), mode="stratified", by=["grp"], n=2, seed=5)
    pd.testing.assert_frame_equal(result_a, result_b)


def test_sample_unknown_mode() -> None:
    with pytest.raises(CleanError):
        sample_rows(_df(), mode="bogus", n=4)


def test_sample_top_n_without_n() -> None:
    with pytest.raises(CleanError):
        sample_rows(_df(), mode="top_n")


def test_sample_top_n_with_frac() -> None:
    with pytest.raises(CleanError):
        sample_rows(_df(), mode="top_n", n=3, frac=0.5)


def test_sample_random_both_n_and_frac() -> None:
    with pytest.raises(CleanError):
        sample_rows(_df(), mode="random", n=3, frac=0.5)


def test_sample_random_neither() -> None:
    with pytest.raises(CleanError):
        sample_rows(_df(), mode="random")


def test_sample_negative_n() -> None:
    with pytest.raises(CleanError):
        sample_rows(_df(), mode="random", n=-1)


def test_sample_frac_out_of_range() -> None:
    with pytest.raises(CleanError):
        sample_rows(_df(), mode="random", frac=1.5)


def test_sample_stratified_without_by() -> None:
    with pytest.raises(CleanError):
        sample_rows(_df(), mode="stratified", n=2)


def test_sample_stratified_unknown_column() -> None:
    with pytest.raises(UnknownColumnError):
        sample_rows(_df(), mode="stratified", by=["nope"], n=2)


# --- fuzzy_join ---


def test_fuzzy_join_matches_close_strings() -> None:
    pytest.importorskip("rapidfuzz")
    result = fuzzy_join(_left(), _right(), left_on="name", right_on="company", threshold=80)
    matched_companies = set(result.loc[result["rid"].notna(), "company"])
    assert "Apple Inc." in matched_companies
    assert "Microsoft Corp" in matched_companies


def test_fuzzy_join_inner_drops_unmatched() -> None:
    pytest.importorskip("rapidfuzz")
    result = fuzzy_join(
        _left(), _right(), left_on="name", right_on="company", threshold=80, how="inner"
    )
    assert "Zzzz Ltd" not in set(result["name"])


def test_fuzzy_join_left_keeps_unmatched() -> None:
    pytest.importorskip("rapidfuzz")
    result = fuzzy_join(
        _left(), _right(), left_on="name", right_on="company", threshold=80, how="left"
    )
    unmatched = result[result["name"] == "Zzzz Ltd"]
    assert len(unmatched) == 1
    assert unmatched["rid"].isna().all()


def test_fuzzy_join_adds_score_column() -> None:
    pytest.importorskip("rapidfuzz")
    result = fuzzy_join(
        _left(), _right(), left_on="name", right_on="company", threshold=80, how="inner"
    )
    assert "match_score" in result.columns
    assert (result["match_score"] >= 80).all()


def test_fuzzy_join_threshold_excludes() -> None:
    pytest.importorskip("rapidfuzz")
    result_low = fuzzy_join(
        _left(), _right(), left_on="name", right_on="company", threshold=50, how="inner"
    )
    result_high = fuzzy_join(
        _left(), _right(), left_on="name", right_on="company", threshold=99, how="inner"
    )
    assert result_high.shape[0] <= result_low.shape[0]


def test_fuzzy_join_one_to_many() -> None:
    pytest.importorskip("rapidfuzz")
    result_one = fuzzy_join(
        _left(), _right(), left_on="name", right_on="company", threshold=50, limit=1
    )
    result_many = fuzzy_join(
        _left(), _right(), left_on="name", right_on="company", threshold=50, limit=2
    )
    assert result_many.shape[0] >= result_one.shape[0]


def test_fuzzy_join_is_non_mutating() -> None:
    pytest.importorskip("rapidfuzz")
    left, right = _left(), _right()
    snap_left, snap_right = left.copy(), right.copy()
    fuzzy_join(left, right, left_on="name", right_on="company")
    pd.testing.assert_frame_equal(left, snap_left)
    pd.testing.assert_frame_equal(right, snap_right)


def test_fuzzy_join_suffixes_on_overlap() -> None:
    pytest.importorskip("rapidfuzz")
    left = _left().rename(columns={"lid": "id"})
    right = _right().rename(columns={"rid": "id"})
    result = fuzzy_join(left, right, left_on="name", right_on="company", threshold=50)
    assert "id_x" in result.columns
    assert "id_y" in result.columns


def test_fuzzy_join_unknown_scorer() -> None:
    pytest.importorskip("rapidfuzz")
    with pytest.raises(CleanError):
        fuzzy_join(_left(), _right(), left_on="name", right_on="company", scorer="bogus")


def test_fuzzy_join_unknown_how() -> None:
    pytest.importorskip("rapidfuzz")
    with pytest.raises(CleanError):
        fuzzy_join(_left(), _right(), left_on="name", right_on="company", how="bogus")


def test_fuzzy_join_bad_limit() -> None:
    pytest.importorskip("rapidfuzz")
    with pytest.raises(CleanError):
        fuzzy_join(_left(), _right(), left_on="name", right_on="company", limit=0)


def test_fuzzy_join_bad_threshold() -> None:
    pytest.importorskip("rapidfuzz")
    with pytest.raises(CleanError):
        fuzzy_join(_left(), _right(), left_on="name", right_on="company", threshold=150)


def test_fuzzy_join_unknown_key_column() -> None:
    pytest.importorskip("rapidfuzz")
    with pytest.raises(UnknownColumnError):
        fuzzy_join(_left(), _right(), left_on="nope", right_on="company")


def test_fuzzy_join_score_column_collision() -> None:
    pytest.importorskip("rapidfuzz")
    left = _left().assign(match_score=1.0)
    with pytest.raises(ColumnCollisionError):
        fuzzy_join(left, _right(), left_on="name", right_on="company")


# --- shared ---


def test_sampling_results_are_inspectable() -> None:
    sample_result = sample_rows(_df(), mode="random", n=4, seed=1)
    assert is_inspectable(sample_result) is True

    if pytest.importorskip("rapidfuzz"):
        fuzzy_result = fuzzy_join(_left(), _right(), left_on="name", right_on="company")
        assert is_inspectable(fuzzy_result) is True


def test_fuzzy_join_score_column_collides_with_suffix_renamed_column() -> None:
    """The score column must be checked against the POST-suffix-rename names.

    Both frames carry a ``score`` column, so it is renamed to ``score_x``/``score_y``; a
    caller asking for ``score_column="score_x"`` would otherwise silently overwrite the
    renamed left-hand column instead of raising.
    """
    pytest.importorskip("rapidfuzz")
    left = pd.DataFrame({"name": ["Apple Inc"], "score": [1]})
    right = pd.DataFrame({"company": ["Apple Inc."], "score": [2]})
    with pytest.raises(ColumnCollisionError, match="collides"):
        fuzzy_join(left, right, left_on="name", right_on="company", score_column="score_x")
