"""
tests/test_collab_agents_opencode.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
OpenCodeAdapter (emergentflow/collab/agents/opencode_adapter.py): argv building and JSON event
line parsing, using real captured ``opencode run --format json`` transcripts as fixtures.
"""

from __future__ import annotations

import json

from emergentflow.collab.agents.opencode_adapter import OpenCodeAdapter


class TestBuildCommand:
    def test_first_turn_has_no_session_flag(self) -> None:
        adapter = OpenCodeAdapter()
        argv = adapter.build_command(prompt="hello", resume_id=None)
        assert argv[0] == "opencode"
        assert argv[1] == "run"
        assert "hello" in argv
        assert "--session" not in argv
        assert "--format" in argv
        assert "json" in argv
        assert "--auto" in argv

    def test_later_turn_includes_session_flag(self) -> None:
        adapter = OpenCodeAdapter()
        argv = adapter.build_command(prompt="another message", resume_id="ses_abc123")
        assert "--session" in argv
        assert argv[argv.index("--session") + 1] == "ses_abc123"


class TestParseLine:
    def test_blank_line_returns_none(self) -> None:
        adapter = OpenCodeAdapter()
        assert adapter.parse_line("") is None
        assert adapter.parse_line("   ") is None

    def test_malformed_json_returns_none(self) -> None:
        adapter = OpenCodeAdapter()
        assert adapter.parse_line("not json") is None

    def test_step_start_yields_thread_id(self) -> None:
        adapter = OpenCodeAdapter()
        line = (
            '{"type":"step_start","timestamp":1783908070201,'
            '"sessionID":"ses_0a6cb1510ffefpLwmyL357Q1RQ",'
            '"part":{"id":"prt_f5934f335001N0obwEA39CniCw",'
            '"messageID":"msg_f5934ec84001QqAgzSoBS394NS",'
            '"sessionID":"ses_0a6cb1510ffefpLwmyL357Q1RQ","type":"step-start"}}'
        )
        event = adapter.parse_line(line)
        assert event is not None
        assert event.kind == "thread_id"
        assert event.text == "ses_0a6cb1510ffefpLwmyL357Q1RQ"

    def test_text_event_yields_text(self) -> None:
        adapter = OpenCodeAdapter()
        line = (
            '{"type":"text","timestamp":1783908070949,'
            '"sessionID":"ses_0a6cb1510ffefpLwmyL357Q1RQ",'
            '"part":{"id":"prt_f5934f5b10016mSOXm52FrUkX2",'
            '"messageID":"msg_f5934ec84001QqAgzSoBS394NS",'
            '"sessionID":"ses_0a6cb1510ffefpLwmyL357Q1RQ","type":"text","text":"pong",'
            '"time":{"start":1783908070833,"end":1783908070913}}}'
        )
        event = adapter.parse_line(line)
        assert event is not None
        assert event.kind == "text"
        assert event.text == "pong"

    def test_tool_use_event_yields_tool_call_with_command(self) -> None:
        adapter = OpenCodeAdapter()
        line = (
            '{"type":"tool_use","timestamp":1783908083393,'
            '"sessionID":"ses_0a6cae5a3ffeuKkxWrIzzLz68t",'
            '"part":{"type":"tool","tool":"bash",'
            '"callID":"call_00_TiyNMUa0hx2503yNRGn09925",'
            '"state":{"status":"completed","input":{"command":"echo hi"},'
            '"output":"hi\\n","metadata":{"output":"hi\\n","exit":0,"truncated":false},'
            '"title":"echo hi","time":{"start":1783908083344,"end":1783908083353}},'
            '"id":"prt_f59352595001bfjCyRmktfGHW2","sessionID":"ses_0a6cae5a3ffeuKkxWrIzzLz68t",'
            '"messageID":"msg_f59351bed001NyMu6R2tRArASV"}}'
        )
        event = adapter.parse_line(line)
        assert event is not None
        assert event.kind == "tool_call"
        assert event.text == "bash: echo hi"

    def test_tool_use_without_command_yields_generic_summary(self) -> None:
        adapter = OpenCodeAdapter()
        line = json.dumps(
            {
                "type": "tool_use",
                "sessionID": "ses_x",
                "part": {"type": "tool", "tool": "read", "state": {"input": {}}},
            }
        )
        event = adapter.parse_line(line)
        assert event is not None
        assert event.kind == "tool_call"
        assert event.text == "running read"

    def test_step_finish_returns_none(self) -> None:
        adapter = OpenCodeAdapter()
        line = (
            '{"type":"step_finish","timestamp":1783908070949,'
            '"sessionID":"ses_0a6cb1510ffefpLwmyL357Q1RQ",'
            '"part":{"id":"prt_f5934f60c001oY5kV995itW8gr","reason":"stop",'
            '"messageID":"msg_f5934ec84001QqAgzSoBS394NS",'
            '"sessionID":"ses_0a6cb1510ffefpLwmyL357Q1RQ","type":"step-finish",'
            '"tokens":{"total":10076,"input":10053,"output":3,"reasoning":20,'
            '"cache":{"write":0,"read":0}},"cost":0}}'
        )
        assert adapter.parse_line(line) is None
