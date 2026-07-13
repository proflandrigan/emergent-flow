"""
tests/test_collab_agents_gemini.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
GeminiAdapter (emergentflow/collab/agents/gemini_adapter.py): argv building and best-effort JSON
event line parsing. These fixtures are hand-constructed against the documented/public Gemini API
response shape -- NOT captured from a live run (see the adapter module's docstring for why) --
so they validate this adapter's own parsing logic is self-consistent, not that it matches the
real CLI's exact wire format.
"""

from __future__ import annotations

import json

from emergentflow.collab.agents.gemini_adapter import GeminiAdapter


class TestBuildCommand:
    def test_first_turn_has_no_session_id_flag(self) -> None:
        adapter = GeminiAdapter()
        argv = adapter.build_command(prompt="hello", resume_id=None)
        assert argv[0] == "gemini"
        assert "-p" in argv
        assert "hello" in argv
        assert "--session-id" not in argv
        assert "-o" in argv
        assert "stream-json" in argv

    def test_later_turn_reuses_session_id_flag(self) -> None:
        adapter = GeminiAdapter()
        argv = adapter.build_command(prompt="another message", resume_id="abc-123")
        assert "--session-id" in argv
        assert argv[argv.index("--session-id") + 1] == "abc-123"


class TestParseLine:
    def test_blank_line_returns_none(self) -> None:
        adapter = GeminiAdapter()
        assert adapter.parse_line("") is None
        assert adapter.parse_line("   ") is None

    def test_malformed_json_returns_none(self) -> None:
        adapter = GeminiAdapter()
        assert adapter.parse_line("not json") is None

    def test_session_id_field_yields_thread_id(self) -> None:
        adapter = GeminiAdapter()
        line = json.dumps({"sessionId": "abc-123"})
        event = adapter.parse_line(line)
        assert event is not None
        assert event.kind == "thread_id"
        assert event.text == "abc-123"

    def test_candidates_text_yields_text(self) -> None:
        adapter = GeminiAdapter()
        line = json.dumps({"candidates": [{"content": {"parts": [{"text": "Added the node."}]}}]})
        event = adapter.parse_line(line)
        assert event is not None
        assert event.kind == "text"
        assert event.text == "Added the node."

    def test_top_level_text_field_yields_text(self) -> None:
        adapter = GeminiAdapter()
        line = json.dumps({"text": "hello there"})
        event = adapter.parse_line(line)
        assert event is not None
        assert event.kind == "text"
        assert event.text == "hello there"

    def test_function_call_with_command_yields_tool_call(self) -> None:
        adapter = GeminiAdapter()
        line = json.dumps(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "functionCall": {
                                        "name": "run_shell_command",
                                        "args": {
                                            "command": "curl -X POST http://127.0.0.1:8765/sessions/s1/proposals"
                                        },
                                    }
                                }
                            ]
                        }
                    }
                ]
            }
        )
        event = adapter.parse_line(line)
        assert event is not None
        assert event.kind == "tool_call"
        assert (
            event.text
            == "run_shell_command: curl -X POST http://127.0.0.1:8765/sessions/s1/proposals"
        )

    def test_function_call_without_command_yields_generic_summary(self) -> None:
        adapter = GeminiAdapter()
        line = json.dumps(
            {"content": {"parts": [{"functionCall": {"name": "read_file", "args": {}}}]}}
        )
        event = adapter.parse_line(line)
        assert event is not None
        assert event.kind == "tool_call"
        assert event.text == "running read_file"

    def test_unrecognized_shape_returns_none(self) -> None:
        adapter = GeminiAdapter()
        line = json.dumps({"unrelated": "data"})
        assert adapter.parse_line(line) is None
