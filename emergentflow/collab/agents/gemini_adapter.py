"""
emergentflow.collab.agents.gemini_adapter
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
AgentAdapter for the Gemini CLI (`gemini`). BEST-EFFORT AND UNVERIFIED: the Gemini CLI account
available during development is not currently eligible to run non-interactively (an
IneligibleTierError from Google's backend when probed), so unlike the Claude and opencode
adapters, this one's JSON event shape was NOT observed from a real `gemini -o stream-json` run.
It is written from `gemini --help`'s documented flags plus the well-known public Gemini API
response shape (`candidates[].content.parts[].text` / `.functionCall`). `parse_line` degrades
gracefully (returns None) for any line shape it doesn't recognize rather than raising, so an
unexpected real-world format silently drops narration/text for that line rather than crashing
the chat turn. Treat this adapter as a starting point to correct once verified against a working,
eligible Gemini CLI account.

Spawns the CLI in headless mode (`-p <prompt> -o stream-json`) with `--approval-mode auto_edit`
so it never blocks on an interactive approval prompt it has no TTY to answer, since the spawned
agent drives the session purely over its own shell access to the already-running `emergentflow
serve` HTTP API (agents/emergent-flow-collaborator.md). Because `-r/--resume` is documented as
accepting only `"latest"` or a numeric index, this adapter instead re-passes `--session-id` with
the same id on later turns as its best-effort continuation mechanism -- if the CLI never echoes
a session id back on stdout (this adapter cannot be sure it does, unverified), multi-turn
continuity for this backend may silently fall back to a fresh session each turn; a known,
documented v1 limitation.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

from emergentflow.collab.agents.base import AdapterEvent, AgentAdapter, register_adapter


def _find_text(payload: dict[str, Any]) -> str | None:
    text = payload.get("text")
    if isinstance(text, str) and text:
        return text
    response = payload.get("response")
    if isinstance(response, str) and response:
        return response
    content = payload.get("content")
    if isinstance(content, dict):
        parts = content.get("parts")
        if isinstance(parts, list):
            for part in parts:
                if isinstance(part, dict):
                    part_text = part.get("text")
                    if isinstance(part_text, str) and part_text:
                        return part_text
    candidates = payload.get("candidates")
    if isinstance(candidates, list):
        for candidate in candidates:
            if isinstance(candidate, dict):
                nested = _find_text({"content": candidate.get("content")})
                if nested is not None:
                    return nested
    return None


def _iter_parts(payload: dict[str, Any]) -> list[Any]:
    content = payload.get("content")
    if isinstance(content, dict):
        parts = content.get("parts")
        if isinstance(parts, list):
            return parts
    candidates = payload.get("candidates")
    if isinstance(candidates, list):
        for candidate in candidates:
            if isinstance(candidate, dict):
                cand_content = candidate.get("content")
                if isinstance(cand_content, dict):
                    parts = cand_content.get("parts")
                    if isinstance(parts, list):
                        return parts
    return []


def _find_function_call(payload: dict[str, Any]) -> str | None:
    for part in _iter_parts(payload):
        if not isinstance(part, dict):
            continue
        function_call = part.get("functionCall")
        if isinstance(function_call, dict):
            name = function_call.get("name")
            tool_name = name if isinstance(name, str) and name else "tool"
            args = function_call.get("args")
            command = args.get("command") if isinstance(args, dict) else None
            if isinstance(command, str) and command:
                return f"{tool_name}: {command}"
            return f"running {tool_name}"
    return None


@register_adapter
class GeminiAdapter(AgentAdapter):
    name: ClassVar[str] = "gemini"
    cli_executable: ClassVar[str] = "gemini"

    def build_command(self, *, prompt: str, resume_id: str | None) -> list[str]:
        argv = [
            self.cli_executable,
            "-p",
            prompt,
            "-o",
            "stream-json",
            "--approval-mode",
            "auto_edit",
        ]
        if resume_id is not None:
            argv += ["--session-id", resume_id]
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

        for key in ("sessionId", "session_id"):
            session_id = event.get(key)
            if isinstance(session_id, str) and session_id:
                return AdapterEvent(kind="thread_id", text=session_id)

        function_call_summary = _find_function_call(event)
        if function_call_summary is not None:
            return AdapterEvent(kind="tool_call", text=function_call_summary)

        text = _find_text(event)
        if text is not None:
            return AdapterEvent(kind="text", text=text)

        return None
