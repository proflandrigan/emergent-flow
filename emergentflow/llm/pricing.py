"""
emergentflow.llm.pricing
~~~~~~~~~~~~~~~~~~~~~~~~
Per-model price table for LLM completion calls (Epic 9 Story 2/4).

Cost is a pure function of `(model, usage)`: `compute_cost(model, usage)`.
The table is plain data, deliberately easy to update as providers change
prices (Epic 9 Notes/Risks: "Cost table drift ... keep it editable and out
of the equivalence-critical path"). An unpriced model returns cost `0.0`
rather than raising, so a caller wiring an unlisted model still gets a
usable `LLMResponse` -- just without a cost figure.
"""

from __future__ import annotations

from emergentflow.llm.protocol import Usage

#: model id -> (USD per 1000 input tokens, USD per 1000 output tokens).
#: Update here as providers change pricing; not part of the ADR-0002
#: equivalence-critical path (see module docstring).
PRICE_TABLE_PER_1K_TOKENS: dict[str, tuple[float, float]] = {
    "claude-opus-4-8": (15.00, 75.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-haiku-4-5-20251001": (0.80, 4.00),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gemini-2.5-flash": (0.075, 0.30),
}


def compute_cost(model: str, usage: Usage) -> float:
    """Return the USD cost of one completion call, given *model* and *usage*.

    Pure function of its two arguments. Returns ``0.0`` for a *model* not
    present in :data:`PRICE_TABLE_PER_1K_TOKENS` (an unpriced/unlisted model
    still produces a usable `LLMResponse`; see module docstring).
    """
    prices = PRICE_TABLE_PER_1K_TOKENS.get(model)
    if prices is None:
        return 0.0
    input_per_1k, output_per_1k = prices
    return (usage.input_tokens / 1000.0) * input_per_1k + (
        usage.output_tokens / 1000.0
    ) * output_per_1k
