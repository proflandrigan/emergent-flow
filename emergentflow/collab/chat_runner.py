"""
emergentflow.collab.chat_runner
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Subprocess orchestration for the in-app agent chat feature: spawns a coding-agent CLI (via its
AgentAdapter, emergentflow/collab/agents/) in headless mode, streams its stdout through the
adapter's parse_line, and publishes narration/text/thread-id events through SessionStore as they
arrive -- the same "producer thread pushes into a queue" shape emergentflow/server/app.py's
/execute/stream route already uses, except the producer here is a spawned OS process rather than
an in-process generator.

The spawned CLI drives the session over its OWN shell/curl access to the already-running
`emergentflow serve` HTTP API (agents/emergent-flow-collaborator.md) -- this module builds that
protocol document plus the session's id/base URL/auth into the FIRST turn's prompt as a context
block, then sends just the human's new message on every later turn (relying on the CLI's own
--resume/--session continuation to remember the rest, per each AgentAdapter's build_command).
Reading agents/emergent-flow-collaborator.md from disk assumes a repo checkout / editable
install where agents/ is present; packaging that file into a wheel-only install is out of scope
here.

Text events accumulate across a turn and are only published as the turn's final agent_message
once the process exits -- narration (tool-call) events publish live, one per line, as they
arrive. A deliberate v1 simplification: no partial/streaming text display, only the final reply.
Another deliberate v1 simplification: stderr is only read AFTER stdout reaches EOF, not
concurrently -- a CLI that writes enough to stderr to fill the OS pipe buffer before exiting
could in theory deadlock; acceptable for now since these CLIs' stderr is expected to carry only
occasional error text, not high-volume output.

start_chat_turn spawns the subprocess in a background thread and returns immediately once the
turn is recorded on SessionStore -- callers (an HTTP route, a later task) do not block for the
turn to finish; watch a session's SSE event stream for narration/completion instead.

Never imported by emergentflow/__init__.py or emergentflow/ir/graph.py (works-without-agents
invariant, ADR 0019).
"""

from __future__ import annotations

import contextlib
import pathlib
import subprocess
import threading
from typing import IO

from emergentflow.collab.agents import AgentAdapter, get_adapter, list_available_adapter_names
from emergentflow.collab.chat import ChatTurn, ChatTurnAlreadyResolvedError
from emergentflow.collab.session import SessionStore, get_default_store

_PROTOCOL_DOC_PATH = (
    pathlib.Path(__file__).resolve().parents[2] / "agents" / "emergent-flow-collaborator.md"
)

_RUNNING_PROCESSES: dict[str, subprocess.Popen[str]] = {}
_PROCESS_LOCK = threading.Lock()


class UnknownBackendError(Exception):
    """Raised when *backend* isn't a registered AND available (CLI detected on PATH) adapter
    name."""


def _build_first_turn_prompt(
    *, session_id: str, base_url: str, auth_token: str | None, user_message: str
) -> str:
    protocol = _PROTOCOL_DOC_PATH.read_text(encoding="utf-8")
    auth_line = f"- Auth header: `Authorization: Bearer {auth_token}`\n" if auth_token else ""
    return (
        f"{protocol}\n\n"
        "---\n\n"
        "## Live chat session\n\n"
        "You are now in a live chat with the human. This chat is scoped to ONE session that "
        "already exists -- do not create or discover a different one:\n\n"
        f"- Base URL: {base_url}\n"
        f"- Session id: {session_id}\n"
        f"{auth_line}"
        "Reply conversationally in plain text. When you take an action (propose a mutation, "
        "run validate, etc.), do it via curl as described above, then tell the human what you "
        "did and why in your reply. Keep replies concise.\n\n"
        "The human says:\n\n"
        f"{user_message}"
    )


