"""Tests for emergentflow.clean (Epic 1, Story 8).

Covers ``ef.clean.impute_missing``: a thin wrapper over
``sklearn.impute.SimpleImputer`` that fills missing values column-wise while
remaining pure (never mutating its input DataFrame).
"""

from __future__ import annotations

import pandas as pd
import pytest

from emergentflow.api import PUBLIC_OPS
from emergentflow.clean import (
    cast_types,
    drop_missing,
    encode_lists,
    explode_lists,
    filter_rows,
    impute_missing,
    merge,
    select_columns,
    semi_join,
)


def test_impute_mean_fills_nan() -> None:
    df = pd.DataFrame({"a": [1.0, None, 3.0]})
    result = impute_missing(df, strategy="mean")
    assert result["a"].iloc[1] == 2.0
    assert not result.isna().any().any()


def test_impute_does_not_mutate_input() -> None:
    df = pd.DataFrame({"a": [1.0, None, 3.0]})
    original = df.copy()
    impute_missing(df, strategy="mean")
    assert original.isna().any().any()
    pd.testing.assert_frame_equal(df, original)


def test_impute_bad_strategy_raises() -> None:
    df = pd.DataFrame({"a": [1.0, None, 3.0]})
    with pytest.raises(ValueError):
        impute_missing(df, strategy="bogus")


def test_impute_unknown_column_raises() -> None:
    df = pd.DataFrame({"a": [1.0, None, 3.0]})
    with pytest.raises(ValueError):
        impute_missing(df, columns=["nope"])


def test_impute_returns_dataframe() -> None:
    df = pd.DataFrame({"a": [1.0, None, 3.0]})
    result = impute_missing(df, strategy="mean")
    assert isinstance(result, pd.DataFrame)


def test_impute_registered_as_public_op() -> None:
    assert "ef.clean.impute_missing" in PUBLIC_OPS


def test_drop_missing_rows_default() -> None:
    df = pd.DataFrame({"a": [1.0, None, 3.0]})
    result = drop_missing(df)
    assert len(result) == 2
    assert not result.isna().any().any()


def test_drop_missing_columns() -> None:
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [None, None, None]})
    result = drop_missing(df, axis="columns")
    assert list(result.columns) == ["a"]


def test_drop_missing_how_all() -> None:
    df = pd.DataFrame({"a": [1.0, None, 3.0], "b": [None, None, 4.0]})
    result = drop_missing(df, how="all")
    # only the all-NA row (index 1) is dropped; partial-NA rows are kept
    assert len(result) == 2
    assert 1 not in result.index


def test_drop_missing_subset() -> None:
    df = pd.DataFrame({"a": [1.0, None, 3.0], "b": [1.0, 2.0, 3.0]})
    result = drop_missing(df, subset=["b"])
    assert len(result) == 3


def test_drop_missing_does_not_mutate_input() -> None:
    df = pd.DataFrame({"a": [1.0, None, 3.0]})
    original = df.copy()
    drop_missing(df)
    pd.testing.assert_frame_equal(df, original)


def test_drop_missing_bad_axis_raises() -> None:
    df = pd.DataFrame({"a": [1.0, None, 3.0]})
    with pytest.raises(ValueError):
        drop_missing(df, axis="bogus")


def test_drop_missing_bad_how_raises() -> None:
    df = pd.DataFrame({"a": [1.0, None, 3.0]})
    with pytest.raises(ValueError):
        drop_missing(df, how="bogus")


def test_drop_missing_unknown_subset_column_raises() -> None:
    df = pd.DataFrame({"a": [1.0, None, 3.0]})
    with pytest.raises(ValueError):
        drop_missing(df, subset=["nope"])


def test_drop_missing_returns_dataframe() -> None:
    df = pd.DataFrame({"a": [1.0, None, 3.0]})
    result = drop_missing(df)
    assert isinstance(result, pd.DataFrame)


def test_drop_missing_registered_as_public_op() -> None:
    assert "ef.clean.drop_missing" in PUBLIC_OPS


def test_select_columns_keep_subset_preserves_order() -> None:
    df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6], "c": [7, 8, 9]})
    result = select_columns(df, columns=["c", "a"])
    assert list(result.columns) == ["c", "a"]
    assert list(result["c"]) == [7, 8, 9]
    assert list(result["a"]) == [1, 2, 3]


