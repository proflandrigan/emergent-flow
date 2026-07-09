"""
emergentflow.collab.session
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Graph sessions — the shared, server-side collaboration document (Epic 14 Story 3,
ADR 0019). A GraphSession pairs a Graph with a monotonically increasing version
and a set of pending/resolved GraphMutation proposals. This is deliberately
boring, process-local, in-memory state (the "report-store precedent",
emergentflow/server/reports.py) -- no CRDT/OT merge, no persistence --
optimistic concurrency (a monotonic ``version`` + each write's expected/base
version) is sufficient for one human + advisory agents.

Collaboration state lives BESIDE the graph, never on it (epic invariant): this
module defines its own models, never touches emergentflow.ir.graph.Graph's
schema, and is never imported by emergentflow/__init__.py or
emergentflow/ir/__init__.py.

Pub/sub: every session-mutating method publishes a JSON-safe event dict to
every live subscriber queue for that session id, so the ``GET
/sessions/{id}/events`` SSE route (emergentflow/server/app.py) can stream
proposal-added/accepted/rejected and graph-replaced events to any watcher --
the same "producer thread pushes into a queue.SimpleQueue" shape the existing
``/execute/stream`` route already uses (``_bridge_to_queue``, app.py), except
here MULTIPLE HTTP requests (from different clients/threads) publish into the
SAME per-session subscriber queues, instead of one generator being drained.
"""

from __future__ import annotations

import queue
import threading
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from emergentflow.codegen.validation import Diagnostics
from emergentflow.ir.common import new_id
from emergentflow.ir.graph import Graph
from emergentflow.ir.mutation import GraphMutation, apply_mutation, propose_diagnostics


class SessionError(Exception):
    """Base class for all graph-session errors."""


class UnknownSessionError(SessionError):
    """Raised when a session id does not exist in the store."""


class UnknownProposalError(SessionError):
    """Raised when a proposal id does not exist on a session."""


class StaleVersionError(SessionError):
    """Raised when a write's expected/base version does not match the
    session's current version (an optimistic-concurrency conflict)."""


class ProposalAlreadyResolvedError(SessionError):
    """Raised when accept/reject targets a proposal that is no longer PENDING.

    A proposal's status transition is one-shot: once accepted or rejected, it
    cannot be re-resolved. Without this guard, an already-REJECTED proposal
    could later be accepted (nothing about rejecting bumps the session
    version, so the stale-version check alone would not catch it), silently
    applying a mutation a human already turned down; and an already-ACCEPTED
    proposal (whose mutation is already baked into the graph) could be
    flipped to REJECTED, leaving the session's proposal status contradicting
    its own graph.
    """


class ProposalStatus(str, Enum):
    """Lifecycle status of a stored GraphMutation proposal."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class StoredProposal(BaseModel):
    """A GraphMutation proposal as recorded on a session, with its verdict."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=new_id)
    mutation: GraphMutation
    diagnostics: Diagnostics
    status: ProposalStatus = ProposalStatus.PENDING


