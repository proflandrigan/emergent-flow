"""Tests for emergentflow.clean.detect_outliers (Issue #101).

Covers the public op and the clean.detect_outliers reference node, including
ADR-0002 equivalence between execute() and the code codegen() emits.
"""

from __future__ import annotations

import pandas as pd
import pytest

from emergentflow.api import PUBLIC_OPS, is_inspectable
from emergentflow.clean import detect_outliers
from emergentflow.clean.errors import CleanError, ColumnCollisionError, UnknownColumnError
from emergentflow.nodes.examples import DetectOutliers


def _make_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "x": [0.0, 0.0, 0.0, 10.0],
            "y": [1.0, 2.0, 3.0, 4.0],
            "z": ["a", "b", "c", "d"],
        }
    )


def test_detect_outliers_is_registered_public_op() -> None:
    assert "ef.clean.detect_outliers" in PUBLIC_OPS


def test_detect_outliers_result_is_inspectable() -> None:
    df = _make_df()
    result = detect_outliers(df)
    assert isinstance(result, pd.DataFrame)
    assert is_inspectable(result)


def test_detect_outliers_does_not_mutate_input() -> None:
    df = _make_df()
    before = df.copy(deep=True)
    detect_outliers(df)
    pd.testing.assert_frame_equal(df, before)


def test_detect_outliers_zscore_flags_extreme_value() -> None:
    df = _make_df()
    result = detect_outliers(df, columns=["x"], method="zscore", threshold=1.0)
    assert result["is_outlier"].tolist() == [False, False, False, True]


def test_detect_outliers_modified_zscore_flags_extreme_value() -> None:
    df = pd.DataFrame({"x": [0.0, 1.0, 2.0, 3.0, 100.0]})
    result = detect_outliers(df, columns=["x"], method="modified_zscore", threshold=3.0)
    assert result["is_outlier"].tolist() == [False, False, False, False, True]


def test_detect_outliers_iqr_flags_extreme_value() -> None:
    df = _make_df()
    result = detect_outliers(df, columns=["x"], method="iqr", threshold=1.5)
    assert result["is_outlier"].tolist() == [False, False, False, True]


def test_detect_outliers_quantile_flags_extreme_value() -> None:
    df = pd.DataFrame({"x": list(range(100))})
    result = detect_outliers(df, columns=["x"], method="quantile", threshold=0.01)
    assert result["is_outlier"].iloc[0]
    assert result["is_outlier"].iloc[-1]
    assert not result["is_outlier"].iloc[50]


def test_detect_outliers_percent_flags_extreme_fraction() -> None:
    df = pd.DataFrame({"x": list(range(100))})
    result = detect_outliers(df, columns=["x"], method="percent", threshold=0.05)
    assert result["is_outlier"].sum() > 0


def test_detect_outliers_combine_all_requires_all_columns() -> None:
    df = pd.DataFrame({"x": [0.0, 10.0], "y": [1.0, 2.0]})
    result = detect_outliers(df, columns=["x", "y"], method="zscore", threshold=1.0, combine="all")
    # y has no outliers with this threshold, so combine=all should flag nothing.
    assert not result["is_outlier"].any()


def test_detect_outliers_drop_true_omits_columns_and_outliers() -> None:
    df = _make_df()
    result = detect_outliers(df, columns=["x"], method="zscore", threshold=1.0, drop=True)
    assert "is_outlier" not in result.columns
    assert "outlier_score" not in result.columns
    assert len(result) == 3


def test_detect_outliers_unknown_column_raises() -> None:
    df = _make_df()
    with pytest.raises(UnknownColumnError):
        detect_outliers(df, columns=["nope"])


def test_detect_outliers_non_numeric_column_raises() -> None:
    df = _make_df()
    with pytest.raises(CleanError):
        detect_outliers(df, columns=["z"])


def test_detect_outliers_bad_method_raises() -> None:
    df = _make_df()
    with pytest.raises(CleanError):
        detect_outliers(df, method="bogus")


def test_detect_outliers_bad_combine_raises() -> None:
    df = _make_df()
    with pytest.raises(CleanError):
        detect_outliers(df, combine="bogus")


def test_detect_outliers_collision_raises() -> None:
    df = pd.DataFrame({"x": [1.0, 2.0], "is_outlier": [False, False]})
    with pytest.raises(ColumnCollisionError):
        detect_outliers(df, columns=["x"])


def test_detect_outliers_no_numeric_columns_returns_empty_flag() -> None:
    df = pd.DataFrame({"z": ["a", "b", "c"]})
    result = detect_outliers(df)
    assert not result["is_outlier"].any()
    assert result["outlier_score"].isna().all()


# ---------------------------------------------------------------------------
# ADR-0002 equivalence: execute() == running codegen()'s emitted code.
# ---------------------------------------------------------------------------


def _run_codegen(definition, node, scope):
    frag = definition.preview(node)
    exec(frag.render(), scope)  # noqa: S102 -- test-only, on our own emitted code
    return scope


@pytest.mark.equivalence
def test_detect_outliers_node_equivalence() -> None:
    df = _make_df()
    defn = DetectOutliers()
    node = defn.instantiate(columns=["x"], method="zscore", threshold=1.0)

    executed = defn.execute(node, inputs={"frame": df.copy()})
    executed_result = executed["frame"]

    scope = _run_codegen(defn, node, {"frame": df.copy()})
    codegen_result = scope["frame"]

    assert executed_result["is_outlier"].tolist() == codegen_result["is_outlier"].tolist()
    assert executed_result["outlier_score"].tolist() == pytest.approx(
        codegen_result["outlier_score"].tolist(), nan_ok=True
    )
    pd.testing.assert_frame_equal(
        executed_result.drop(columns=["is_outlier", "outlier_score"]),
        codegen_result.drop(columns=["is_outlier", "outlier_score"]),
    )