def test_select_columns_drop_true_removes_named_cols() -> None:
    df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6], "c": [7, 8, 9]})
    result = select_columns(df, columns=["b"], drop=True)
    assert list(result.columns) == ["a", "c"]


def test_select_columns_unknown_column_raises() -> None:
    df = pd.DataFrame({"a": [1, 2, 3]})
    with pytest.raises(ValueError):
        select_columns(df, columns=["nope"])


def test_select_columns_empty_columns_raises() -> None:
    df = pd.DataFrame({"a": [1, 2, 3]})
    with pytest.raises(ValueError):
        select_columns(df, columns=[])


def test_select_columns_registered_as_public_op() -> None:
    assert "ef.clean.select_columns" in PUBLIC_OPS


def test_select_columns_does_not_mutate_input() -> None:
    df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
    original = df.copy()
    select_columns(df, columns=["a"])
    pd.testing.assert_frame_equal(df, original)


def test_cast_types_int_to_float() -> None:
    df = pd.DataFrame({"a": [1, 2, 3]})
    result = cast_types(df, dtypes={"a": "float"})
    assert result["a"].dtype == float
    assert list(result["a"]) == [1.0, 2.0, 3.0]


def test_cast_types_unknown_column_raises() -> None:
    df = pd.DataFrame({"a": [1, 2, 3]})
    with pytest.raises(ValueError):
        cast_types(df, dtypes={"nope": "float"})


def test_cast_types_unknown_dtype_raises() -> None:
    df = pd.DataFrame({"a": [1, 2, 3]})
    with pytest.raises(ValueError):
        cast_types(df, dtypes={"a": "unknown"})


def test_cast_types_empty_dtypes_raises() -> None:
    df = pd.DataFrame({"a": [1, 2, 3]})
    with pytest.raises(ValueError):
        cast_types(df, dtypes={})


def test_cast_types_registered_as_public_op() -> None:
    assert "ef.clean.cast_types" in PUBLIC_OPS


def test_cast_types_does_not_mutate_input() -> None:
    df = pd.DataFrame({"a": [1, 2, 3]})
    original = df.copy()
    cast_types(df, dtypes={"a": "float"})
    pd.testing.assert_frame_equal(df, original)


def test_filter_rows_gt_keeps_right_rows() -> None:
    df = pd.DataFrame({"a": [1, 2, 3, 4]})
    result = filter_rows(df, column="a", operator=">", value=2)
    assert list(result["a"]) == [3, 4]


def test_filter_rows_eq_on_string_column() -> None:
    df = pd.DataFrame({"name": ["alice", "bob", "alice"]})
    result = filter_rows(df, column="name", operator="==", value="alice")
    assert list(result["name"]) == ["alice", "alice"]


def test_filter_rows_isin_keeps_matching_rows() -> None:
    df = pd.DataFrame({"a": [1, 2, 3, 4]})
    result = filter_rows(df, column="a", operator="isin", value=[2, 4])
    assert list(result["a"]) == [2, 4]


def test_filter_rows_isin_non_list_raises() -> None:
    df = pd.DataFrame({"a": [1, 2, 3]})
    with pytest.raises(ValueError, match="list value"):
        filter_rows(df, column="a", operator="isin", value=42)


def test_filter_rows_unknown_column_raises() -> None:
    df = pd.DataFrame({"a": [1, 2, 3]})
    with pytest.raises(ValueError, match="unknown column"):
        filter_rows(df, column="nope", operator="==", value=1)


def test_filter_rows_unknown_operator_raises() -> None:
    df = pd.DataFrame({"a": [1, 2, 3]})
    with pytest.raises(ValueError, match="unknown operator"):
        filter_rows(df, column="a", operator="bogus", value=1)


def test_filter_rows_registered_as_public_op() -> None:
    assert "ef.clean.filter_rows" in PUBLIC_OPS


def test_filter_rows_does_not_mutate_input() -> None:
    df = pd.DataFrame({"a": [1, 2, 3, 4]})
    original = df.copy()
    filter_rows(df, column="a", operator=">", value=2)
    pd.testing.assert_frame_equal(df, original)


