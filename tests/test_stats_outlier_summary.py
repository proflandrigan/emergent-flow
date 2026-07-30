"""Tests for emergentflow.stats.outlier_summary (Issue #102).

Covers the public op and the stats.outlier_summary reference node, including
ADR-0002 equivalence between execute() and the code codegen() emits.
"""

from __future__ import annotations

import pandas as pd
import pytest

from emergentflow.api import PUBLIC_OPS, is_inspectable
from emergentflow.nodes.examples import OutlierSummary
from emergentflow.stats import outlier_summary


def _make_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "x": [0.0, 0.0, 0.0, 10.0],
            "y": [1.0, 2.0, 3.0, 4.0],
            "z": ["a", "b", "c", "d"],
        }
    )


def test_outlier_summary_is_registered_public_op() -> None:
    assert "ef.stats.outlier_summary" in PUBLIC_OPS


def test_outlier_summary_result_is_inspectable() -> None:
    df = _make_df()
    result = outlier_summary(df)
    assert isinstance(result, pd.DataFrame)
    assert is_inspectable(result)


def test_outlier_summary_does_not_mutate_input() -> None:
    df = _make_df()
    before = df.copy(deep=True)
    outlier_summary(df)
    pd.testing.assert_frame_equal(df, before)


def test_outlier_summary_reports_expected_columns() -> None:
    df = _make_df()
    result = outlier_summary(df, columns=["x"], method="zscore", threshold=1.0)
    assert list(result.columns) == [
        "column",
        "method",
        "threshold",
        "lower",
        "upper",
        "n",
        "n_outliers",
        "pct_outliers",
    ]
    assert result["column"].tolist() == ["x"]
    assert result["method"].tolist() == ["zscore"]
    assert result["n"].iloc[0] == 4
    assert result["n_outliers"].iloc[0] == 1


def test_outlier_summary_defaults_to_all_numeric_columns() -> None:
    df = _make_df()
    result = outlier_summary(df, method="zscore", threshold=1.0)
    assert set(result["column"]) == {"x", "y"}
    assert "z" not in set(result["column"])


def test_outlier_summary_skips_non_numeric_named_columns() -> None:
    df = _make_df()
    result = outlier_summary(df, columns=["z"], method="zscore", threshold=1.0)
    assert len(result) == 0


def test_outlier_summary_unknown_column_raises() -> None:
    df = _make_df()
    with pytest.raises(ValueError):
        outlier_summary(df, columns=["nope"])


def test_outlier_summary_shares_bounds_with_detect_outliers() -> None:
    from emergentflow.clean import detect_outliers

    df = _make_df()
    summary = outlier_summary(df, columns=["x"], method="zscore", threshold=1.0)
    flagged = detect_outliers(df, columns=["x"], method="zscore", threshold=1.0)
    assert summary["n_outliers"].iloc[0] == int(flagged["is_outlier"].sum())


def test_outlier_summary_skips_boolean_columns_like_the_detector() -> None:
    df = pd.DataFrame({"x": [1.0, 2.0, 3.0, 100.0], "flag": [True, False, True, False]})
    assert outlier_summary(df, method="zscore", threshold=1.0)["column"].tolist() == ["x"]


@pytest.mark.parametrize(
    ("method", "threshold"),
    [("quantile", 3.0), ("percent", 3.0), ("zscore", 0.0), ("iqr", -1.0), ("quantile", 0.5)],
)
def test_outlier_summary_out_of_domain_threshold_raises(method: str, threshold: float) -> None:
    with pytest.raises(ValueError, match="threshold"):
        outlier_summary(_make_df(), columns=["x"], method=method, threshold=threshold)


def test_outlier_summary_unknown_method_raises_value_error() -> None:
    # Not a CleanError: this is a stats op, and its callers should not have to catch
    # an error type from the clean family just because the two ops share a rule seam.
    with pytest.raises(ValueError, match="unknown method"):
        outlier_summary(_make_df(), method="bogus")


# ---------------------------------------------------------------------------
# Issue #102's actual promise: the reported cut IS the applied cut. Swept across
# every method and several degenerate shapes, not just the happy path.
# ---------------------------------------------------------------------------

_RULES = [
    ("zscore", 3.0),
    ("zscore", 1.0),
    ("modified_zscore", 3.0),
    ("iqr", 1.5),
    ("iqr", 0.5),
    ("quantile", 0.01),
    ("quantile", 0.1),
    ("percent", 0.05),
    ("percent", 0.2),
]

_SHAPES = {
    "spread": [float(v) for v in range(50)] + [10_000.0],
    "constant": [3.0] * 20,
    # IQR == 0 but real extremes present: the fence collapses to a point, and the
    # summary must still agree with what the detector flags.
    "zero_iqr": [1.0] * 18 + [50.0, -70.0],
    "with_nan": [1.0, 2.0, float("nan"), 3.0, 99.0],
    "two_rows": [1.0, 2.0],
}


@pytest.mark.parametrize("method,threshold", _RULES)
@pytest.mark.parametrize("shape", sorted(_SHAPES))
def test_summary_count_equals_detector_flag_count(
    shape: str, method: str, threshold: float
) -> None:
    from emergentflow.clean import detect_outliers

    df = pd.DataFrame({"x": _SHAPES[shape]})
    summary = outlier_summary(df, columns=["x"], method=method, threshold=threshold)
    flagged = detect_outliers(df, columns=["x"], method=method, threshold=threshold)
    assert int(summary["n_outliers"].iloc[0]) == int(flagged["is_outlier"].sum())


def test_outlier_summary_ignores_missing_values_in_counts() -> None:
    df = pd.DataFrame({"x": [1.0, 2.0, float("nan"), 3.0]})
    row = outlier_summary(df, columns=["x"], method="zscore", threshold=1.0).iloc[0]
    assert row["n"] == 3  # non-missing only
    assert row["n_outliers"] == 0  # a missing value is never an outlier


# ---------------------------------------------------------------------------
# ADR-0002 equivalence: execute() == running codegen()'s emitted code.
# ---------------------------------------------------------------------------


def _run_codegen(definition, node, scope):
    frag = definition.preview(node)
    exec(frag.render(), scope)  # noqa: S102 -- test-only, on our own emitted code
    return scope


@pytest.mark.equivalence
def test_outlier_summary_node_equivalence() -> None:
    df = _make_df()
    defn = OutlierSummary()
    node = defn.instantiate(columns=["x"], method="zscore", threshold=1.0)

    executed = defn.execute(node, inputs={"frame": df.copy()})
    executed_result = executed["summary"]

    scope = _run_codegen(defn, node, {"frame": df.copy()})
    codegen_result = scope["summary"]

    pd.testing.assert_frame_equal(executed_result, codegen_result)
