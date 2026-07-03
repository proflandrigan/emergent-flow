"""
tests/test_llm_aggregate.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Fixed-fixture test for `emergentflow.llm.aggregate.summarize_run` (Epic 9 Story 4).
"""

from __future__ import annotations

import pandas as pd
import pytest

from emergentflow.llm.aggregate import summarize_run


def test_summarize_run_fixed_fixture():
    """A small, hand-verifiable fixture produces exact expected totals and percentiles."""
    df = pd.DataFrame(
        {
            "cost_usd": [0.01, 0.02, 0.03, 0.04],
            "input_tokens": [10, 20, 30, 40],
            "output_tokens": [5, 10, 15, 20],
            "latency_ms": [10.0, 20.0, 30.0, 40.0],
        }
    )

    summary = summarize_run(df)

    assert list(summary.columns) == [
        "n_calls",
        "total_cost_usd",
        "total_input_tokens",
        "total_output_tokens",
        "latency_p50_ms",
        "latency_p95_ms",
    ]
    assert summary.shape == (1, 6)
    row = summary.iloc[0]
    assert row["n_calls"] == 4
    assert row["total_cost_usd"] == pytest.approx(0.10)
    assert row["total_input_tokens"] == 100
    assert row["total_output_tokens"] == 50
    assert row["latency_p50_ms"] == pytest.approx(25.0)
    assert row["latency_p95_ms"] == pytest.approx(38.5)


def test_summarize_run_missing_column_raises():
    """A DataFrame missing a required column raises a clear ValueError."""
    df = pd.DataFrame({"cost_usd": [1.0]})
    with pytest.raises(ValueError, match="missing required column"):
        summarize_run(df)


def test_summarize_run_is_public_op():
    """summarize_run is reachable as ef.llm.summarize_run and returns an inspectable DataFrame."""
    import emergentflow as ef

    df = pd.DataFrame(
        {"cost_usd": [0.5], "input_tokens": [1], "output_tokens": [1], "latency_ms": [5.0]}
    )
    summary = ef.llm.summarize_run(df)
    assert summary.shape == (1, 6)