def test_filter_rows_none_value_with_comparator_raises() -> None:
    df = pd.DataFrame({"a": [1, 2, 3]})
    with pytest.raises(ValueError, match="requires a non-None value"):
        filter_rows(df, column="a", operator="==")


def test_drop_missing_subset_with_column_axis_raises() -> None:
    df = pd.DataFrame({"a": [1.0, None, 3.0], "b": [1.0, 2.0, None]})
    with pytest.raises(ValueError, match="subset is only supported when axis='rows'"):
        drop_missing(df, axis="columns", subset=["a"])


class TestExplodeLists:
    def test_single_column_explode(self) -> None:
        df = pd.DataFrame({"u": [1, 2], "items": [["a", "b"], ["c"]]})
        result = explode_lists(df, columns=["items"])
        assert len(result) == 3
        assert list(result["items"]) == ["a", "b", "c"]
        assert list(result["u"]) == [1, 1, 2]

    def test_aligned_multi_column_explode(self) -> None:
        df = pd.DataFrame({"u": [1], "items": [["a", "b"]], "ts": [[10, 20]]})
        result = explode_lists(df, columns=["items", "ts"])
        assert len(result) == 2
        assert list(result["items"]) == ["a", "b"]
        assert list(result["ts"]) == [10, 20]

    def test_drop_empty_true_drops_empty_list_row(self) -> None:
        df = pd.DataFrame({"u": [1, 2], "items": [["a"], []]})
        result = explode_lists(df, columns=["items"], drop_empty=True)
        assert len(result) == 1
        assert list(result["u"]) == [1]

    def test_drop_empty_false_keeps_nan_row(self) -> None:
        df = pd.DataFrame({"u": [1, 2], "items": [["a"], []]})
        result = explode_lists(df, columns=["items"], drop_empty=False)
        assert len(result) == 2

    def test_drop_empty_true_preserves_none_element_in_nonempty_list(self) -> None:
        df = pd.DataFrame({"u": [1, 2], "items": [["a", None], ["c"]]})
        result = explode_lists(df, columns=["items"], drop_empty=True)
        assert len(result) == 3
        assert list(result["u"]) == [1, 1, 2]
        assert result["items"].tolist()[1] is None

    def test_does_not_mutate_input(self) -> None:
        df = pd.DataFrame({"u": [1, 2], "items": [["a", "b"], ["c"]]})
        original = df.copy()
        explode_lists(df, columns=["items"])
        pd.testing.assert_frame_equal(df, original)

    def test_unknown_column_raises(self) -> None:
        df = pd.DataFrame({"u": [1, 2], "items": [["a", "b"], ["c"]]})
        with pytest.raises(ValueError):
            explode_lists(df, columns=["nope"])

    def test_empty_columns_raises(self) -> None:
        df = pd.DataFrame({"u": [1, 2], "items": [["a", "b"], ["c"]]})
        with pytest.raises(ValueError):
            explode_lists(df, columns=[])


