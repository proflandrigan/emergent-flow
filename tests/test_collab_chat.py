"""
tests/test_collab_chat.py
~~~~~~~~~~~~~~~~~~~~~~~~~~
Chat models (emergentflow/collab/chat.py). Mirrors tests/test_collab_gates.py's structure and
conventions for its model-only tests (TestGateModel). SessionStore chat-lifecycle-method tests
land in a later task alongside the SessionStore methods themselves.
"""

from __future__ import annotations

import pytest

from emergentflow.collab.chat import (
    ChatAlreadyActiveError,
    ChatState,
    ChatTurn,
    ChatTurnAlreadyResolvedError,
    ChatTurnStatus,
    UnknownChatTurnError,
)
from emergentflow.collab.session import SessionStore, UnknownSessionError


class TestChatTurnModel:
    def test_defaults(self) -> None:
        turn = ChatTurn(backend="claude", user_message="add a cleaning step")
        assert turn.status == ChatTurnStatus.RUNNING
        assert turn.narration == []
        assert turn.agent_message is None
        assert turn.error is None

    def test_round_trips_through_json(self) -> None:
        turn = ChatTurn(
            backend="claude",
            user_message="add a cleaning step",
            narration=["proposing mutation: add node clean.drop_na"],
            agent_message="Added a clean.drop_na node.",
            status=ChatTurnStatus.COMPLETED,
        )
        dumped = turn.model_dump(mode="json")
        restored = ChatTurn.model_validate(dumped)
        assert restored == turn


class TestChatStateModel:
    def test_defaults(self) -> None:
        state = ChatState()
        assert state.backend is None
        assert state.backend_thread_id is None
        assert state.turns == []

    def test_round_trips_through_json(self) -> None:
        state = ChatState(
            backend="claude",
            backend_thread_id="abc-123",
            turns=[ChatTurn(backend="claude", user_message="hello")],
        )
        dumped = state.model_dump(mode="json")
        restored = ChatState.model_validate(dumped)
        assert restored == state


