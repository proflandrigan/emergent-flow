"""
tests/test_collab_agents_codex.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
CodexAdapter (emergentflow/collab/agents/codex_adapter.py): argv building and best-effort JSON
event line parsing. These fixtures are hand-constructed placeholders -- NOT captured from a live
run and not checked against `codex --help` (the CLI is not installed on this machine; see the
adapter module's docstring) -- so they validate this adapter's own parsing logic is
self-consistent, not that it matches the real CLI's exact wire format.
"""

from __future__ import annotations

import json

from emergentflow.collab.agents.codex_adapter import CodexAdapter


class TestBuildCommand:
    def test_first_turn_has_no_resume_subcommand(self) -> None:
        adapter = CodexAdapter()
        argv = adapter.build_command(prompt="hello", resume_id=None)
        assert argv[0] == "codex"
        assert argv[1] == "exec"
        assert "resume" not in argv
        assert "hello" in argv
        assert "--json" in argv

    def test_later_turn_includes_resume_subcommand(self) -> None:
        adapter = CodexAdapter()
        argv = adapter.build_command(prompt="another message", resume_id="thread-abc")
        assert argv[0] == "codex"
        assert argv[1] == "exec"
        assert argv[2] == "resume"
        assert argv[3] == "thread-abc"
        assert "another message" in argv


class TestParseLine:
    def test_blank_line_returns_none(self) -> None:
        adapter = CodexAdapter()
        assert adapter.parse_line("") is None
        assert adapter.parse_line("   ") is None

    def test_malformed_json_returns_none(self) -> None:
        adapter = CodexAdapter()
        assert adapter.parse_line("not json") is None

    def test_top_level_session_id_yields_thread_id(self) -> None:
        adapter = CodexAdapter()
        line = json.dumps({"session_id": "abc-123"})
        event = adapter.parse_line(line)
        assert event is not None
        assert event.kind == "thread_id"
        assert event.text == "abc-123"

    def test_nested_msg_thread_id_yields_thread_id(self) -> None:
        adapter = CodexAdapter()
        line = json.dumps({"msg": {"conversation_id": "conv-456"}})
        event = adapter.parse_line(line)
        assert event is not None
        assert event.kind == "thread_id"
        assert event.text == "conv-456"

    def test_top_level_message_yields_text(self) -> None:
        adapter = CodexAdapter()
        line = json.dumps({"message": "Added the node."})
        event = adapter.parse_line(line)
        assert event is not None
        assert event.kind == "text"
        assert event.text == "Added the node."

    def test_nested_msg_text_yields_text(self) -> None:
        adapter = CodexAdapter()
        line = json.dumps({"msg": {"text": "hello there"}})
        event = adapter.parse_line(line)
        assert event is not None
        assert event.kind == "text"
        assert event.text == "hello there"

    def test_string_command_yields_tool_call(self) -> None:
        adapter = CodexAdapter()
        line = json.dumps({"command": "curl -X POST http://127.0.0.1:8765/sessions/s1/proposals"})
        event = adapter.parse_line(line)
        assert event is not None
        assert event.kind == "tool_call"
        assert event.text == "running: curl -X POST http://127.0.0.1:8765/sessions/s1/proposals"

    def test_list_command_is_joined(self) -> None:
        adapter = CodexAdapter()
        line = json.dumps({"cmd": ["curl", "-X", "POST", "http://127.0.0.1:8765"]})
        event = adapter.parse_line(line)
        assert event is not None
        assert event.kind == "tool_call"
        assert event.text == "running: curl -X POST http://127.0.0.1:8765"

    def test_unrecognized_shape_returns_none(self) -> None:
        adapter = CodexAdapter()
        line = json.dumps({"unrelated": "data"})
        assert adapter.parse_line(line) is None
