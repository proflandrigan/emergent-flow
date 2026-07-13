"""
emergentflow.collab.agents.opencode_adapter
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
AgentAdapter for the local opencode CLI (`opencode run`). Spawns it in headless mode with
structured JSON events (`--format json`) and ``--auto`` so it never blocks on an interactive
permission prompt it has no TTY to answer, since the spawned agent drives the session purely
over its own shell access to the already-running ``emergentflow serve`` HTTP API
(agents/emergent-flow-collaborator.md).

Parsing here is grounded in two REAL captured ``opencode run --format json`` transcripts (not a
guess): every event is ``{"type": ..., "sessionID": ..., "part": {...}}`` with ``type`` in
``{"step_start", "text", "tool_use", "step_finish"}``. ``sessionID`` is present on every event
but is only surfaced as a ``thread_id`` AdapterEvent from ``step_start`` lines (the first line of
every turn always carries one, and ``step_start``/``step_finish`` lines have no other content
worth showing) — ``text``/``tool_use`` lines surface their own content instead, so a single line
never needs to report two different things at once.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

from emergentflow.collab.agents.base import AdapterEvent, AgentAdapter, register_adapter


def _summarize_tool_use(part: dict[str, Any]) -> str:
    tool = part.get("tool")
    tool_name = tool if isinstance(tool, str) and tool else "tool"
    state = part.get("state")
    command = None
    if isinstance(state, dict):
        tool_input = state.get("input")
        if isinstance(tool_input, dict):
            command = tool_input.get("command")
    if isinstance(command, str) and command:
        return f"{tool_name}: {command}"
    return f"running {tool_name}"


@register_adapter
class OpenCodeAdapter(AgentAdapter):
    name: ClassVar[str] = "opencode"
    cli_executable: ClassVar[str] = "opencode"

    def build_command(self, *, prompt: str, resume_id: str | None) -> list[str]:
        argv = [
            self.cli_executable,
            "run",
            prompt,
            "--format",
            "json",
            "--auto",
        ]
        if resume_id is not None:
            argv += ["--session", resume_id]
        return argv

    def parse_line(self, raw_line: str) -> AdapterEvent | None:
        line = raw_line.strip()
        if not line:
            return None
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return None
        if not isinstance(event, dict):
            return None

        event_type = event.get("type")
        part = event.get("part")
        part = part if isinstance(part, dict) else {}

        if event_type == "step_start":
            session_id = event.get("sessionID")
            if isinstance(session_id, str) and session_id:
                return AdapterEvent(kind="thread_id", text=session_id)
            return None

        if event_type == "text":
            text = part.get("text")
            if isinstance(text, str) and text:
                return AdapterEvent(kind="text", text=text)
            return None

        if event_type == "tool_use":
            return AdapterEvent(kind="tool_call", text=_summarize_tool_use(part))

        return None
