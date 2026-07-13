"""
emergentflow.collab.agents.codex_adapter
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
AgentAdapter for the OpenAI Codex CLI (`codex`). BEST-EFFORT AND UNVERIFIED, more so than the
Gemini adapter: the `codex` CLI is not installed on this development machine at all, so neither
its flags NOR its JSON event shape could be checked against `--help` or a live run (contrast
opencode_adapter.py, captured from real output, and gemini_adapter.py, at least checked against
`gemini --help`). `detect()` (inherited from AgentAdapter) returns False wherever `codex` isn't
on PATH, so this adapter simply won't appear in the "Start chat" backend picker until someone
has it installed -- correctness here matters only once that happens. `build_command` assumes a
`codex exec <prompt> --json` non-interactive mode with a `codex exec resume <id> <prompt> --json`
continuation form, based on the CLI's general publicly-documented shape at the time this was
written; `parse_line` degrades gracefully (returns None) for any line shape it doesn't recognize,
checking several plausible field names (`message`/`text`/`content` for text, `command`/`cmd` for
tool calls, `session_id`/`conversation_id`/`thread_id`/`rollout_id` for the resume id, including
nested under a `msg` key) rather than committing to one guessed shape. Treat this whole adapter
as a placeholder to correct once someone can run `codex --help` and a live `codex exec --json`
session to verify against.

Spawned with a full-auto/bypass-approval flag so it never blocks on an interactive prompt it has
no TTY to answer, since the spawned agent drives the session purely over its own shell access to
the already-running `emergentflow serve` HTTP API (agents/emergent-flow-collaborator.md).
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

from emergentflow.collab.agents.base import AdapterEvent, AgentAdapter, register_adapter

_TEXT_KEYS = ("message", "text", "content")
_THREAD_ID_KEYS = ("session_id", "conversation_id", "thread_id", "rollout_id")
_COMMAND_KEYS = ("command", "cmd")


def _find_text(payload: dict[str, Any]) -> str | None:
    msg = payload.get("msg")
    if isinstance(msg, dict):
        nested = _find_text(msg)
        if nested is not None:
            return nested
    for key in _TEXT_KEYS:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _find_thread_id(payload: dict[str, Any]) -> str | None:
    msg = payload.get("msg")
    if isinstance(msg, dict):
        nested = _find_thread_id(msg)
        if nested is not None:
            return nested
    for key in _THREAD_ID_KEYS:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _find_command(payload: dict[str, Any]) -> str | None:
    msg = payload.get("msg")
    if isinstance(msg, dict):
        nested = _find_command(msg)
        if nested is not None:
            return nested
    for key in _COMMAND_KEYS:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
        if isinstance(value, list) and value and all(isinstance(v, str) for v in value):
            return " ".join(value)
    return None


@register_adapter
class CodexAdapter(AgentAdapter):
    name: ClassVar[str] = "codex"
    cli_executable: ClassVar[str] = "codex"

    def build_command(self, *, prompt: str, resume_id: str | None) -> list[str]:
        if resume_id is not None:
            return [
                self.cli_executable,
                "exec",
                "resume",
                resume_id,
                prompt,
                "--json",
                "--dangerously-bypass-approvals-and-sandbox",
            ]
        return [
            self.cli_executable,
            "exec",
            prompt,
            "--json",
            "--dangerously-bypass-approvals-and-sandbox",
        ]

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

        thread_id = _find_thread_id(event)
        if thread_id is not None:
            return AdapterEvent(kind="thread_id", text=thread_id)

        command = _find_command(event)
        if command is not None:
            return AdapterEvent(kind="tool_call", text=f"running: {command}")

        text = _find_text(event)
        if text is not None:
            return AdapterEvent(kind="text", text=text)

        return None
