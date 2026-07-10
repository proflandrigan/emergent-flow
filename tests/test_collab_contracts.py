"""
tests/test_collab_contracts.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Epic 14, Story 4 — the mutation/session-event JSON Schema contracts
(emergentflow/collab/contracts.py) stay in sync with what SessionStore actually
publishes and what the export script actually writes.
"""

from __future__ import annotations

from emergentflow.collab.contracts import (
    SessionEvent,
    mutation_json_schema,
    session_event_json_schema,
)
from emergentflow.server.service import get_mutation_schema, get_session_event_schema


def test_session_event_matches_every_publish_call_shape() -> None:
    """Every literal event dict SessionStore._publish emits (see emergentflow/collab/session.py)
    must validate against SessionEvent -- this is the drift guard the contracts.py docstring
    promises."""
    SessionEvent.model_validate({"type": "graph_replaced", "session_id": "s1", "version": 1})
    SessionEvent.model_validate({"type": "proposal_added", "session_id": "s1", "proposal_id": "p1"})
    SessionEvent.model_validate(
        {"type": "proposal_accepted", "session_id": "s1", "proposal_id": "p1", "version": 2}
    )
    SessionEvent.model_validate(
        {"type": "proposal_rejected", "session_id": "s1", "proposal_id": "p1"}
    )
    SessionEvent.model_validate({"type": "review_added", "session_id": "s1", "review_id": "r1"})
    SessionEvent.model_validate(
        {
            "type": "review_comment_added",
            "session_id": "s1",
            "review_id": "r1",
            "comment_id": "c1",
        }
    )
    SessionEvent.model_validate({"type": "gate_opened", "session_id": "s1", "gate_id": "g1"})
    SessionEvent.model_validate({"type": "gate_closed", "session_id": "s1", "gate_id": "g1"})
    SessionEvent.model_validate({"type": "gate_skipped", "session_id": "s1", "gate_id": "g1"})
    SessionEvent.model_validate(
        {
            "type": "decision_added",
            "session_id": "s1",
            "gate_id": "g1",
            "decision_id": "d1",
        }
    )


def test_mutation_json_schema_has_expected_top_level_shape() -> None:
    schema = mutation_json_schema()
    assert schema["title"] == "GraphMutation"
    assert "base_version" in schema["properties"]
    assert "set_params" in schema["properties"]


def test_session_event_json_schema_has_expected_top_level_shape() -> None:
    schema = session_event_json_schema()
    assert schema["title"] == "SessionEvent"
    assert "type" in schema["properties"]
    assert "session_id" in schema["properties"]


def test_service_functions_match_contracts_module() -> None:
    assert get_mutation_schema() == mutation_json_schema()
    assert get_session_event_schema() == session_event_json_schema()
