"""
emergentflow.eval.run
~~~~~~~~~~~~~~~~~~~~~~
`run()` -- the compare/eval-run harness (Epic 9 Story 5, `ef.eval.run`).

Pure aside from the calls it delegates to the injected `LLMClient`: for each
`(dataset row, variant)` pair it renders a fresh `PromptSpec` (via
`emergentflow.llm.templating.render_prompt`) from the shared `system`/`user`
templates and that row's variable bindings, then calls
`emergentflow.llm.call()` with the variant's provider/model/params. The
result is a tidy DataFrame, one row per `(input_row, variant)`, in the exact
column shape `emergentflow.llm.aggregate.summarize_run` (Epic 9 Story 4)
expects: `cost_usd`, `input_tokens`, `output_tokens`, `latency_ms`.

Deterministic under a `ReplayClient` (fixtures are keyed by each rendered
request's content hash), so re-running the same dataset/variants/client
reproduces byte-identical results -- the property the Prompt Lab compare grid
(Epic 9 Story 8) and run history depend on.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from emergentflow.api import public_op
from emergentflow.llm import call
from emergentflow.llm.protocol import LLMClient
from emergentflow.llm.templating import render_prompt

# Kept in sync with the dict built per-row below so an empty `dataset`/`variants`
# still produces a DataFrame with this exact column shape (Epic 9 Story 4's
# `summarize_run` requires `cost_usd`/`input_tokens`/`output_tokens`/`latency_ms`
# to exist as columns, not just be absent because there were zero rows).
_RESULT_COLUMNS = (
    "row_id",
    "input",
    "messages",
    "provider",
    "model",
    "output",
    "input_tokens",
    "output_tokens",
    "cost_usd",
    "latency_ms",
    "finish_reason",
)


@public_op(name="ef.eval.run")
def run(
    system: str,
    user: str,
    dataset: list[dict[str, Any]],
    variants: list[dict[str, Any]],
    *,
    client: LLMClient | None,
) -> pd.DataFrame:
    """Run the `system`/`user` prompt template over every `(row, variant)` pair.

    Parameters
    ----------
    system, user:
        Prompt templates (`{{var}}` substitution; see
        `emergentflow.llm.templating.render_prompt`).
    dataset:
        Variable-binding rows, each rendered fresh against *system*/*user*.
    variants:
        Model variants to compare, each a dict with required `provider` and
        `model` keys and optional `temperature`, `max_tokens`,
        `response_format`, `response_schema`, `api_key_env` keys (passed
        straight through to `emergentflow.llm.call`).
    client:
        The injected `LLMClient` (ADR 0017) every call delegates to.

    Returns
    -------
    pd.DataFrame
        One row per `(input_row, variant)`, columns: `row_id` (0-based index of
        the row's position in `dataset`; shared by every variant of that row),
        `input` (the row dict), `messages` (the exact rendered
        `list[dict[str, str]]` messages this cell's call used), `provider`,
        `model`, `output` (text or parsed structured data), `input_tokens`,
        `output_tokens`, `cost_usd`, `latency_ms`, `finish_reason`.

    Raises
    ------
    MissingClientError
        If *client* is ``None`` (propagated from `emergentflow.llm.call`).
    PromptVariableError
        If a dataset row's bindings don't match what *system*/*user*
        reference (propagated from `render_prompt`).
    """
    rows: list[dict[str, Any]] = []
    for row_id, row in enumerate(dataset):
        prompt_spec = render_prompt(system, user, row)
        for variant in variants:
            variant_kwargs = {k: v for k, v in variant.items() if k not in ("provider", "model")}
            response = call(
                prompt_spec.messages,
                provider=variant["provider"],
                model=variant["model"],
                client=client,
                **variant_kwargs,
            )
            rows.append(
                {
                    "row_id": row_id,
                    "input": row,
                    "messages": list(prompt_spec.messages),
                    "provider": variant["provider"],
                    "model": variant["model"],
                    "output": response.text if response.text is not None else response.data,
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                    "cost_usd": response.cost_usd,
                    "latency_ms": response.latency_ms,
                    "finish_reason": response.finish_reason,
                }
            )
    return pd.DataFrame(rows, columns=list(_RESULT_COLUMNS))