class TestEncodeLists:
    def test_basic_multi_hot(self) -> None:
        df = pd.DataFrame({"u": [1, 2], "g": [["rock", "jazz"], ["pop"]]})
        result = encode_lists(df, column="g")
        assert list(result.columns) == ["u", "g_jazz", "g_pop", "g_rock"]
        assert result.loc[0, ["g_jazz", "g_pop", "g_rock"]].tolist() == [1, 0, 1]
        assert result.loc[1, ["g_jazz", "g_pop", "g_rock"]].tolist() == [0, 1, 0]
        assert "g" not in result.columns

    def test_prefix_override(self) -> None:
        df = pd.DataFrame({"u": [1, 2], "g": [["rock", "jazz"], ["pop"]]})
        result = encode_lists(df, column="g", prefix="genre")
        assert list(result.columns) == ["u", "genre_jazz", "genre_pop", "genre_rock"]

    def test_drop_false_keeps_original_column(self) -> None:
        df = pd.DataFrame({"u": [1, 2], "g": [["rock", "jazz"], ["pop"]]})
        result = encode_lists(df, column="g", drop=False)
        assert "g" in result.columns
        assert list(result["g"]) == [["rock", "jazz"], ["pop"]]

    def test_empty_cell_yields_all_zeros(self) -> None:
        df = pd.DataFrame({"u": [1], "g": [[]]})
        result = encode_lists(df, column="g")
        assert len(result) == 1
        assert list(result.columns) == ["u"]

    def test_none_cell_mixed_with_list_yields_all_zeros_row(self) -> None:
        df = pd.DataFrame({"u": [1, 2], "g": [["rock"], None]})
        result = encode_lists(df, column="g")
        assert result.loc[0, "g_rock"] == 1
        assert result.loc[1, "g_rock"] == 0

    def test_sep_splitting(self) -> None:
        df = pd.DataFrame({"u": [1], "g": ["rock|jazz"]})
        result = encode_lists(df, column="g", sep="|")
        assert result.loc[0, "g_jazz"] == 1
        assert result.loc[0, "g_rock"] == 1

    def test_does_not_mutate_input(self) -> None:
        df = pd.DataFrame({"u": [1, 2], "g": [["rock", "jazz"], ["pop"]]})
        original = df.copy()
        encode_lists(df, column="g")
        pd.testing.assert_frame_equal(df, original)

    def test_unknown_column_raises(self) -> None:
        df = pd.DataFrame({"u": [1, 2], "g": [["rock", "jazz"], ["pop"]]})
        with pytest.raises(ValueError):
            encode_lists(df, column="nope")

    def test_mixed_unsortable_label_types_raises_value_error(self) -> None:
        df = pd.DataFrame({"u": [1, 2], "g": [[1, "a"], ["b"]]})
        with pytest.raises(ValueError, match="mutually unsortable"):
            encode_lists(df, column="g")

    def test_generated_column_colliding_with_existing_column_raises(self) -> None:
        df = pd.DataFrame({"u": [1, 2], "g_rock": [10, 20], "g": [["rock"], ["jazz"]]})
        with pytest.raises(ValueError, match="collide"):
            encode_lists(df, column="g")

    def test_generated_column_colliding_with_kept_original_column_raises(self) -> None:
        df = pd.DataFrame({"g_rock": [10, 20], "g": [["rock"], ["jazz"]]})
        with pytest.raises(ValueError, match="collide"):
            encode_lists(df, column="g", drop=False)


def test_merge_inner_on_shared_key() -> None:
    left = pd.DataFrame({"user_id": [1, 2, 3], "name": ["a", "b", "c"]})
    right = pd.DataFrame({"user_id": [2, 3, 4], "score": [10, 20, 30]})
    result = merge(left, right, on=["user_id"], how="inner")
    assert list(result["user_id"]) == [2, 3]
    assert list(result["score"]) == [10, 20]


def test_merge_left_on_right_on_different_names() -> None:
    left = pd.DataFrame({"uid": [1, 2], "name": ["a", "b"]})
    right = pd.DataFrame({"user_id": [1, 2], "score": [10, 20]})
    result = merge(left, right, left_on=["uid"], right_on=["user_id"], how="inner")
    assert list(result["name"]) == ["a", "b"]
    assert list(result["score"]) == [10, 20]


def test_merge_how_left_keeps_unmatched_left_rows() -> None:
    left = pd.DataFrame({"user_id": [1, 2, 3]})
    right = pd.DataFrame({"user_id": [2], "score": [10]})
    result = merge(left, right, on=["user_id"], how="left")
    assert len(result) == 3


def test_merge_cross_join() -> None:
    left = pd.DataFrame({"a": [1, 2]})
    right = pd.DataFrame({"b": [10, 20]})
    result = merge(left, right, how="cross")
    assert len(result) == 4


def test_merge_cross_with_keys_raises() -> None:
    left = pd.DataFrame({"a": [1]})
    right = pd.DataFrame({"a": [1]})
    with pytest.raises(ValueError, match="cross join takes no key columns"):
        merge(left, right, how="cross", on=["a"])


def test_merge_on_and_left_on_together_raises() -> None:
    left = pd.DataFrame({"a": [1]})
    right = pd.DataFrame({"a": [1]})
    with pytest.raises(ValueError, match="not both"):
        merge(left, right, on=["a"], left_on=["a"])


