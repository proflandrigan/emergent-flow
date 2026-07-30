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


def test_detect_outliers_drop_does_not_collide() -> None:
    """``drop=True`` adds neither column, so an existing one is not a collision.

    This is the two-node canvas flow: flag with one ``clean.detect_outliers``, inspect
    the scores, then cut the rows with a second one set to ``drop=True``. The second
    call sees the first's ``is_outlier`` column and must not refuse it.
    """
    flagged = detect_outliers(
        pd.DataFrame({"x": [1.0, 2.0, 3.0, 99.0]}), columns=["x"], method="zscore", threshold=1.0
    )
    result = detect_outliers(flagged, columns=["x"], method="zscore", threshold=1.0, drop=True)

    assert result["x"].tolist() == [1.0, 2.0, 3.0]
    # drop=True omits the columns it would have added, but passes through the ones the
    # upstream node already put there.
    assert list(result.columns) == ["x", "is_outlier", "outlier_score"]


def test_detect_outliers_no_numeric_columns_returns_empty_flag() -> None:
    df = pd.DataFrame({"z": ["a", "b", "c"]})
    result = detect_outliers(df)
    assert not result["is_outlier"].any()
    assert result["outlier_score"].isna().all()


def test_detect_outliers_no_numeric_columns_with_drop_is_a_passthrough() -> None:
    df = pd.DataFrame({"z": ["a", "b", "c"]})
    result = detect_outliers(df, drop=True)
    pd.testing.assert_frame_equal(result, df)


# ---------------------------------------------------------------------------
# threshold domain: the shared 3.0 default is invalid for quantile/percent and
# must surface as a typed CleanError, not pandas' "percentiles should all be in
# the interval [0, 1]".
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method", ["quantile", "percent"])
def test_detect_outliers_default_threshold_is_rejected_for_fraction_methods(method: str) -> None:
    df = _make_df()
    with pytest.raises(CleanError, match="threshold"):
        detect_outliers(df, columns=["x"], method=method)


@pytest.mark.parametrize(
    ("method", "threshold"),
    [
        ("zscore", 0.0),
        ("zscore", -1.0),
        ("modified_zscore", -0.5),
        ("iqr", 0.0),
        ("quantile", 0.0),
        ("quantile", 0.5),
        ("quantile", 0.9),
        ("percent", 0.0),
        ("percent", 1.0),
    ],
)
def test_detect_outliers_out_of_domain_threshold_raises(method: str, threshold: float) -> None:
    df = _make_df()
    with pytest.raises(CleanError, match="threshold"):
        detect_outliers(df, columns=["x"], method=method, threshold=threshold)


@pytest.mark.parametrize(
    ("method", "threshold"),
    [
        ("zscore", 3.0),
        ("modified_zscore", 3.0),
        ("iqr", 1.5),
        ("quantile", 0.01),
        ("percent", 0.05),
    ],
)
def test_detect_outliers_in_domain_threshold_is_accepted(method: str, threshold: float) -> None:
    df = pd.DataFrame({"x": [float(v) for v in range(50)]})
    result = detect_outliers(df, columns=["x"], method=method, threshold=threshold)
    assert result["is_outlier"].dtype == bool


# ---------------------------------------------------------------------------
# Score semantics: one meaning for every method -- 0.0 at the fence's centre,
# 1.0 exactly on the fence, > 1.0 outside it.
# ---------------------------------------------------------------------------


def test_outlier_score_is_continuous_inside_the_fence() -> None:
    # mean 2.5 / std 5.0 at threshold 1.0 -> fence [-2.5, 7.5], half-width 5.0.
    result = detect_outliers(
        pd.DataFrame({"x": [0.0, 0.0, 0.0, 10.0]}), columns=["x"], method="zscore", threshold=1.0
    )
    # Inliers score by distance, not a flat 0.0: |0 - 2.5| / 5.0 == 0.5.
    assert result["outlier_score"].tolist() == pytest.approx([0.5, 0.5, 0.5, 1.5])


@pytest.mark.parametrize(
    ("method", "threshold"),
    [("zscore", 2.0), ("modified_zscore", 3.0), ("iqr", 1.5), ("quantile", 0.05), ("percent", 0.1)],
)
def test_outlier_score_above_one_iff_flagged(method: str, threshold: float) -> None:
    df = pd.DataFrame({"x": [*[float(v) for v in range(40)], 5_000.0, -9_000.0]})
    result = detect_outliers(df, columns=["x"], method=method, threshold=threshold)
    scored = result["outlier_score"].notna()
    assert ((result.loc[scored, "outlier_score"] > 1.0) == result.loc[scored, "is_outlier"]).all()


