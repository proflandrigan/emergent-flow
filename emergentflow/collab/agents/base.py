"""
emergentflow.collab.agents.base
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The AgentAdapter contract (in-app agent chat): one coding-agent CLI's spawn/parse translation
for the chat feature. A concrete adapter knows how to build the argv for that CLI's
headless/print mode and how to turn each line of that CLI's own JSON event stream into a
normalized AdapterEvent -- it does NOT run the subprocess itself; emergentflow/collab/
chat_runner.py (a later task) owns spawning, threading, and publishing events through
SessionStore. Adapters are pure translators: argv in, AdapterEvent out.

Adapters self-register via @register_adapter (mirrors emergentflow.nodes.contract's @register
pattern) -- importing emergentflow.collab.agents fires every adapter module's registration.

Never imported by emergentflow/__init__.py or emergentflow/ir/graph.py (works-without-agents
invariant, ADR 0019).
"""

from __future__ import annotations

import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar, Literal


@dataclass(frozen=True)
class AdapterEvent:
    """One normalized event parsed from a spawned agent CLI's JSON stream line.

    kind == "text": a chunk of the agent's plain-text reply (`text` set).
    kind == "tool_call": a compact, already-formatted narration line describing a tool the CLI
        ran (`text` set, e.g. "Bash: curl -X POST ...").
    kind == "thread_id": the CLI's own resume/session id for this conversation (`text` set to
        that id) -- captured once per turn and stored via SessionStore.set_chat_thread_id.
    """

    kind: Literal["text", "tool_call", "thread_id"]
    text: str


class AgentAdapter(ABC):
    """One coding-agent CLI's spawn/parse contract for the in-app chat feature."""

    name: ClassVar[str]
    cli_executable: ClassVar[str]

    @classmethod
    def detect(cls) -> bool:
        """Return True if this adapter's CLI is on PATH."""
        return shutil.which(cls.cli_executable) is not None

    @abstractmethod
    def build_command(self, *, prompt: str, resume_id: str | None) -> list[str]:
        """Return the argv to spawn this CLI in headless/print mode.

        *prompt* is the full text to send this turn, already assembled by the caller (a context
        block on the first turn, just the user's message on later turns since *resume_id*
        carries the backend's own conversation state). *resume_id* is this session's stored
        ``backend_thread_id`` (None on the first turn).
        """

    @abstractmethod
    def parse_line(self, raw_line: str) -> AdapterEvent | None:
        """Parse one line of this CLI's stdout (in its own JSON streaming format) into a
        normalized AdapterEvent, or None if the line carries nothing worth surfacing (e.g. a
        blank line, malformed JSON, or an event kind this adapter doesn't map to
        text/tool_call/thread_id)."""


_ADAPTER_REGISTRY: dict[str, type[AgentAdapter]] = {}


def register_adapter(cls: type[AgentAdapter]) -> type[AgentAdapter]:
    """Class decorator: register *cls* under its ``name`` so get_adapter/list_adapter_names can
    find it. Mirrors emergentflow.nodes.contract's @register self-registration pattern --
    importing emergentflow.collab.agents fires every adapter module's registration."""
    _ADAPTER_REGISTRY[cls.name] = cls
    return cls


def get_adapter(name: str) -> AgentAdapter:
    """Return a new instance of the registered adapter for *name*.

    Raises KeyError if no adapter is registered under that name.
    """
    return _ADAPTER_REGISTRY[name]()


def list_adapter_names() -> list[str]:
    """Return every registered adapter's name, sorted, regardless of CLI availability."""
    return sorted(_ADAPTER_REGISTRY)


def list_available_adapter_names() -> list[str]:
    """Return every registered adapter's name whose CLI is detected (`detect()` True) on this
    machine, sorted -- what the "Start chat" backend picker shows."""
    return sorted(name for name, cls in _ADAPTER_REGISTRY.items() if cls.detect())
