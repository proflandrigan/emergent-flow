"""
emergentflow.llm.budget
~~~~~~~~~~~~~~~~~~~~~~~
`BudgetClient` -- an `LLMClient` decorator enforcing a running-total USD
ceiling (Epic 9 Story 4). Wraps any `LLMClient` (a `ReplayClient`, a
`GatewayClient`, or another decorator); the guard lives entirely at this
client edge, never inside a node -- nodes stay unaware of budgeting. It
guards both completion calls (`complete()`) and embedding calls (`embed()`)
against the same running total, since a node graph may mix `llm.call` and
`embed.text` nodes behind one injected client.

Cost per call is computed independently via `emergentflow.llm.pricing`
(the same source of truth `emergentflow.llm.call()` uses), not read from the
wrapped client's returned `cost_usd` -- some clients (e.g. `GatewayClient`)
deliberately return a `0.0` placeholder there, since cost is centralized
elsewhere; `BudgetClient` cannot rely on it.
"""

from __future__ import annotations

from emergentflow.llm.pricing import compute_cost, compute_embedding_cost
from emergentflow.llm.protocol import (
    EmbeddingRequest,
    EmbeddingResponse,
    LLMClient,
    LLMRequest,
    LLMResponse,
)


class BudgetExceededError(RuntimeError):
    """Raised by `BudgetClient` when cumulative spend has already reached the ceiling.

    Raised *before* the wrapped client's `complete` is invoked, so the
    refused call incurs no further cost.
    """


class BudgetClient:
    """An `LLMClient` decorator that enforces a running-total `budget_usd` ceiling.

    Wraps any `LLMClient` structurally (see `emergentflow.llm.protocol.LLMClient`).
    Before each call, if `spent_usd` has already reached or exceeded
    `budget_usd`, the call is refused with `BudgetExceededError`. After a
    successful call, its cost -- computed via
    `emergentflow.llm.pricing.compute_cost`, independent of whatever
    `cost_usd` the wrapped client returned -- is added to the running total.

    Attributes
    ----------
    budget_usd:
        The ceiling. Never mutated by this class.
    spent_usd:
        Running total spent so far across calls that were allowed through.
        Starts at ``0.0``.
    """

    def __init__(self, client: LLMClient, *, budget_usd: float) -> None:
        self._client = client
        self.budget_usd = budget_usd
        self.spent_usd = 0.0

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Delegate to the wrapped client, guarded by the running budget.

        Raises
        ------
        BudgetExceededError
            If `spent_usd` has already reached or exceeded `budget_usd`.
        """
        if self.spent_usd >= self.budget_usd:
            raise BudgetExceededError(
                f"Budget of ${self.budget_usd:.4f} already reached (spent "
                f"${self.spent_usd:.4f}); refusing further calls."
            )
        response = self._client.complete(request)
        self.spent_usd += compute_cost(response.model, response.usage)
        return response

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Delegate to the wrapped client's `embed()`, guarded by the running budget.

        Mirrors `complete()`: refuses the call before it reaches the wrapped
        client if the budget is already exhausted, then tracks the call's
        cost -- computed via `emergentflow.llm.pricing.compute_embedding_cost`,
        independent of whatever `cost_usd` the wrapped client returned --
        against the same running total `complete()` uses.

        Raises
        ------
        BudgetExceededError
            If `spent_usd` has already reached or exceeded `budget_usd`.
        """
        if self.spent_usd >= self.budget_usd:
            raise BudgetExceededError(
                f"Budget of ${self.budget_usd:.4f} already reached (spent "
                f"${self.spent_usd:.4f}); refusing further calls."
            )
        response = self._client.embed(request)
        self.spent_usd += compute_embedding_cost(response.model, response.usage)
        return response
