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
_AGENTS_DIR = pathlib.Path(__file__).resolve().parents[2] / "agents"

# Slash commands recognized as chat messages, mapped to their persona markdown filename under
# agents/ -- the single source of truth for which commands are recognized. Slash-command slugs
# use hyphens (as typed by the human); persona slugs (ChatState.active_persona) use underscores,
# matching emergentflow.collab.persona_defs -- _FILENAME_TO_SLUG/_SLUG_TO_FILENAME below bridge
# the two.
_PERSONA_SLASH_COMMANDS: dict[str, str] = {
    "/data-scientist": "data-scientist.md",
    "/researcher": "researcher.md",
    "/ml-engineer": "ml-engineer.md",
}
_FILENAME_TO_SLUG: dict[str, str] = {
    filename: command.lstrip("/").replace("-", "_")
    for command, filename in _PERSONA_SLASH_COMMANDS.items()
}
_SLUG_TO_FILENAME: dict[str, str] = {slug: filename for filename, slug in _FILENAME_TO_SLUG.items()}

_RUNNING_PROCESSES: dict[str, subprocess.Popen[str]] = {}
# Registered synchronously in start_chat_turn, BEFORE the background thread is even started --
# closes the race where stop_chat_turn is called before _run_turn has gotten far enough to
# register its Popen in _RUNNING_PROCESSES (fast Stop click, or a slow-to-cold-start CLI). Both
# _run_turn and stop_chat_turn only ever touch this (and _RUNNING_PROCESSES) while holding
# _PROCESS_LOCK, so whichever of "spawn" and "stop" happens second always observes the other's
# effect: a stop that lands first is seen by _run_turn right after it registers the process; a
# stop that lands after registration finds the process directly. Popped once the turn resolves.
_STOP_REQUESTED: dict[str, threading.Event] = {}
_PROCESS_LOCK = threading.Lock()


class UnknownBackendError(Exception):
    """Raised when *backend* isn't a registered AND available (CLI detected on PATH) adapter
    name."""


def _detect_persona_command(message: str) -> str | None:
    """Return the persona markdown filename if *message* starts with a known persona slash
    command (``_PERSONA_SLASH_COMMANDS``), else None.

    Only the first word is checked case-insensitively, so ``/data-scientist build me a
    pipeline`` still matches.
    """
    stripped = message.strip()
    if not stripped:
        return None
    first_word = stripped.split()[0].lower()
    return _PERSONA_SLASH_COMMANDS.get(first_word)


def _read_persona_markdown(filename: str) -> str:
    """Read an agent persona markdown file (e.g. ``"data-scientist.md"``) from agents/."""
    return (_AGENTS_DIR / filename).read_text(encoding="utf-8")


def _persona_filename_for_slug(slug: str) -> str | None:
    """Return the persona markdown filename for an already-active persona *slug*, or None if
    *slug* isn't one of the recognized personas."""
    return _SLUG_TO_FILENAME.get(slug)


