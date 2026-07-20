"""
tests/test_collab_chat_runner.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
emergentflow/collab/chat_runner.py: subprocess orchestration for the in-app agent chat feature.
Exercises real (but tiny, deterministic, python-interpreter-based) subprocesses via throwaway
test-only AgentAdapters registered just for this file -- not any of the four real CLI adapters,
which are never spawned in tests.
"""

from __future__ import annotations

import json
import sys
import time
from typing import ClassVar

import pytest

from emergentflow.collab import chat_runner
from emergentflow.collab.agents.base import AdapterEvent, AgentAdapter, register_adapter
from emergentflow.collab.chat import ChatTurnStatus
from emergentflow.collab.session import SessionStore

_HAPPY_SCRIPT = (
    "import json\n"
    "print(json.dumps({'type': 'thread_id', 'text': 'thread-xyz'}))\n"
    "print(json.dumps({'type': 'tool_call', 'text': 'running curl'}))\n"
    "print(json.dumps({'type': 'text', 'text': 'All done.'}))\n"
)

_FAILING_SCRIPT = "import sys\nsys.stderr.write('boom: something broke')\nsys.exit(1)\n"

_SLOW_SCRIPT = "import time\ntime.sleep(30)\n"

_ECHO_SCRIPT_TEMPLATE = "import json\nprint(json.dumps({{'type': 'text', 'text': {prompt!r}}}))\n"


class _FakeChatAdapter(AgentAdapter):
    """Base for test-only adapters: spawns `python -c <SCRIPT>` and parses simple
    `{"type": ..., "text": ...}` JSON lines directly into an AdapterEvent."""

    cli_executable: ClassVar[str] = sys.executable
    SCRIPT: ClassVar[str] = ""

    def build_command(self, *, prompt: str, resume_id: str | None) -> list[str]:
        return [sys.executable, "-c", self.SCRIPT]

    def parse_line(self, raw_line: str) -> AdapterEvent | None:
        line = raw_line.strip()
        if not line:
            return None
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            return None
        return AdapterEvent(kind=data["type"], text=data["text"])


@register_adapter
class _HappyChatAdapter(_FakeChatAdapter):
    name: ClassVar[str] = "fake-chat-happy"
    SCRIPT: ClassVar[str] = _HAPPY_SCRIPT


@register_adapter
class _FailingChatAdapter(_FakeChatAdapter):
    name: ClassVar[str] = "fake-chat-failing"
    SCRIPT: ClassVar[str] = _FAILING_SCRIPT


@register_adapter
class _SlowChatAdapter(_FakeChatAdapter):
    name: ClassVar[str] = "fake-chat-slow"
    SCRIPT: ClassVar[str] = _SLOW_SCRIPT


@register_adapter
class _EchoChatAdapter(AgentAdapter):
    """Echoes the exact *prompt* chat_runner built back as its "text" reply, so tests can
    assert on the prompt-assembly logic without inspecting Popen args directly."""

    name: ClassVar[str] = "fake-chat-echo"
    cli_executable: ClassVar[str] = sys.executable

    def build_command(self, *, prompt: str, resume_id: str | None) -> list[str]:
        script = _ECHO_SCRIPT_TEMPLATE.format(prompt=prompt)
        return [sys.executable, "-c", script]

    def parse_line(self, raw_line: str) -> AdapterEvent | None:
        line = raw_line.strip()
        if not line:
            return None
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            return None
        return AdapterEvent(kind=data["type"], text=data["text"])


def _wait_for_status(
    store: SessionStore, session_id: str, turn_id: str, timeout: float = 5.0
) -> ChatTurnStatus:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        turn = next(t for t in store.get(session_id).collab.chat.turns if t.id == turn_id)
        if turn.status != ChatTurnStatus.RUNNING:
            return turn.status
        time.sleep(0.05)
    raise TimeoutError(f"turn {turn_id} did not resolve within {timeout}s")


