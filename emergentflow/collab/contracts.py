"""
emergentflow.collab.contracts
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Typed JSON-Schema-exportable mirror of the SSE event shapes `SessionStore` publishes
(Epic 14 Story 4). This module exists purely so the canvas has a committed JSON Schema
to ajv-validate session events against, the same role `emergentflow.ir.schema` plays for
the `Graph` IR model. It does not construct or validate the dicts `SessionStore._publish`
actually emits at runtime -- `tests/test_collab_contracts.py` asserts the two stay in sync.

Never imported by `emergentflow/__init__.py`, `emergentflow/ir/graph.py`, or
`emergentflow/ir/mutation.py` (works-without-agents invariant, ADR 0019).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from emergentflow.ir.mutation import GraphMutation


class SessionEvent(BaseModel):
    """The shape of every event `SessionStore` publishes on a session's SSE stream."""

    model_config = ConfigDict(extra="forbid")

    type: Literal[
        "graph_replaced",
        "proposal_added",
        "proposal_accepted",
        "proposal_rejected",
        "review_added",
        "review_comment_added",
        "gate_opened",
        "gate_closed",
        "gate_skipped",
        "decision_added",
        "chat_turn_started",
        "chat_narration_added",
        "chat_turn_completed",
        "chat_turn_failed",
        "chat_turn_interrupted",
        "chat_ended",
        "persona_changed",
    ]
    session_id: str
    proposal_id: str | None = None
    version: int | None = None
    review_id: str | None = None
    comment_id: str | None = None
    gate_id: str | None = None
    decision_id: str | None = None
    turn_id: str | None = None
    persona: str | None = None


def mutation_json_schema() -> dict[str, Any]:
    """Return the JSON Schema for `GraphMutation` (emergentflow/ir/mutation.py)."""
    return GraphMutation.model_json_schema()


def session_event_json_schema() -> dict[str, Any]:
    """Return the JSON Schema for `SessionEvent`."""
    return SessionEvent.model_json_schema()