def test_merge_left_on_without_right_on_raises() -> None:
    left = pd.DataFrame({"a": [1]})
    right = pd.DataFrame({"a": [1]})
    with pytest.raises(ValueError, match="must be given together"):
        merge(left, right, left_on=["a"])


def test_merge_no_keys_raises() -> None:
    left = pd.DataFrame({"a": [1]})
    right = pd.DataFrame({"a": [1]})
    with pytest.raises(ValueError, match="must specify"):
        merge(left, right)


def test_merge_unknown_key_column_raises() -> None:
    left = pd.DataFrame({"a": [1]})
    right = pd.DataFrame({"a": [1]})
    with pytest.raises(ValueError, match="unknown column"):
        merge(left, right, on=["nope"])


def test_merge_unequal_left_on_right_on_length_raises() -> None:
    left = pd.DataFrame({"a": [1], "b": [1]})
    right = pd.DataFrame({"a": [1]})
    with pytest.raises(ValueError, match="same length"):
        merge(left, right, left_on=["a", "b"], right_on=["a"])


def test_merge_suffixes_disambiguate_overlapping_columns() -> None:
    left = pd.DataFrame({"user_id": [1], "value": [10]})
    right = pd.DataFrame({"user_id": [1], "value": [20]})
    result = merge(left, right, on=["user_id"], suffixes=("_left", "_right"))
    assert "value_left" in result.columns
    assert "value_right" in result.columns


def test_merge_bad_suffixes_length_raises() -> None:
    left = pd.DataFrame({"a": [1]})
    right = pd.DataFrame({"a": [1]})
    with pytest.raises(ValueError, match="suffixes must be"):
        merge(left, right, on=["a"], suffixes=("_x", "_y", "_z"))


def test_merge_validate_one_to_one_raises_on_violation() -> None:
    left = pd.DataFrame({"user_id": [1, 1]})
    right = pd.DataFrame({"user_id": [1]})
    with pytest.raises(ValueError):
        merge(left, right, on=["user_id"], validate="1:1")


def test_merge_does_not_mutate_inputs() -> None:
    left = pd.DataFrame({"user_id": [1, 2]})
    right = pd.DataFrame({"user_id": [1, 2], "score": [10, 20]})
    left_orig, right_orig = left.copy(), right.copy()
    merge(left, right, on=["user_id"])
    pd.testing.assert_frame_equal(left, left_orig)
    pd.testing.assert_frame_equal(right, right_orig)


def test_merge_registered_as_public_op() -> None:
    assert "ef.clean.merge" in PUBLIC_OPS


def test_semi_join_keep_mode_filters_to_matching_keys() -> None:
    frame = pd.DataFrame({"user_id": [1, 2, 3, 4], "event": ["a", "b", "c", "d"]})
    keys = pd.DataFrame({"user_id": [2, 4]})
    result = semi_join(frame, keys, on=["user_id"], mode="keep")
    assert list(result["user_id"]) == [2, 4]
    assert list(result["event"]) == ["b", "d"]


def test_semi_join_exclude_mode_removes_matching_keys() -> None:
    frame = pd.DataFrame({"user_id": [1, 2, 3, 4], "event": ["a", "b", "c", "d"]})
    keys = pd.DataFrame({"user_id": [2, 4]})
    result = semi_join(frame, keys, on=["user_id"], mode="exclude")
    assert list(result["user_id"]) == [1, 3]
    assert list(result["event"]) == ["a", "c"]


def test_semi_join_duplicate_keys_in_right_do_not_fan_out() -> None:
    frame = pd.DataFrame({"user_id": [1, 2, 3]})
    keys = pd.DataFrame({"user_id": [2, 2, 2]})
    result = semi_join(frame, keys, on=["user_id"], mode="keep")
    assert len(result) == 1
    assert list(result["user_id"]) == [2]


def test_semi_join_output_has_only_frame_columns() -> None:
    frame = pd.DataFrame({"user_id": [1, 2], "event": ["a", "b"]})
    keys = pd.DataFrame({"user_id": [1, 2], "count": [10, 20]})
    result = semi_join(frame, keys, on=["user_id"], mode="keep")
    assert list(result.columns) == ["user_id", "event"]