class GraphSession(BaseModel):
    """A server-side shared graph document: the graph, its version, and proposals.

    ``version`` is bumped by exactly 1 on every accepted change (a
    ``PUT .../graph`` replace or an accepted proposal) -- never on any other
    operation. Writers send the version they expect to be replacing
    (``PUT .../graph``'s body) or the version their mutation was computed
    against (``GraphMutation.base_version``); a mismatch is a typed
    ``StaleVersionError``, never silently applied.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=new_id)
    graph: Graph = Field(default_factory=Graph)
    version: int = 0
    proposals: dict[str, StoredProposal] = Field(default_factory=dict)


class SessionStore:
    """In-memory, thread-safe store of GraphSessions (the report-store precedent).

    One global lock guards every read-modify-write across every session --
    simple and correct; a per-session lock would be a premature optimization
    for a store that only ever serves one local human plus a few advisory
    agents.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, GraphSession] = {}
        self._lock = threading.Lock()
        self._subscribers: dict[str, list[queue.SimpleQueue[dict[str, Any]]]] = {}

    def create(self, graph: Graph | None = None) -> GraphSession:
        """Create a new session, optionally seeded with *graph* (else an empty Graph)."""
        session = GraphSession(graph=graph if graph is not None else Graph())
        with self._lock:
            self._sessions[session.id] = session
        return session

    def get(self, session_id: str) -> GraphSession:
        """Return the session for *session_id*.

        Raises
        ------
        UnknownSessionError
            If no session with that id exists.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise UnknownSessionError(f"no session with id {session_id!r}.")
            return session

    def delete(self, session_id: str) -> None:
        """Remove the session for *session_id*.

        Raises
        ------
        UnknownSessionError
            If no session with that id exists.
        """
        with self._lock:
            if session_id not in self._sessions:
                raise UnknownSessionError(f"no session with id {session_id!r}.")
            del self._sessions[session_id]
            self._subscribers.pop(session_id, None)

    def subscribe(self, session_id: str) -> queue.SimpleQueue[dict[str, Any]]:
        """Register a new subscriber queue for *session_id*'s event stream.

        The caller (the SSE route) reads events off the returned queue until it
        stops watching, then calls ``unsubscribe`` with the SAME queue object.

        Raises
        ------
        UnknownSessionError
            If no session with that id exists.
        """
        with self._lock:
            if session_id not in self._sessions:
                raise UnknownSessionError(f"no session with id {session_id!r}.")
            q: queue.SimpleQueue[dict[str, Any]] = queue.SimpleQueue()
            self._subscribers.setdefault(session_id, []).append(q)
            return q

    def unsubscribe(self, session_id: str, q: queue.SimpleQueue[dict[str, Any]]) -> None:
        """Remove a subscriber queue registered via ``subscribe``.

        A no-op if *q* is already gone (e.g. the session was deleted first) --
        the SSE route's cleanup path always calls this exactly once, but must
        not raise if the session vanished out from under it mid-stream.
        """
        with self._lock:
            subscribers = self._subscribers.get(session_id)
            if subscribers is not None and q in subscribers:
                subscribers.remove(q)

    def _publish(self, session_id: str, event: dict[str, Any]) -> None:
        """Push *event* to every live subscriber of *session_id*.

        Internal helper: every public mutator below calls this right before
        returning, still inside its own ``with self._lock`` block, so a
        subscriber can never observe an event for a state change it can't yet
        read back via ``get``.
        """
        for q in self._subscribers.get(session_id, []):
            q.put(event)

    def replace_graph(
        self, session_id: str, graph: Graph, *, expected_version: int
    ) -> GraphSession:
        """Replace *session_id*'s graph wholesale, bumping its version by 1.

        Raises
        ------
        UnknownSessionError
            If no session with that id exists.
        StaleVersionError
            If *expected_version* does not match the session's current version.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise UnknownSessionError(f"no session with id {session_id!r}.")
            if session.version != expected_version:
                raise StaleVersionError(
                    f"session {session_id!r}: expected version {expected_version}, "
                    f"but the session is at version {session.version}."
                )
            session.graph = graph
            session.version += 1
            self._publish(
                session_id,
                {"type": "graph_replaced", "session_id": session_id, "version": session.version},
            )
            return session

    def add_proposal(self, session_id: str, mutation: GraphMutation) -> StoredProposal:
        """Validate-on-propose and store *mutation* as a new pending StoredProposal.

        Raises
        ------
        UnknownSessionError
            If no session with that id exists.
        StaleVersionError
            If ``mutation.base_version`` does not match the session's current version.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise UnknownSessionError(f"no session with id {session_id!r}.")
            if mutation.base_version != session.version:
                raise StaleVersionError(
                    f"session {session_id!r}: proposal base_version "
                    f"{mutation.base_version} does not match the session's current "
                    f"version {session.version}."
                )
            diagnostics = propose_diagnostics(session.graph, mutation)
            proposal = StoredProposal(mutation=mutation, diagnostics=diagnostics)
            session.proposals[proposal.id] = proposal
            self._publish(
                session_id,
                {"type": "proposal_added", "session_id": session_id, "proposal_id": proposal.id},
            )
            return proposal

    def _get_proposal(self, session: GraphSession, proposal_id: str) -> StoredProposal:
        proposal = session.proposals.get(proposal_id)
        if proposal is None:
            raise UnknownProposalError(
                f"no proposal with id {proposal_id!r} on session {session.id!r}."
            )
        return proposal

    def accept_proposal(self, session_id: str, proposal_id: str) -> GraphSession:
        """Apply *proposal_id*'s mutation, bump the session's version, mark it accepted.

        Raises
        ------
        UnknownSessionError
            If no session with that id exists.
        UnknownProposalError
            If no proposal with that id exists on the session.
        ProposalAlreadyResolvedError
            If the proposal is not PENDING (already accepted or rejected).
        StaleVersionError
            If the session's graph has moved on since the proposal's
            ``base_version`` (another change landed first).
        MutationError
            (from ``emergentflow.ir.mutation``) if applying the mutation itself
            fails structurally -- not caught here, propagates to the caller.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise UnknownSessionError(f"no session with id {session_id!r}.")
            proposal = self._get_proposal(session, proposal_id)
            if proposal.status != ProposalStatus.PENDING:
                raise ProposalAlreadyResolvedError(
                    f"session {session_id!r}: proposal {proposal_id!r} is already "
                    f"{proposal.status.value} and cannot be re-resolved."
                )
            if proposal.mutation.base_version != session.version:
                raise StaleVersionError(
                    f"session {session_id!r}: proposal {proposal_id!r} was computed "
                    f"against version {proposal.mutation.base_version}, but the "
                    f"session is now at version {session.version}."
                )
            new_graph = apply_mutation(session.graph, proposal.mutation)
            session.graph = new_graph
            session.version += 1
            proposal.status = ProposalStatus.ACCEPTED
            self._publish(
                session_id,
                {
                    "type": "proposal_accepted",
                    "session_id": session_id,
                    "proposal_id": proposal_id,
                    "version": session.version,
                },
            )
            return session

    def reject_proposal(self, session_id: str, proposal_id: str) -> GraphSession:
        """Mark *proposal_id* rejected. Does not touch the session's graph/version.

        Raises
        ------
        UnknownSessionError
            If no session with that id exists.
        UnknownProposalError
            If no proposal with that id exists on the session.
        ProposalAlreadyResolvedError
            If the proposal is not PENDING (already accepted or rejected).
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise UnknownSessionError(f"no session with id {session_id!r}.")
            proposal = self._get_proposal(session, proposal_id)
            if proposal.status != ProposalStatus.PENDING:
                raise ProposalAlreadyResolvedError(
                    f"session {session_id!r}: proposal {proposal_id!r} is already "
                    f"{proposal.status.value} and cannot be re-resolved."
                )
            proposal.status = ProposalStatus.REJECTED
            self._publish(
                session_id,
                {"type": "proposal_rejected", "session_id": session_id, "proposal_id": proposal_id},
            )
            return session


# A process-wide default store, lazily created (the report-store precedent --
# emergentflow/server/reports.py's get_default_store -- double-checked locking
# so concurrent first-hit requests never build two different stores).
_default_store: SessionStore | None = None
_default_store_lock = threading.Lock()


def get_default_store() -> SessionStore:
    """Return the lazily-created process-wide default SessionStore."""
    global _default_store
    if _default_store is None:
        with _default_store_lock:
            if _default_store is None:
                _default_store = SessionStore()
    return _default_store
