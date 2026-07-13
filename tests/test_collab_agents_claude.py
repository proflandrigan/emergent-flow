"""
tests/test_collab_agents_claude.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
ClaudeAdapter (emergentflow/collab/agents/claude_adapter.py): argv building and stream-json
line parsing.
"""

from __future__ import annotations

import json

from emergentflow.collab.agents.claude_adapter import ClaudeAdapter


class TestBuildCommand:
    def test_first_turn_has_no_resume_flag(self) -> None:
        adapter = ClaudeAdapter()
        argv = adapter.build_command(prompt="hello", resume_id=None)
        assert argv[0] == "claude"
        assert "hello" in argv
        assert "--resume" not in argv
        assert "--output-format" in argv
        assert "stream-json" in argv

    def test_later_turn_includes_resume_flag(self) -> None:
        adapter = ClaudeAdapter()
        argv = adapter.build_command(prompt="another message", resume_id="thread-abc")
        assert "--resume" in argv
        assert argv[argv.index("--resume") + 1] == "thread-abc"


class TestParseLine:
    def test_blank_line_returns_none(self) -> None:
        adapter = ClaudeAdapter()
        assert adapter.parse_line("") is None
        assert adapter.parse_line("   ") is None

    def test_malformed_json_returns_none(self) -> None:
        adapter = ClaudeAdapter()
        assert adapter.parse_line("not json") is None

    def test_system_init_line_yields_thread_id(self) -> None:
        adapter = ClaudeAdapter()
        line = json.dumps({"type": "system", "subtype": "init", "session_id": "abc-123"})
        event = adapter.parse_line(line)
        assert event is not None
        assert event.kind == "thread_id"
        assert event.text == "abc-123"

    def test_assistant_text_block_yields_text(self) -> None:
        adapter = ClaudeAdapter()
        line = json.dumps(
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "Added the node."}]},
            }
        )
        event = adapter.parse_line(line)
        assert event is not None
        assert event.kind == "text"
        assert event.text == "Added the node."

    def test_assistant_tool_use_block_yields_tool_call_with_command(self) -> None:
        adapter = ClaudeAdapter()
        line = json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Bash",
                            "input": {
                                "command": "curl -X POST http://127.0.0.1:8765/sessions/s1/proposals"
                            },
                        }
                    ]
                },
            }
        )
        event = adapter.parse_line(line)
        assert event is not None
        assert event.kind == "tool_call"
        assert event.text == "Bash: curl -X POST http://127.0.0.1:8765/sessions/s1/proposals"

    def test_assistant_tool_use_without_command_yields_generic_summary(self) -> None:
        adapter = ClaudeAdapter()
        line = json.dumps(
            {
                "type": "assistant",
                "message": {"content": [{"type": "tool_use", "name": "Read", "input": {}}]},
            }
        )
        event = adapter.parse_line(line)
        assert event is not None
        assert event.kind == "tool_call"
        assert event.text == "running Read"

    def test_unrecognized_type_returns_none(self) -> None:
        adapter = ClaudeAdapter()
        line = json.dumps({"type": "result", "subtype": "success"})
        assert adapter.parse_line(line) is None

    def test_system_line_without_init_subtype_returns_none(self) -> None:
        adapter = ClaudeAdapter()
        line = json.dumps({"type": "system", "subtype": "other"})
        assert adapter.parse_line(line) is None