def test_semi_join_preserves_frame_index() -> None:
    frame = pd.DataFrame({"user_id": [1, 2, 3, 4]}, index=[10, 11, 12, 13])
    keys = pd.DataFrame({"user_id": [2, 4]})
    result = semi_join(frame, keys, on=["user_id"], mode="keep")
    assert list(result.index) == [11, 13]


def test_semi_join_composite_left_on_right_on_different_names() -> None:
    frame = pd.DataFrame({"uid": [1, 1, 2], "day": ["mon", "tue", "mon"], "v": [1, 2, 3]})
    keys = pd.DataFrame({"user_id": [1], "date": ["mon"]})
    result = semi_join(
        frame, keys, left_on=["uid", "day"], right_on=["user_id", "date"], mode="keep"
    )
    assert list(result["v"]) == [1]


def test_semi_join_unknown_mode_raises() -> None:
    frame = pd.DataFrame({"a": [1]})
    keys = pd.DataFrame({"a": [1]})
    with pytest.raises(ValueError, match="unknown mode"):
        semi_join(frame, keys, on=["a"], mode="bogus")


def test_semi_join_on_and_left_on_together_raises() -> None:
    frame = pd.DataFrame({"a": [1]})
    keys = pd.DataFrame({"a": [1]})
    with pytest.raises(ValueError, match="not both"):
        semi_join(frame, keys, on=["a"], left_on=["a"])


def test_semi_join_left_on_without_right_on_raises() -> None:
    frame = pd.DataFrame({"a": [1]})
    keys = pd.DataFrame({"a": [1]})
    with pytest.raises(ValueError, match="must be given together"):
        semi_join(frame, keys, left_on=["a"])


def test_semi_join_no_keys_spec_raises() -> None:
    frame = pd.DataFrame({"a": [1]})
    keys = pd.DataFrame({"a": [1]})
    with pytest.raises(ValueError, match="must specify"):
        semi_join(frame, keys)


def test_semi_join_unequal_left_on_right_on_length_raises() -> None:
    frame = pd.DataFrame({"a": [1], "b": [1]})
    keys = pd.DataFrame({"a": [1]})
    with pytest.raises(ValueError, match="same length"):
        semi_join(frame, keys, left_on=["a", "b"], right_on=["a"])


def test_semi_join_unknown_column_in_frame_raises() -> None:
    frame = pd.DataFrame({"a": [1]})
    keys = pd.DataFrame({"a": [1]})
    with pytest.raises(ValueError, match="unknown column.*in frame"):
        semi_join(frame, keys, on=["nope"])


def test_semi_join_unknown_column_in_keys_raises() -> None:
    frame = pd.DataFrame({"a": [1]})
    keys = pd.DataFrame({"b": [1]})
    with pytest.raises(ValueError, match="unknown column.*in keys"):
        semi_join(frame, keys, left_on=["a"], right_on=["nope"])


def test_semi_join_does_not_mutate_inputs() -> None:
    frame = pd.DataFrame({"user_id": [1, 2, 3]})
    keys = pd.DataFrame({"user_id": [2]})
    frame_orig, keys_orig = frame.copy(), keys.copy()
    semi_join(frame, keys, on=["user_id"], mode="keep")
    pd.testing.assert_frame_equal(frame, frame_orig)
    pd.testing.assert_frame_equal(keys, keys_orig)


def test_semi_join_registered_as_public_op() -> None:
    assert "ef.clean.semi_join" in PUBLIC_OPS


def test_semi_join_composes_with_group_by_aggregate_and_filter_rows() -> None:
    """End-to-end motivating example: exclude raw rows for users whose total
    interaction count exceeds a threshold, without widening the raw frame."""
    from emergentflow.stats import group_by_aggregate

    raw = pd.DataFrame(
        {
            "user_id": [1, 1, 1, 2, 3, 3],
            "event": ["click", "click", "click", "click", "click", "click"],
        }
    )
    counts = group_by_aggregate(raw, by=["user_id"], agg="count", columns=["event"])
    count_col = [c for c in counts.columns if c != "user_id"][0]
    flagged = filter_rows(counts, column=count_col, operator=">", value=2)
    result = semi_join(raw, flagged, on=["user_id"], mode="exclude")
    assert set(result["user_id"]) == {2, 3}
    assert list(result.columns) == ["user_id", "event"]
