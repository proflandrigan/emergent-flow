"""
emergentflow.llm.aggregate
~~~~~~~~~~~~~~~~~~~~~~~~~~
Pure cost/token/latency aggregation over an eval-run result (Epic 9 Story 4).

`summarize_run` is a pure function of a tidy DataFrame -- expected columns
`cost_usd` (float), `input_tokens` (int), `output_tokens` (int), `latency_ms`
(float), one row per (input_row, variant) call -- into a single-row tidy
summary DataFrame: total cost, total tokens, and p50/p95 latency. This is
the aggregation contract `ef.eval.run` (Epic 9 Story 5) produces rows to
satisfy; Story 4 defines it first so Story 5 conforms to it.
"""

from __future__ import annotations

import pandas as pd

from emergentflow.api import public_op

_REQUIRED_COLUMNS = ("cost_usd", "input_tokens", "output_tokens", "latency_ms")


@public_op(name="ef.llm.summarize_run")
def summarize_run(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate a tidy per-call DataFrame into a single-row cost/token/latency summary.

    Parameters
    ----------
    df:
        A tidy DataFrame with one row per LLM call, requiring at least the
        columns `cost_usd`, `input_tokens`, `output_tokens`, `latency_ms`
        (the shape `ef.eval.run`, Epic 9 Story 5, produces).

    Returns
    -------
    pd.DataFrame
        A single-row DataFrame with columns `n_calls`, `total_cost_usd`,
        `total_input_tokens`, `total_output_tokens`, `latency_p50_ms`,
        `latency_p95_ms`.

    Raises
    ------
    ValueError
        If *df* is missing any required column.
    """
    missing = [c for c in _REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"summarize_run: missing required column(s): {missing}")

    latency = df["latency_ms"]
    summary = {
        "n_calls": [len(df)],
        "total_cost_usd": [float(df["cost_usd"].sum())],
        "total_input_tokens": [int(df["input_tokens"].sum())],
        "total_output_tokens": [int(df["output_tokens"].sum())],
        "latency_p50_ms": [float(latency.quantile(0.5))],
        "latency_p95_ms": [float(latency.quantile(0.95))],
    }
    return pd.DataFrame(summary)