def _build_first_turn_prompt(
    *,
    session_id: str,
    base_url: str,
    auth_token: str | None,
    user_message: str,
    persona_filename: str | None = None,
) -> str:
    protocol = _PROTOCOL_DOC_PATH.read_text(encoding="utf-8")
    auth_line = f"- Auth header: `Authorization: Bearer {auth_token}`\n" if auth_token else ""

    persona_block = ""
    if persona_filename is not None:
        persona_md = _read_persona_markdown(persona_filename)
        persona_block = (
            "\n\n---\n\n"
            "## Your persona\n\n"
            "You have been activated with a specific persona. Adopt the following identity "
            "and follow its behavioral rules for the duration of this chat session:\n\n"
            f"{persona_md}\n\n"
        )

    return (
        f"{protocol}\n\n"
        "---\n\n"
        "## Live chat session\n\n"
        "You are now in a live chat with the human. This chat is scoped to ONE session that "
        "already exists -- do not create or discover a different one:\n\n"
        f"- Base URL: {base_url}\n"
        f"- Session id: {session_id}\n"
        f"{auth_line}"
        f"{persona_block}"
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
    stop_event: threading.Event,
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
        with _PROCESS_LOCK:
            _STOP_REQUESTED.pop(turn.id, None)
        with contextlib.suppress(ChatTurnAlreadyResolvedError):
            store.fail_chat_turn(session_id, turn.id, error=f"failed to start {backend!r}: {exc}")
        return

    with _PROCESS_LOCK:
        _RUNNING_PROCESSES[turn.id] = proc
        stop_already_requested = stop_event.is_set()
    if stop_already_requested:
        # stop_chat_turn ran before this point saw the process registered -- it already marked
        # the turn INTERRUPTED, so just make sure the process it couldn't find gets killed too.
        proc.terminate()

    try:
        assert proc.stdout is not None
        text_chunks = _read_stream(proc.stdout, adapter, session_id, turn, store)
        stderr_output = proc.stderr.read() if proc.stderr is not None else ""
        exit_code = proc.wait()
    finally:
        with _PROCESS_LOCK:
            _RUNNING_PROCESSES.pop(turn.id, None)
            _STOP_REQUESTED.pop(turn.id, None)

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

    # A persona slash command (e.g. "/data-scientist") in the user's message activates (or
    # switches) the session's persona -- store it on ChatState so the UI can show it and later
    # turns keep injecting/continuing it.
    persona_filename = _detect_persona_command(user_message)
    if persona_filename is not None:
        store.set_chat_persona(session_id, _FILENAME_TO_SLUG[persona_filename])
        session = store.get(session_id)  # re-read so active_persona reflects the update below
    active_persona_slug = session.collab.chat.active_persona

    if resume_id is None:
        # First turn: build the full protocol+session prompt, with the persona markdown (if
        # any is active yet) folded in as an extra context block.
        prompt = _build_first_turn_prompt(
            session_id=session_id,
            base_url=base_url,
            auth_token=auth_token,
            user_message=user_message,
            persona_filename=(
                _persona_filename_for_slug(active_persona_slug) if active_persona_slug else None
            ),
        )
    elif persona_filename is not None:
        # A resumed turn that just switched (or newly activated) persona: inject the persona
        # markdown into this turn's prompt so the already-running CLI conversation picks it up.
        persona_md = _read_persona_markdown(persona_filename)
        prompt = (
            "## Persona switch\n\n"
            "The human has activated a new persona. From now on, adopt the following identity "
            "and follow its behavioral rules:\n\n"
            f"{persona_md}\n\n"
            "---\n\n"
            "The human says:\n\n"
            f"{user_message}"
        )
    else:
        # A resumed turn continuing an already-active persona (or no persona at all) -- the CLI
        # already has whatever persona context it needs from a previous turn's prompt.
        prompt = user_message

    # Registered here, synchronously, BEFORE the background thread starts -- so a stop_chat_turn
    # call racing the thread's own startup (fast Stop click, or a slow-to-cold-start CLI) always
    # has a _STOP_REQUESTED entry to set, even if _run_turn hasn't reached Popen() yet.
    stop_event = threading.Event()
    with _PROCESS_LOCK:
        _STOP_REQUESTED[turn.id] = stop_event

    thread = threading.Thread(
        target=_run_turn,
        args=(store, session_id, backend, turn, prompt, resume_id, stop_event),
        daemon=True,
    )
    thread.start()
    return turn


def stop_chat_turn(session_id: str, turn_id: str) -> None:
    """Interrupt a RUNNING chat turn: mark it INTERRUPTED first (so the background reader
    thread's own resolve attempt sees it already resolved and no-ops), then terminate its
    subprocess (escalating to kill if it doesn't exit within 5 seconds) if one has been spawned
    yet -- if not, setting the stop event makes _run_turn terminate it the moment it is.

    Raises
    ------
    UnknownSessionError, UnknownChatTurnError, ChatTurnAlreadyResolvedError
        Propagated from SessionStore.interrupt_chat_turn.
    """
    store = get_default_store()
    store.interrupt_chat_turn(session_id, turn_id)
    with _PROCESS_LOCK:
        stop_event = _STOP_REQUESTED.get(turn_id)
        if stop_event is not None:
            stop_event.set()
        proc = _RUNNING_PROCESSES.get(turn_id)
    if proc is not None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
