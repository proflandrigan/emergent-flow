"""Tests for emergentflow.clean.combine (Epic 16, Story 7).

Covers ``ef.clean.concat``, ``ef.clean.deduplicate``, and ``ef.clean.sort``: thin wrappers
over ``pandas.concat`` / ``DataFrame.drop_duplicates`` / ``DataFrame.sort_values``, none of
which mutate their input.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from emergentflow.api import is_inspectable
from emergentflow.clean import (
    CleanError,
    ColumnCollisionError,
    UnknownColumnError,
    concat,
    deduplicate,
    sort,
)


def _a() -> pd.DataFrame:
    return pd.DataFrame({"id": [1, 2], "value": [10.0, 20.0]})


def _b() -> pd.DataFrame:
    return pd.DataFrame({"id": [3, 4], "value": [30.0, 40.0]})


def _c_extra_column() -> pd.DataFrame:
    return pd.DataFrame({"id": [5], "value": [50.0], "extra": ["x"]})


def _dupes() -> pd.DataFrame:
    return pd.DataFrame(
        {"id": [1, 1, 2, 2, 3], "grp": ["a", "a", "b", "b", "c"], "n": [1, 2, 3, 4, 5]}
    )


# --- concat ---


def test_concat_row_union() -> None:
    result = concat([_a(), _b()])
    assert result.shape[0] == 4
    assert list(result.columns) == ["id", "value"]


def test_concat_is_non_mutating() -> None:
    a, b = _a(), _b()
    snap_a, snap_b = a.copy(), b.copy()
    concat([a, b])
    pd.testing.assert_frame_equal(a, snap_a)
    pd.testing.assert_frame_equal(b, snap_b)


def test_concat_schema_aligns() -> None:
    result = concat([_a(), _c_extra_column()])
    assert "extra" in result.columns
    a_rows = result[result["id"].isin([1, 2])]
    assert a_rows["extra"].isna().all()


def test_concat_source_column_default_labels() -> None:
    result = concat([_a(), _b()], source_column="src")
    assert list(result["src"]) == ["frame_0", "frame_0", "frame_1", "frame_1"]


def test_concat_source_column_with_keys() -> None:
    result = concat([_a(), _b()], keys=["left", "right"], source_column="src")
    assert list(result["src"]) == ["left", "left", "right", "right"]


def test_concat_source_column_collision() -> None:
    with_src = _a().assign(src="preexisting")
    with pytest.raises(ColumnCollisionError, match="collide"):
        concat([with_src, _b()], source_column="src")


def test_concat_keys_length_mismatch() -> None:
    with pytest.raises(CleanError, match="one label per frame"):
        concat([_a(), _b()], keys=["only_one"])


def test_concat_requires_two_frames() -> None:
    with pytest.raises(CleanError):
        concat([_a()])


def test_concat_rejects_non_dataframe() -> None:
    with pytest.raises(CleanError):
        concat([_a(), "nope"])  # type: ignore[list-item]


def test_concat_ignore_index_resets() -> None:
    result = concat([_a(), _b()])
    assert list(result.index) == [0, 1, 2, 3]


# --- deduplicate ---


def test_deduplicate_all_columns() -> None:
    df = pd.DataFrame({"id": [1, 1, 2], "n": [1, 1, 2]})
    result = deduplicate(df)
    assert result.shape[0] == 2


def test_deduplicate_subset() -> None:
    result = deduplicate(_dupes(), subset=["id"])
    assert result.shape[0] == 3


def test_deduplicate_keep_last() -> None:
    result = deduplicate(_dupes(), subset=["id"], keep="last")
    assert list(result["n"]) == [2, 4, 5]


def test_deduplicate_keep_none() -> None:
    result = deduplicate(_dupes(), subset=["id"], keep="none")
    assert list(result["id"]) == [3]


def test_deduplicate_is_non_mutating() -> None:
    df = _dupes()
    snapshot = df.copy()
    deduplicate(df, subset=["id"])
    pd.testing.assert_frame_equal(df, snapshot)


def test_deduplicate_unknown_column() -> None:
    with pytest.raises(UnknownColumnError):
        deduplicate(_dupes(), subset=["nope"])


def test_deduplicate_unknown_keep() -> None:
    with pytest.raises(CleanError, match="unknown keep"):
        deduplicate(_dupes(), keep="bogus")


def test_deduplicate_empty_subset() -> None:
    with pytest.raises(CleanError):
        deduplicate(_dupes(), subset=[])


# --- sort ---


def test_sort_single_key_descending() -> None:
    result = sort(_dupes(), by=["n"], ascending=False)
    assert list(result["n"]) == [5, 4, 3, 2, 1]


def test_sort_multi_key_mixed_directions() -> None:
    result = sort(_dupes(), by=["grp", "n"], ascending=[True, False])
    assert list(result["grp"]) == ["a", "a", "b", "b", "c"]
    assert list(result["n"]) == [2, 1, 4, 3, 5]


def test_sort_is_stable() -> None:
    df = pd.DataFrame({"key": [1, 1, 1, 0], "tag": ["a", "b", "c", "d"]})
    result = sort(df, by=["key"])
    tied = result[result["key"] == 1]
    assert list(tied["tag"]) == ["a", "b", "c"]


def test_sort_na_position() -> None:
    df = pd.DataFrame({"key": [2.0, np.nan, 1.0], "tag": ["x", "y", "z"]})
    result_first = sort(df, by=["key"], na_position="first")
    assert result_first["tag"].iloc[0] == "y"
    result_last = sort(df, by=["key"], na_position="last")
    assert result_last["tag"].iloc[-1] == "y"


def test_sort_is_non_mutating() -> None:
    df = _dupes()
    snapshot = df.copy()
    sort(df, by=["n"], ascending=False)
    pd.testing.assert_frame_equal(df, snapshot)


def test_sort_unknown_column() -> None:
    with pytest.raises(UnknownColumnError):
        sort(_dupes(), by=["nope"])


def test_sort_empty_by() -> None:
    with pytest.raises(CleanError):
        sort(_dupes(), by=[])


def test_sort_ascending_length_mismatch() -> None:
    with pytest.raises(CleanError, match="one bool per key"):
        sort(_dupes(), by=["grp", "n"], ascending=[True])


def test_sort_unknown_na_position() -> None:
    with pytest.raises(CleanError, match="na_position"):
        sort(_dupes(), by=["n"], na_position="bogus")


# --- shared ---


def test_combine_results_are_inspectable() -> None:
    concat_result = concat([_a(), _b()])
    dedup_result = deduplicate(_dupes(), subset=["id"])
    sort_result = sort(_dupes(), by=["n"])
    assert is_inspectable(concat_result) is True
    assert is_inspectable(dedup_result) is True
    assert is_inspectable(sort_result) is True
