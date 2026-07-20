"""
emergentflow.collab.chat
~~~~~~~~~~~~~~~~~~~~~~~~~
Agent chat turns: a ChatTurn records one request/response exchange between the human and a
spawned coding-agent CLI (Claude Code, Codex, opencode, Gemini CLI) driving this session over
its own shell/curl access to the HTTP API (agents/emergent-flow-collaborator.md) -- this module
adds no new graph-mutation path, only the chat transcript and turn lifecycle around it. Lives on
CollaborationState.chat, BESIDE the graph, never on it. Never imported by
emergentflow/__init__.py or emergentflow/ir/graph.py.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from emergentflow.ir.common import new_id


class ChatError(Exception):
    """Base class for all chat errors."""


class UnknownChatTurnError(ChatError):
    """Raised when a chat turn id does not exist on a session."""


class ChatTurnAlreadyResolvedError(ChatError):
    """Raised when complete/fail/interrupt targets a turn that is no longer RUNNING.

    Mirrors GateAlreadyResolvedError's one-shot transition discipline
    (emergentflow/collab/gates.py): a turn's status transition is one-shot -- once completed,
    failed, or interrupted, it cannot be re-resolved.
    """


class ChatAlreadyActiveError(ChatError):
    """Raised when starting a chat turn while another turn on the same session is still
    RUNNING, or starting a new backend while a different backend is already active on the
    session (one active chat at a time, per product decision)."""


class ChatTurnStatus(str, Enum):
    """Lifecycle status of one ChatTurn."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class ChatTurn(BaseModel):
    """One request/response exchange in a session's agent chat.

    ``narration`` accumulates compact tool-call log lines as the spawned CLI works.
    ``agent_message`` is filled in once the turn COMPLETES; it stays None while RUNNING and on
    FAILED/INTERRUPTED turns.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=new_id)
    backend: str
    user_message: str
    narration: list[str] = Field(default_factory=list)
    agent_message: str | None = None
    status: ChatTurnStatus = ChatTurnStatus.RUNNING
    error: str | None = None


class ChatState(BaseModel):
    """Session-scoped agent chat state: which backend is active, that backend's own
    resume/thread id (so the next turn continues the same conversation instead of starting
    fresh), and the ordered transcript of turns.

    Lives on ``CollaborationState.chat``. ``backend`` is None when no chat is active -- "one
    active chat at a time" (product decision) is enforced at the SessionStore level (a later
    task), not on this model itself -- the model stays a plain data container, same division of
    labor as ReviewThread/Gate.

    ``active_persona`` records which persona slug (e.g. ``"data_scientist"``) is currently
    active in the chat, set when the human types a persona slash command (e.g.
    ``/data-scientist``) as a chat message. None means no persona is active -- plain chat.
    """

    model_config = ConfigDict(extra="forbid")

    backend: str | None = None
    backend_thread_id: str | None = None
    turns: list[ChatTurn] = Field(default_factory=list)
    active_persona: str | None = None