def _read_stream(
    stream: IO[str],
    adapter: AgentAdapter,
    session_id: str,
    turn: ChatTurn,
    store: SessionStore,
) -> list[str]:
    """Read *stream* line by line, publishing narration/thread-id events live and returning the
    ordered list of text chunks the adapter parsed (joined by the caller into the final
    agent_message)."""
    text_chunks: list[str] = []
    for raw_line in stream:
        event = adapter.parse_line(raw_line)
        if event is None:
            continue
        if event.kind == "thread_id":
            store.set_chat_thread_id(session_id, event.text)
        elif event.kind == "tool_call":
            with contextlib.suppress(ChatTurnAlreadyResolvedError):
                store.append_chat_narration(session_id, turn.id, event.text)
        elif event.kind == "text":
            text_chunks.append(event.text)
    return text_chunks


def _run_turn(
    store: SessionStore,
    session_id: str,
    backend: str,
    turn: ChatTurn,
    prompt: str,
    resume_id: str | None,
) -> None:
    adapter = get_adapter(backend)
    argv = adapter.build_command(prompt=prompt, resume_id=resume_id)
    try:
        proc = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
    except OSError as exc:
        with contextlib.suppress(ChatTurnAlreadyResolvedError):
            store.fail_chat_turn(session_id, turn.id, error=f"failed to start {backend!r}: {exc}")
        return

    with _PROCESS_LOCK:
        _RUNNING_PROCESSES[turn.id] = proc

    try:
        assert proc.stdout is not None
        text_chunks = _read_stream(proc.stdout, adapter, session_id, turn, store)
        stderr_output = proc.stderr.read() if proc.stderr is not None else ""
        exit_code = proc.wait()
    finally:
        with _PROCESS_LOCK:
            _RUNNING_PROCESSES.pop(turn.id, None)

    try:
        if exit_code != 0:
            error = stderr_output.strip() or f"{backend} exited with code {exit_code}"
            store.fail_chat_turn(session_id, turn.id, error=error)
        else:
            agent_message = "\n\n".join(text_chunks) if text_chunks else "(no reply)"
            store.complete_chat_turn(session_id, turn.id, agent_message)
    except ChatTurnAlreadyResolvedError:
        pass


def start_chat_turn(
    session_id: str,
    backend: str,
    user_message: str,
    *,
    base_url: str,
    auth_token: str | None = None,
) -> ChatTurn:
    """Start a chat turn on *session_id* with *backend*, spawning its CLI in a background
    thread and returning immediately once the turn is recorded -- the caller does not block for
    the turn to finish; watch a session's SSE event stream for narration/completion.

    Raises
    ------
    UnknownBackendError
        If *backend* isn't a registered AND available (CLI detected on PATH) adapter name.
    UnknownSessionError, ChatAlreadyActiveError
        Propagated from SessionStore.start_chat_turn.
    """
    if backend not in list_available_adapter_names():
        raise UnknownBackendError(f"backend {backend!r} is not registered or not available.")

    store = get_default_store()
    turn = store.start_chat_turn(session_id, backend, user_message)

    session = store.get(session_id)
    resume_id = session.collab.chat.backend_thread_id
    if resume_id is None:
        prompt = _build_first_turn_prompt(
            session_id=session_id,
            base_url=base_url,
            auth_token=auth_token,
            user_message=user_message,
        )
    else:
        prompt = user_message

    thread = threading.Thread(
        target=_run_turn,
        args=(store, session_id, backend, turn, prompt, resume_id),
        daemon=True,
    )
    thread.start()
    return turn


def stop_chat_turn(session_id: str, turn_id: str) -> None:
    """Interrupt a RUNNING chat turn: mark it INTERRUPTED first (so the background reader
    thread's own resolve attempt sees it already resolved and no-ops), then terminate its
    subprocess (escalating to kill if it doesn't exit within 5 seconds).

    Raises
    ------
    UnknownSessionError, UnknownChatTurnError, ChatTurnAlreadyResolvedError
        Propagated from SessionStore.interrupt_chat_turn.
    """
    store = get_default_store()
    store.interrupt_chat_turn(session_id, turn_id)
    with _PROCESS_LOCK:
        proc = _RUNNING_PROCESSES.get(turn_id)
    if proc is not None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
