"""
emergentflow.collab.agents.claude_adapter
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
AgentAdapter for the Claude Code CLI (`claude`). Spawns it in headless/print mode with
structured JSON streaming output (`-p --output-format stream-json`) and a Bash-only tool
allowlist, since the spawned agent drives the session purely over its own curl access to the
already-running `emergentflow serve` HTTP API (agents/emergent-flow-collaborator.md) -- it needs
no file-editing or other tool access to participate in a chat session. `--permission-mode
bypassPermissions` avoids the process hanging on an interactive approval prompt it has no TTY to
answer; this is a best-effort choice against the currently-installed CLI version and may need
adjusting as the CLI's flags evolve.

Best-effort parsing of Claude Code's stream-json message shape (system/init, assistant
text/tool_use blocks); a message whose content array has more than one recognized block
surfaces only the first one per line -- a known v1 limitation.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

from emergentflow.collab.agents.base import AdapterEvent, AgentAdapter, register_adapter


def _summarize_tool_use(name: str, tool_input: dict[str, Any]) -> str:
    command = tool_input.get("command")
    if isinstance(command, str) and command:
        return f"{name}: {command}"
    return f"running {name}"


@register_adapter
class ClaudeAdapter(AgentAdapter):
    name: ClassVar[str] = "claude"
    cli_executable: ClassVar[str] = "claude"

    def build_command(self, *, prompt: str, resume_id: str | None) -> list[str]:
        argv = [
            self.cli_executable,
            "-p",
            prompt,
            "--output-format",
            "stream-json",
            "--verbose",
            "--allowedTools",
            "Bash",
            "--permission-mode",
            "bypassPermissions",
        ]
        if resume_id is not None:
            argv += ["--resume", resume_id]
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
        if event_type == "system" and event.get("subtype") == "init":
            session_id = event.get("session_id")
            if isinstance(session_id, str) and session_id:
                return AdapterEvent(kind="thread_id", text=session_id)
            return None

        if event_type == "assistant":
            message = event.get("message")
            if not isinstance(message, dict):
                return None
            content = message.get("content")
            if not isinstance(content, list):
                return None
            for block in content:
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type")
                if block_type == "text":
                    text = block.get("text")
                    if isinstance(text, str) and text:
                        return AdapterEvent(kind="text", text=text)
                elif block_type == "tool_use":
                    tool_name = block.get("name")
                    tool_input = block.get("input")
                    if isinstance(tool_name, str):
                        summary = _summarize_tool_use(
                            tool_name, tool_input if isinstance(tool_input, dict) else {}
                        )
                        return AdapterEvent(kind="tool_call", text=summary)
            return None

        return None
