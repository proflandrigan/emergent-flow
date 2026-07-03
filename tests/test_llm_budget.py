"""
tests/test_llm_budget.py
~~~~~~~~~~~~~~~~~~~~~~~~~
Trip test for `emergentflow.llm.budget.BudgetClient` (Epic 9 Story 4).
"""

from __future__ import annotations

import pytest

from emergentflow.llm.budget import BudgetClient, BudgetExceededError
from emergentflow.llm.protocol import LLMRequest, LLMResponse, Usage


class _FakeInnerClient:
    """A trivial LLMClient double: 1000/1000 tokens on claude-sonnet-5 = $18/call
    (per emergentflow/llm/pricing.py's PRICE_TABLE_PER_1K_TOKENS)."""

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls += 1
        return LLMResponse(
            text="ok",
            data=None,
            model="claude-sonnet-5",
            usage=Usage(input_tokens=1000, output_tokens=1000),
            cost_usd=0.0,  # BudgetClient must NOT trust this placeholder.
            latency_ms=1.0,
            finish_reason="stop",
        )


def _request() -> LLMRequest:
    return LLMRequest(
        provider="anthropic",
        model="claude-sonnet-5",
        messages=({"role": "user", "content": "hi"},),
    )


def test_budget_client_allows_calls_under_budget():
    inner = _FakeInnerClient()
    client = BudgetClient(inner, budget_usd=10.0)

    response = client.complete(_request())

    assert response.text == "ok"
    assert inner.calls == 1
    assert client.spent_usd == pytest.approx(18.0)


def test_budget_client_trips_after_ceiling_reached():
    inner = _FakeInnerClient()
    client = BudgetClient(inner, budget_usd=10.0)

    # First call: allowed (spent starts at 0.0, under the 10.0 ceiling), even
    # though its own cost (18.0) exceeds the ceiling -- unavoidable, since
    # cost is unknown until the response returns.
    client.complete(_request())
    assert inner.calls == 1
    assert client.spent_usd == pytest.approx(18.0)

    # Second call: spent_usd (18.0) already >= budget_usd (10.0) -> refused
    # BEFORE the inner client is invoked.
    with pytest.raises(BudgetExceededError, match=r"\$10\.0000"):
        client.complete(_request())
    assert inner.calls == 1  # inner client was NOT invoked for the blocked call