class TestSessionStoreChat:
    def test_start_chat_turn_creates_and_publishes(self) -> None:
        store = SessionStore()
        session = store.create()
        q = store.subscribe(session.id)

        turn = store.start_chat_turn(session.id, "claude", "add a cleaning step")

        assert turn.backend == "claude"
        assert turn.user_message == "add a cleaning step"
        assert turn.status == ChatTurnStatus.RUNNING
        assert store.get(session.id).collab.chat.backend == "claude"
        assert store.get(session.id).collab.chat.turns == [turn]
        event = q.get(timeout=1.0)
        assert event == {
            "type": "chat_turn_started",
            "session_id": session.id,
            "turn_id": turn.id,
        }

    def test_start_chat_turn_unknown_session_raises(self) -> None:
        store = SessionStore()
        with pytest.raises(UnknownSessionError):
            store.start_chat_turn("no-such-session", "claude", "hi")

    def test_start_chat_turn_different_backend_raises(self) -> None:
        store = SessionStore()
        session = store.create()
        store.start_chat_turn(session.id, "claude", "hi")
        store.complete_chat_turn(session.id, store.get(session.id).collab.chat.turns[0].id, "done")

        with pytest.raises(ChatAlreadyActiveError):
            store.start_chat_turn(session.id, "codex", "hi again")

    def test_start_chat_turn_while_previous_running_raises(self) -> None:
        store = SessionStore()
        session = store.create()
        store.start_chat_turn(session.id, "claude", "hi")

        with pytest.raises(ChatAlreadyActiveError):
            store.start_chat_turn(session.id, "claude", "another message")

    def test_start_chat_turn_same_backend_after_resolved_is_allowed(self) -> None:
        store = SessionStore()
        session = store.create()
        first = store.start_chat_turn(session.id, "claude", "hi")
        store.complete_chat_turn(session.id, first.id, "done")

        second = store.start_chat_turn(session.id, "claude", "another message")

        assert second.id != first.id
        assert store.get(session.id).collab.chat.turns == [first, second]

    def test_append_chat_narration_appends_and_publishes(self) -> None:
        store = SessionStore()
        session = store.create()
        turn = store.start_chat_turn(session.id, "claude", "hi")
        q = store.subscribe(session.id)

        result = store.append_chat_narration(session.id, turn.id, "running POST /validate")

        assert result.narration == ["running POST /validate"]
        event = q.get(timeout=1.0)
        assert event == {
            "type": "chat_narration_added",
            "session_id": session.id,
            "turn_id": turn.id,
        }

    def test_append_chat_narration_unknown_turn_raises(self) -> None:
        store = SessionStore()
        session = store.create()
        with pytest.raises(UnknownChatTurnError):
            store.append_chat_narration(session.id, "no-such-turn", "text")

    def test_append_chat_narration_on_resolved_turn_raises(self) -> None:
        store = SessionStore()
        session = store.create()
        turn = store.start_chat_turn(session.id, "claude", "hi")
        store.complete_chat_turn(session.id, turn.id, "done")

        with pytest.raises(ChatTurnAlreadyResolvedError):
            store.append_chat_narration(session.id, turn.id, "too late")

    def test_complete_chat_turn_transitions_and_publishes(self) -> None:
        store = SessionStore()
        session = store.create()
        turn = store.start_chat_turn(session.id, "claude", "hi")
        q = store.subscribe(session.id)

        result = store.complete_chat_turn(session.id, turn.id, "Added the node.")

        assert result.status == ChatTurnStatus.COMPLETED
        assert result.agent_message == "Added the node."
        event = q.get(timeout=1.0)
        assert event == {
            "type": "chat_turn_completed",
            "session_id": session.id,
            "turn_id": turn.id,
        }

    def test_fail_chat_turn_transitions_and_publishes(self) -> None:
        store = SessionStore()
        session = store.create()
        turn = store.start_chat_turn(session.id, "claude", "hi")
        q = store.subscribe(session.id)

        result = store.fail_chat_turn(session.id, turn.id, "claude: command not found")

        assert result.status == ChatTurnStatus.FAILED
        assert result.error == "claude: command not found"
        event = q.get(timeout=1.0)
        assert event == {
            "type": "chat_turn_failed",
            "session_id": session.id,
            "turn_id": turn.id,
        }

    def test_interrupt_chat_turn_transitions_and_publishes(self) -> None:
        store = SessionStore()
        session = store.create()
        turn = store.start_chat_turn(session.id, "claude", "hi")
        q = store.subscribe(session.id)

        result = store.interrupt_chat_turn(session.id, turn.id)

        assert result.status == ChatTurnStatus.INTERRUPTED
        event = q.get(timeout=1.0)
        assert event == {
            "type": "chat_turn_interrupted",
            "session_id": session.id,
            "turn_id": turn.id,
        }

    def test_complete_already_resolved_turn_raises(self) -> None:
        store = SessionStore()
        session = store.create()
        turn = store.start_chat_turn(session.id, "claude", "hi")
        store.complete_chat_turn(session.id, turn.id, "done")

        with pytest.raises(ChatTurnAlreadyResolvedError):
            store.complete_chat_turn(session.id, turn.id, "done again")

    def test_set_chat_thread_id_sets_value(self) -> None:
        store = SessionStore()
        session = store.create()

        store.set_chat_thread_id(session.id, "thread-abc")

        assert store.get(session.id).collab.chat.backend_thread_id == "thread-abc"

    def test_set_chat_thread_id_unknown_session_raises(self) -> None:
        store = SessionStore()
        with pytest.raises(UnknownSessionError):
            store.set_chat_thread_id("no-such-session", "thread-abc")

    def test_end_chat_clears_backend_but_keeps_turns(self) -> None:
        store = SessionStore()
        session = store.create()
        turn = store.start_chat_turn(session.id, "claude", "hi")
        store.complete_chat_turn(session.id, turn.id, "done")
        store.set_chat_thread_id(session.id, "thread-abc")
        q = store.subscribe(session.id)

        store.end_chat(session.id)

        chat = store.get(session.id).collab.chat
        assert chat.backend is None
        assert chat.backend_thread_id is None
        assert chat.turns == [turn]
        event = q.get(timeout=1.0)
        assert event == {"type": "chat_ended", "session_id": session.id}

    def test_end_chat_unknown_session_raises(self) -> None:
        store = SessionStore()
        with pytest.raises(UnknownSessionError):
            store.end_chat("no-such-session")
