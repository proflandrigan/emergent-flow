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