@pytest.mark.parametrize(
    ("method", "threshold"),
    [("zscore", 2.0), ("modified_zscore", 3.0), ("iqr", 1.5), ("quantile", 0.05), ("percent", 0.1)],
)
def test_outlier_score_above_one_iff_flagged_across_columns(method: str, threshold: float) -> None:
    """The score invariant must survive the per-column ``max``, not just one column.

    ``x`` has a collapsed fence (half its values identical, so MAD and IQR are both 0)
    while ``y`` is a benign ramp. Scoring ``x``'s outliers ``NaN`` would let the
    NaN-skipping ``max`` publish ``y``'s mild deviation for a row ``x`` flagged, so a
    120x outlier would read as a sub-1.0 score -- indistinguishable from an inlier to a
    downstream ``clean.filter_rows``.
    """
    df = pd.DataFrame({"x": [10.0] * 8 + [900.0, 1200.0], "y": [i / 9 for i in range(10)]})
    result = detect_outliers(df, method=method, threshold=threshold)
    scored = result["outlier_score"].notna()
    assert ((result.loc[scored, "outlier_score"] > 1.0) == result.loc[scored, "is_outlier"]).all()


def test_outlier_score_is_inf_when_the_fence_has_no_width() -> None:
    # IQR is 0 here, so the fence collapses to the single point [1.0, 1.0]: 50.0 is
    # unambiguously outside it, and "infinitely many fence half-widths away" is the
    # limit of the same formula -- keeping the `score > 1.0 iff flagged` contract true.
    result = detect_outliers(
        pd.DataFrame({"x": [1.0, 1.0, 1.0, 1.0, 50.0]}),
        columns=["x"],
        method="iqr",
        threshold=1.5,
    )
    assert result["is_outlier"].tolist() == [False, False, False, False, True]
    assert result["outlier_score"].iloc[-1] == float("inf")
    assert result["outlier_score"].iloc[:-1].tolist() == [0.0, 0.0, 0.0, 0.0]


def test_outlier_score_survives_the_per_column_max_when_one_fence_collapses() -> None:
    """Regression for the NaN-masking bug: a flagged row must not inherit y's score."""
    df = pd.DataFrame({"x": [10.0] * 8 + [900.0, 1200.0], "y": [i / 9 for i in range(10)]})
    result = detect_outliers(df, method="modified_zscore", threshold=3.0)

    assert result["is_outlier"].tolist() == [False] * 8 + [True, True]
    # The two flagged rows score inf (from x), not y's benign 0.39 / 0.50.
    assert result["outlier_score"].iloc[-2:].tolist() == [float("inf"), float("inf")]
    # ...so the advertised `filter_rows` subset reaches exactly the flagged rows.
    assert (result["outlier_score"] > 1.0).tolist() == result["is_outlier"].tolist()


def test_detect_outliers_constant_column_flags_nothing() -> None:
    result = detect_outliers(pd.DataFrame({"x": [5.0] * 6}), columns=["x"], method="zscore")
    assert not result["is_outlier"].any()


# ---------------------------------------------------------------------------
# Missing values: never an outlier, and never a misleadingly confident score.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "threshold"),
    [("zscore", 1.0), ("modified_zscore", 3.0), ("iqr", 1.5), ("quantile", 0.1), ("percent", 0.25)],
)
def test_missing_values_are_never_flagged_and_score_nan(method: str, threshold: float) -> None:
    df = pd.DataFrame({"x": [1.0, 2.0, float("nan"), 100.0]})
    result = detect_outliers(df, columns=["x"], method=method, threshold=threshold)
    assert not bool(result["is_outlier"].iloc[2])
    assert pd.isna(result["outlier_score"].iloc[2])


def test_detect_outliers_handles_nullable_integer_columns() -> None:
    df = pd.DataFrame({"x": pd.array([1, 2, None, 4, 900], dtype="Int64")})
    result = detect_outliers(df, columns=["x"], method="zscore", threshold=1.0)
    assert result["is_outlier"].tolist() == [False, False, False, False, True]


# ---------------------------------------------------------------------------
# Column eligibility: implicit and explicit selection must agree.
# ---------------------------------------------------------------------------


def test_boolean_columns_are_not_outlier_targets() -> None:
    df = pd.DataFrame({"x": [1.0, 2.0, 3.0, 100.0], "flag": [True, False, True, False]})
    # Implicit selection skips it ...
    implicit = detect_outliers(df, method="zscore", threshold=1.0)
    assert implicit["is_outlier"].tolist() == [False, False, False, True]
    # ... and naming it explicitly is an error rather than a silently useless fence.
    with pytest.raises(CleanError):
        detect_outliers(df, columns=["flag"], method="zscore", threshold=1.0)


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
