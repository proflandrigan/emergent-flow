"""
tests/test_collab_gates.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Epic 14, Story 9 -- gate/decision models and SessionStore methods. Mirrors
tests/test_collab_review.py's structure and conventions.
"""

from __future__ import annotations

import pytest

from emergentflow.collab.gates import (
    Decision,
    Gate,
    GateAlreadyResolvedError,
    GateKind,
    GateStatus,
    UnknownGateError,
)
from emergentflow.collab.session import SessionStore, UnknownSessionError


class TestGateModel:
    def test_defaults(self) -> None:
        gate = Gate(phase="review", kind=GateKind.CONFIRM, description="check results")
        assert gate.status == GateStatus.OPEN
        assert gate.decisions == []

    def test_round_trips_through_json(self) -> None:
        gate = Gate(
            phase="review",
            kind=GateKind.CONFIRM,
            description="check results",
            decisions=[Decision(author="agent-x", text="looks good")],
        )
        dumped = gate.model_dump(mode="json")
        restored = Gate.model_validate(dumped)
        assert restored == gate

    def test_decision_defaults(self) -> None:
        d = Decision(author="human", text="proceed")
        assert d.id is not None

    def test_decision_round_trips_through_json(self) -> None:
        d = Decision(author="human", text="proceed")
        dumped = d.model_dump(mode="json")
        restored = Decision.model_validate(dumped)
        assert restored == d


class TestSessionStoreGates:
    def test_open_gate_stores_and_forces_open(self) -> None:
        store = SessionStore()
        session = store.create()
        gate = Gate(phase="train", kind=GateKind.PHASE, description="training phase")
        gate.status = GateStatus.CLOSED  # caller passes closed; must be forced OPEN

        result = store.open_gate(session.id, gate)

        assert result.status == GateStatus.OPEN
        assert result.id == gate.id
        assert store.get(session.id).collab.gates[gate.id].status == GateStatus.OPEN

    def test_open_gate_unknown_session_raises(self) -> None:
        store = SessionStore()
        gate = Gate(phase="train", kind=GateKind.PHASE, description="training")
        with pytest.raises(UnknownSessionError):
            store.open_gate("no-such-session", gate)

    def test_gate_opened_event_is_published(self) -> None:
        store = SessionStore()
        session = store.create()
        q = store.subscribe(session.id)
        gate = Gate(phase="train", kind=GateKind.PHASE, description="training")

        store.open_gate(session.id, gate)

        event = q.get(timeout=1.0)
        assert event == {
            "type": "gate_opened",
            "session_id": session.id,
            "gate_id": gate.id,
        }

    def test_close_gate_transitions_and_publishes(self) -> None:
        store = SessionStore()
        session = store.create()
        gate = store.open_gate(
            session.id, Gate(phase="train", kind=GateKind.PHASE, description="train")
        )
        q = store.subscribe(session.id)

        result = store.close_gate(session.id, gate.id)

        assert result.status == GateStatus.CLOSED
        event = q.get(timeout=1.0)
        assert event == {
            "type": "gate_closed",
            "session_id": session.id,
            "gate_id": gate.id,
        }

    def test_skip_gate_transitions_and_publishes(self) -> None:
        store = SessionStore()
        session = store.create()
        gate = store.open_gate(
            session.id, Gate(phase="train", kind=GateKind.PHASE, description="train")
        )
        q = store.subscribe(session.id)

        result = store.skip_gate(session.id, gate.id)

        assert result.status == GateStatus.SKIPPED
        event = q.get(timeout=1.0)
        assert event == {
            "type": "gate_skipped",
            "session_id": session.id,
            "gate_id": gate.id,
        }

    def test_close_already_closed_gate_raises(self) -> None:
        store = SessionStore()
        session = store.create()
        gate = store.open_gate(
            session.id, Gate(phase="train", kind=GateKind.PHASE, description="train")
        )
        store.close_gate(session.id, gate.id)

        with pytest.raises(GateAlreadyResolvedError):
            store.close_gate(session.id, gate.id)

    def test_skip_already_skipped_gate_raises(self) -> None:
        store = SessionStore()
        session = store.create()
        gate = store.open_gate(
            session.id, Gate(phase="train", kind=GateKind.PHASE, description="train")
        )
        store.skip_gate(session.id, gate.id)

        with pytest.raises(GateAlreadyResolvedError):
            store.skip_gate(session.id, gate.id)

    def test_close_already_skipped_gate_raises(self) -> None:
        store = SessionStore()
        session = store.create()
        gate = store.open_gate(
            session.id, Gate(phase="train", kind=GateKind.PHASE, description="train")
        )
        store.skip_gate(session.id, gate.id)

        with pytest.raises(GateAlreadyResolvedError):
            store.close_gate(session.id, gate.id)

    def test_skip_already_closed_gate_raises(self) -> None:
        store = SessionStore()
        session = store.create()
        gate = store.open_gate(
            session.id, Gate(phase="train", kind=GateKind.PHASE, description="train")
        )
        store.close_gate(session.id, gate.id)

        with pytest.raises(GateAlreadyResolvedError):
            store.skip_gate(session.id, gate.id)

    def test_close_gate_unknown_gate_raises(self) -> None:
        store = SessionStore()
        session = store.create()
        with pytest.raises(UnknownGateError):
            store.close_gate(session.id, "no-such-gate")

    def test_skip_gate_unknown_gate_raises(self) -> None:
        store = SessionStore()
        session = store.create()
        with pytest.raises(UnknownGateError):
            store.skip_gate(session.id, "no-such-gate")

    def test_close_gate_unknown_session_raises(self) -> None:
        store = SessionStore()
        with pytest.raises(UnknownSessionError):
            store.close_gate("no-such-session", "g1")

    def test_skip_gate_unknown_session_raises(self) -> None:
        store = SessionStore()
        with pytest.raises(UnknownSessionError):
            store.skip_gate("no-such-session", "g1")

    def test_add_decision_appends_and_publishes(self) -> None:
        store = SessionStore()
        session = store.create()
        gate = store.open_gate(
            session.id, Gate(phase="train", kind=GateKind.PHASE, description="train")
        )
        q = store.subscribe(session.id)
        decision = Decision(author="human", text="proceed")

        result = store.add_decision(session.id, gate.id, decision)

        assert len(result.decisions) == 1
        assert result.decisions[0].text == "proceed"
        event = q.get(timeout=1.0)
        assert event == {
            "type": "decision_added",
            "session_id": session.id,
            "gate_id": gate.id,
            "decision_id": decision.id,
        }

    def test_add_decision_unknown_gate_raises(self) -> None:
        store = SessionStore()
        session = store.create()
        with pytest.raises(UnknownGateError):
            store.add_decision(session.id, "no-such-gate", Decision(author="human", text="hi"))

    def test_add_decision_unknown_session_raises(self) -> None:
        store = SessionStore()
        with pytest.raises(UnknownSessionError):
            store.add_decision("no-such-session", "g1", Decision(author="human", text="hi"))

    def test_add_decision_on_closed_gate_is_allowed(self) -> None:
        store = SessionStore()
        session = store.create()
        gate = store.open_gate(
            session.id, Gate(phase="train", kind=GateKind.PHASE, description="train")
        )
        store.close_gate(session.id, gate.id)

        result = store.add_decision(
            session.id, gate.id, Decision(author="human", text="retrospective")
        )

        assert len(result.decisions) == 1