class TestStartChatTurn:
    def test_unknown_backend_raises(self) -> None:
        store = SessionStore()
        session = store.create()
        with pytest.raises(chat_runner.UnknownBackendError):
            chat_runner.start_chat_turn(
                session.id, "no-such-backend", "hi", base_url="http://127.0.0.1:8765"
            )

    def test_happy_path_completes_with_narration_and_thread_id(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = SessionStore()
        monkeypatch.setattr(chat_runner, "get_default_store", lambda: store)
        session = store.create()

        turn = chat_runner.start_chat_turn(
            session.id, "fake-chat-happy", "hello", base_url="http://127.0.0.1:8765"
        )

        status = _wait_for_status(store, session.id, turn.id)
        assert status == ChatTurnStatus.COMPLETED
        resolved = store.get(session.id).collab.chat.turns[0]
        assert resolved.agent_message == "All done."
        assert resolved.narration == ["running curl"]
        assert store.get(session.id).collab.chat.backend_thread_id == "thread-xyz"

    def test_failing_process_marks_turn_failed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        store = SessionStore()
        monkeypatch.setattr(chat_runner, "get_default_store", lambda: store)
        session = store.create()

        turn = chat_runner.start_chat_turn(
            session.id, "fake-chat-failing", "hello", base_url="http://127.0.0.1:8765"
        )

        status = _wait_for_status(store, session.id, turn.id)
        assert status == ChatTurnStatus.FAILED
        resolved = store.get(session.id).collab.chat.turns[0]
        assert resolved.error is not None
        assert "boom" in resolved.error

    def test_first_turn_prompt_includes_protocol_and_session_context(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = SessionStore()
        monkeypatch.setattr(chat_runner, "get_default_store", lambda: store)
        session = store.create()

        turn = chat_runner.start_chat_turn(
            session.id,
            "fake-chat-echo",
            "add a cleaning step",
            base_url="http://127.0.0.1:8765",
        )
        status = _wait_for_status(store, session.id, turn.id)
        assert status == ChatTurnStatus.COMPLETED
        echoed_prompt = store.get(session.id).collab.chat.turns[0].agent_message
        assert echoed_prompt is not None
        assert "add a cleaning step" in echoed_prompt
        assert session.id in echoed_prompt
        assert "http://127.0.0.1:8765" in echoed_prompt
        assert "Emergent Flow Collaborator" in echoed_prompt

    def test_second_turn_prompt_is_just_the_user_message(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = SessionStore()
        monkeypatch.setattr(chat_runner, "get_default_store", lambda: store)
        session = store.create()
        first = chat_runner.start_chat_turn(
            session.id, "fake-chat-echo", "first message", base_url="http://127.0.0.1:8765"
        )
        _wait_for_status(store, session.id, first.id)
        # fake-chat-echo never emits a thread_id event; force one, as if a real CLI had reported
        # one, so this turn takes the "later turn" (resume_id is not None) branch.
        store.set_chat_thread_id(session.id, "resume-abc")

        second = chat_runner.start_chat_turn(
            session.id, "fake-chat-echo", "second message", base_url="http://127.0.0.1:8765"
        )
        _wait_for_status(store, session.id, second.id)
        echoed_prompt = store.get(session.id).collab.chat.turns[1].agent_message
        assert echoed_prompt == "second message"


class TestDetectPersonaCommand:
    def test_recognizes_data_scientist(self) -> None:
        assert chat_runner._detect_persona_command("/data-scientist") == "data-scientist.md"

    def test_recognizes_researcher(self) -> None:
        assert chat_runner._detect_persona_command("/researcher") == "researcher.md"

    def test_recognizes_ml_engineer(self) -> None:
        assert chat_runner._detect_persona_command("/ml-engineer") == "ml-engineer.md"

    def test_case_insensitive(self) -> None:
        result = chat_runner._detect_persona_command("/Data-Scientist review this")
        assert result == "data-scientist.md"

    def test_ignores_trailing_text(self) -> None:
        result = chat_runner._detect_persona_command("/researcher build me a pipeline")
        assert result == "researcher.md"

    def test_returns_none_for_unknown(self) -> None:
        assert chat_runner._detect_persona_command("/unknown-command") is None

    def test_returns_none_for_empty(self) -> None:
        assert chat_runner._detect_persona_command("") is None

    def test_returns_none_for_plain_message(self) -> None:
        assert chat_runner._detect_persona_command("just a normal message") is None


class TestPersonaSlashCommands:
    def test_first_turn_with_persona_injects_persona_block(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = SessionStore()
        monkeypatch.setattr(chat_runner, "get_default_store", lambda: store)
        session = store.create()

        turn = chat_runner.start_chat_turn(
            session.id,
            "fake-chat-echo",
            "/data-scientist review my pipeline",
            base_url="http://127.0.0.1:8765",
        )
        status = _wait_for_status(store, session.id, turn.id)
        assert status == ChatTurnStatus.COMPLETED
        echoed = store.get(session.id).collab.chat.turns[0].agent_message
        assert echoed is not None
        assert "Your persona" in echoed
        assert "Data Scientist" in echoed or "data scientist" in echoed.lower()
        assert "Emergent Flow Collaborator" in echoed

    def test_persona_sets_active_persona_on_chat_state(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = SessionStore()
        monkeypatch.setattr(chat_runner, "get_default_store", lambda: store)
        session = store.create()

        turn = chat_runner.start_chat_turn(
            session.id,
            "fake-chat-echo",
            "/data-scientist hello",
            base_url="http://127.0.0.1:8765",
        )
        _wait_for_status(store, session.id, turn.id)
        assert store.get(session.id).collab.chat.active_persona == "data_scientist"

    def test_resume_with_persona_switch_injects_switch_block(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = SessionStore()
        monkeypatch.setattr(chat_runner, "get_default_store", lambda: store)
        session = store.create()

        first = chat_runner.start_chat_turn(
            session.id, "fake-chat-echo", "first message", base_url="http://127.0.0.1:8765"
        )
        _wait_for_status(store, session.id, first.id)
        store.set_chat_thread_id(session.id, "resume-abc")

        second = chat_runner.start_chat_turn(
            session.id,
            "fake-chat-echo",
            "/ml-engineer check the serving path",
            base_url="http://127.0.0.1:8765",
        )
        _wait_for_status(store, session.id, second.id)
        echoed = store.get(session.id).collab.chat.turns[1].agent_message
        assert echoed is not None
        assert "Persona switch" in echoed
        assert store.get(session.id).collab.chat.active_persona == "ml_engineer"

    def test_resume_without_persona_sends_raw_message(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = SessionStore()
        monkeypatch.setattr(chat_runner, "get_default_store", lambda: store)
        session = store.create()

        first = chat_runner.start_chat_turn(
            session.id, "fake-chat-echo", "/researcher hello", base_url="http://127.0.0.1:8765"
        )
        _wait_for_status(store, session.id, first.id)
        store.set_chat_thread_id(session.id, "resume-abc")

        second = chat_runner.start_chat_turn(
            session.id,
            "fake-chat-echo",
            "continue our conversation",
            base_url="http://127.0.0.1:8765",
        )
        _wait_for_status(store, session.id, second.id)
        echoed = store.get(session.id).collab.chat.turns[1].agent_message
        assert echoed == "continue our conversation"
        assert store.get(session.id).collab.chat.active_persona == "researcher"

    def test_end_chat_clears_active_persona(self, monkeypatch: pytest.MonkeyPatch) -> None:
        store = SessionStore()
        monkeypatch.setattr(chat_runner, "get_default_store", lambda: store)
        session = store.create()

        turn = chat_runner.start_chat_turn(
            session.id,
            "fake-chat-echo",
            "/data-scientist hello",
            base_url="http://127.0.0.1:8765",
        )
        _wait_for_status(store, session.id, turn.id)
        assert store.get(session.id).collab.chat.active_persona == "data_scientist"

        store.end_chat(session.id)
        assert store.get(session.id).collab.chat.active_persona is None


class TestStopChatTurn:
    def test_stop_interrupts_a_running_turn(self, monkeypatch: pytest.MonkeyPatch) -> None:
        store = SessionStore()
        monkeypatch.setattr(chat_runner, "get_default_store", lambda: store)
        session = store.create()

        turn = chat_runner.start_chat_turn(
            session.id, "fake-chat-slow", "hello", base_url="http://127.0.0.1:8765"
        )
        time.sleep(0.2)  # let the subprocess actually start before stopping it

        chat_runner.stop_chat_turn(session.id, turn.id)

        status = _wait_for_status(store, session.id, turn.id, timeout=10.0)
        assert status == ChatTurnStatus.INTERRUPTED

    def test_stop_immediately_after_start_still_interrupts(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regression test: stop_chat_turn called with NO delay, racing _run_turn's own
        subprocess spawn -- closes the window where a fast Stop click (or a slow-to-cold-start
        CLI) could leave the spawned process running unstopped even though the UI shows the
        turn as interrupted. Without the _STOP_REQUESTED handshake this would very likely (not
        just theoretically) resolve as COMPLETED after the full 30-second sleep script runs to
        completion, timing out this test's 10-second wait."""
        store = SessionStore()
        monkeypatch.setattr(chat_runner, "get_default_store", lambda: store)
        session = store.create()

        turn = chat_runner.start_chat_turn(
            session.id, "fake-chat-slow", "hello", base_url="http://127.0.0.1:8765"
        )
        chat_runner.stop_chat_turn(session.id, turn.id)

        status = _wait_for_status(store, session.id, turn.id, timeout=10.0)
        assert status == ChatTurnStatus.INTERRUPTED
