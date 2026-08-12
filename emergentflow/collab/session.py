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
from emergentflow.collab.chat import (
    ChatAlreadyActiveError,
    ChatTurn,
    ChatTurnAlreadyResolvedError,
    ChatTurnStatus,
    UnknownChatTurnError,
)
from emergentflow.collab.checkpoints import Checkpoint, CheckpointKind
from emergentflow.collab.gates import (
    Decision,
    Gate,
    GateAlreadyResolvedError,
    GateStatus,
    UnknownGateError,
)
from emergentflow.collab.review import (
    Attempt,
    CollaborationState,
    ReviewComment,
    ReviewThread,
    validate_anchors,
)
from emergentflow.ir.common import new_id
from emergentflow.ir.graph import Graph
from emergentflow.ir.mutation import (
    GraphMutation,
    apply_mutation,
    invert_mutation,
    propose_diagnostics,
)


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


class OpenGatesError(SessionError):
    """Raised when a session-scoped compile/execute is attempted while any gate is OPEN.

    Carries the list of open gates so the route handler's 409 response names them (epic
    text: "409 with the open-gate list") -- the message itself lists each open gate's id,
    phase, and description, following this codebase's convention of a single informative
    string in the {"error": ...} body (the same shape stale_version/proposal_already_resolved
    already use) rather than inventing a second, richer error-body shape for just this case.
    """

    def __init__(self, session_id: str, open_gates: list[Gate]) -> None:
        self.open_gates = open_gates
        gate_list = "; ".join(f"{g.id!r} ({g.phase}, {g.kind.value})" for g in open_gates)
        super().__init__(
            f"session {session_id!r} has {len(open_gates)} open gate(s) blocking "
            f"compile/execute: {gate_list}"
        )


class UnknownReviewError(SessionError):
    """Raised when a review thread id does not exist on a session."""


class UnknownCheckpointError(SessionError):
    """Raised when a checkpoint id does not exist on a session."""


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
    collab: CollaborationState = Field(default_factory=CollaborationState)


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

    def list(self) -> list[GraphSession]:
        """Return every session currently held, ordered by id for a deterministic listing.

        Used by ``GET /sessions`` (Epic 14 Story 5) so an agent can discover an active session
        without the id being copy-pasted out-of-band.
        """
        with self._lock:
            return sorted(self._sessions.values(), key=lambda s: s.id)

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

    def apply_direct_mutation(
        self,
        session_id: str,
        mutation: GraphMutation,
        *,
        author: str = "agent",
        description: str = "",
    ) -> tuple[GraphSession, Checkpoint]:
        """Validate, apply, and checkpoint a mutation directly.

        Raises the same errors as add_proposal (UnknownSessionError,
        StaleVersionError) plus MutationError if the mutation cannot be applied.
        Bumps the session version by 1, stores a Checkpoint of kind EDIT, and
        publishes a ``graph_changed`` event.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise UnknownSessionError(f"no session with id {session_id!r}.")
            if mutation.base_version != session.version:
                raise StaleVersionError(
                    f"session {session_id!r}: mutation base_version "
                    f"{mutation.base_version} does not match the session's current "
                    f"version {session.version}."
                )
            previous_graph = session.graph
            previous_version = session.version
            new_graph = apply_mutation(session.graph, mutation)
            session.graph = new_graph
            session.version += 1
            checkpoint = Checkpoint(
                kind=CheckpointKind.EDIT,
                author=author,
                description=description or mutation.description,
                base_version=previous_version,
                mutation=mutation,
                previous_graph=previous_graph,
                resulting_version=session.version,
            )
            session.collab.checkpoints[checkpoint.id] = checkpoint
            self._publish(
                session_id,
                {
                    "type": "graph_changed",
                    "session_id": session_id,
                    "version": session.version,
                    "checkpoint_id": checkpoint.id,
                    "author": checkpoint.author,
                    "description": checkpoint.description,
                },
            )
            return session, checkpoint

    def revert_checkpoint(self, session_id: str, checkpoint_id: str) -> GraphSession:
        """Restore the graph snapshot stored in *checkpoint_id*.

        Bumps the session version by 1, creates a new REVERT checkpoint, and
        publishes a ``graph_reverted`` event.

        Raises
        ------
        UnknownSessionError
            If no session with that id exists.
        UnknownCheckpointError
            If no checkpoint with that id exists on the session.
        MutationError
            (from ``emergentflow.ir.mutation``) if the checkpoint's forward
            mutation is not invertible -- not caught here, propagates to the
            caller.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise UnknownSessionError(f"no session with id {session_id!r}.")
            checkpoint = session.collab.checkpoints.get(checkpoint_id)
            if checkpoint is None:
                raise UnknownCheckpointError(
                    f"session {session_id!r} has no checkpoint {checkpoint_id!r}."
                )
            previous_graph = session.graph
            previous_version = session.version
            session.graph = checkpoint.previous_graph.model_copy(deep=True)
            session.version += 1
            inverse_mutation = invert_mutation(previous_graph, checkpoint.mutation)
            revert_checkpoint = Checkpoint(
                kind=CheckpointKind.REVERT,
                author=checkpoint.author,
                description=f"Revert: {checkpoint.description}",
                base_version=previous_version,
                mutation=inverse_mutation,
                previous_graph=previous_graph,
                resulting_version=session.version,
            )
            session.collab.checkpoints[revert_checkpoint.id] = revert_checkpoint
            self._publish(
                session_id,
                {
                    "type": "graph_reverted",
                    "session_id": session_id,
                    "version": session.version,
                    "checkpoint_id": revert_checkpoint.id,
                    "reverted_checkpoint_id": checkpoint_id,
                    "author": revert_checkpoint.author,
                    "description": revert_checkpoint.description,
                },
            )
            return session

    def add_review(self, session_id: str, thread: ReviewThread) -> ReviewThread:
        """Validate *thread*'s findings anchor against the session's graph, store it, and
        publish a ``review_added`` event.

        Raises
        ------
        UnknownSessionError
            If no session with that id exists.
        AnchorError
            If any finding in *thread* anchors to a node/edge/port id absent from the
            session's current graph.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise UnknownSessionError(f"no session with id {session_id!r}.")
            validate_anchors(session.graph, thread.findings)
            session.collab.reviews[thread.id] = thread
            self._publish(
                session_id,
                {"type": "review_added", "session_id": session_id, "review_id": thread.id},
            )
            return thread

    def record_attempt(self, session_id: str, attempt: Attempt) -> Attempt:
        """Record *attempt* in the session's experiment ledger and publish an
        ``attempt_recorded`` event.

        The ledger (``collab.attempts``) is the closed-loop record: an attempt
        pairs a mutation with a run, the metric that measured it, and its verdict.
        Callers build an ``Attempt`` with a ``mutation_id`` and the produced
        ``run_id`` once a run completes.

        Raises
        ------
        UnknownSessionError
            If no session with that id exists.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise UnknownSessionError(f"no session with id {session_id!r}.")
            session.collab.attempts[attempt.id] = attempt
            self._publish(
                session_id,
                {"type": "attempt_recorded", "session_id": session_id, "attempt_id": attempt.id},
            )
            return attempt

    def add_review_comment(
        self, session_id: str, review_id: str, comment: ReviewComment
    ) -> ReviewThread:
        """Append *comment* to the review thread *review_id* and publish a
        ``review_comment_added`` event.

        Raises
        ------
        UnknownSessionError
            If no session with that id exists.
        UnknownReviewError
            If no review thread with that id exists on the session.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise UnknownSessionError(f"no session with id {session_id!r}.")
            thread = session.collab.reviews.get(review_id)
            if thread is None:
                raise UnknownReviewError(
                    f"session {session_id!r} has no review thread {review_id!r}."
                )
            thread.comments.append(comment)
            self._publish(
                session_id,
                {
                    "type": "review_comment_added",
                    "session_id": session_id,
                    "review_id": review_id,
                    "comment_id": comment.id,
                },
            )
            return thread

    def open_gate(self, session_id: str, gate: Gate) -> Gate:
        """Store *gate* (status forced to OPEN regardless of what the caller passed --
        opening a gate always starts it OPEN) and publish a ``gate_opened`` event.

        Raises
        ------
        UnknownSessionError
            If no session with that id exists.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise UnknownSessionError(f"no session with id {session_id!r}.")
            gate.status = GateStatus.OPEN
            session.collab.gates[gate.id] = gate
            self._publish(
                session_id,
                {"type": "gate_opened", "session_id": session_id, "gate_id": gate.id},
            )
            return gate

    def _get_gate(self, session: GraphSession, gate_id: str) -> Gate:
        gate = session.collab.gates.get(gate_id)
        if gate is None:
            raise UnknownGateError(f"no gate with id {gate_id!r} on session {session.id!r}.")
        return gate

    def _resolve_gate(
        self, session_id: str, gate_id: str, new_status: GateStatus, event_type: str
    ) -> Gate:
        """Shared close/skip transition: one-shot, OPEN -> new_status only."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise UnknownSessionError(f"no session with id {session_id!r}.")
            gate = self._get_gate(session, gate_id)
            if gate.status != GateStatus.OPEN:
                raise GateAlreadyResolvedError(
                    f"session {session_id!r}: gate {gate_id!r} is already "
                    f"{gate.status.value} and cannot be re-resolved."
                )
            gate.status = new_status
            self._publish(
                session_id,
                {"type": event_type, "session_id": session_id, "gate_id": gate_id},
            )
            return gate

    def close_gate(self, session_id: str, gate_id: str) -> Gate:
        """Close an OPEN gate. Raises UnknownSessionError, UnknownGateError,
        GateAlreadyResolvedError."""
        return self._resolve_gate(session_id, gate_id, GateStatus.CLOSED, "gate_closed")

    def skip_gate(self, session_id: str, gate_id: str) -> Gate:
        """Skip an OPEN gate. Raises UnknownSessionError, UnknownGateError,
        GateAlreadyResolvedError."""
        return self._resolve_gate(session_id, gate_id, GateStatus.SKIPPED, "gate_skipped")

    def assert_no_open_gates(self, session_id: str) -> None:
        """Raise OpenGatesError if *session_id* has any gate with status OPEN.

        Raises
        ------
        UnknownSessionError
            If no session with that id exists.
        OpenGatesError
            If one or more gates are OPEN.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise UnknownSessionError(f"no session with id {session_id!r}.")
            open_gates = [g for g in session.collab.gates.values() if g.status == GateStatus.OPEN]
            if open_gates:
                raise OpenGatesError(session_id, open_gates)

    def add_decision(self, session_id: str, gate_id: str, decision: Decision) -> Gate:
        """Append *decision* to gate *gate_id*'s timeline and publish a
        ``decision_added`` event. Appending a decision is allowed regardless of the
        gate's status (a decision is a historical record; it doesn't reopen a
        closed gate).

        Raises
        ------
        UnknownSessionError
            If no session with that id exists.
        UnknownGateError
            If no gate with that id exists on the session.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise UnknownSessionError(f"no session with id {session_id!r}.")
            gate = self._get_gate(session, gate_id)
            gate.decisions.append(decision)
            self._publish(
                session_id,
                {
                    "type": "decision_added",
                    "session_id": session_id,
                    "gate_id": gate_id,
                    "decision_id": decision.id,
                },
            )
            return gate

    def _get_chat_turn(self, session: GraphSession, turn_id: str) -> ChatTurn:
        for turn in session.collab.chat.turns:
            if turn.id == turn_id:
                return turn
        raise UnknownChatTurnError(f"no chat turn with id {turn_id!r} on session {session.id!r}.")

    def start_chat_turn(self, session_id: str, backend: str, user_message: str) -> ChatTurn:
        """Start a new chat turn on *session_id* with a spawned *backend* CLI.

        If no chat is active on the session, *backend* becomes the session's active chat
        backend. Raises ChatAlreadyActiveError if a DIFFERENT backend is already active, or if
        the active backend's most recent turn is still RUNNING (one active chat, one turn at a
        time, per product decision).

        Raises
        ------
        UnknownSessionError
            If no session with that id exists.
        ChatAlreadyActiveError
            If a different backend is already active, or the current turn hasn't resolved yet.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise UnknownSessionError(f"no session with id {session_id!r}.")
            chat = session.collab.chat
            if chat.backend is not None and chat.backend != backend:
                raise ChatAlreadyActiveError(
                    f"session {session_id!r}: chat backend {chat.backend!r} is already active; "
                    f"end it before starting {backend!r}."
                )
            if chat.turns and chat.turns[-1].status == ChatTurnStatus.RUNNING:
                raise ChatAlreadyActiveError(
                    f"session {session_id!r}: turn {chat.turns[-1].id!r} is still running."
                )
            if chat.backend is None:
                chat.backend = backend
            turn = ChatTurn(backend=backend, user_message=user_message)
            chat.turns.append(turn)
            self._publish(
                session_id,
                {"type": "chat_turn_started", "session_id": session_id, "turn_id": turn.id},
            )
            return turn

    def append_chat_narration(self, session_id: str, turn_id: str, text: str) -> ChatTurn:
        """Append one narration line (e.g. "proposing mutation: ...") to a RUNNING chat turn.

        Raises
        ------
        UnknownSessionError
            If no session with that id exists.
        UnknownChatTurnError
            If no turn with that id exists on the session.
        ChatTurnAlreadyResolvedError
            If the turn is not RUNNING.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise UnknownSessionError(f"no session with id {session_id!r}.")
            turn = self._get_chat_turn(session, turn_id)
            if turn.status != ChatTurnStatus.RUNNING:
                raise ChatTurnAlreadyResolvedError(
                    f"session {session_id!r}: turn {turn_id!r} is already "
                    f"{turn.status.value} and cannot receive more narration."
                )
            turn.narration.append(text)
            self._publish(
                session_id,
                {"type": "chat_narration_added", "session_id": session_id, "turn_id": turn_id},
            )
            return turn

    def _resolve_chat_turn(
        self,
        session_id: str,
        turn_id: str,
        new_status: ChatTurnStatus,
        event_type: str,
        *,
        agent_message: str | None = None,
        error: str | None = None,
    ) -> ChatTurn:
        """Shared complete/fail/interrupt transition: one-shot, RUNNING -> new_status only."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise UnknownSessionError(f"no session with id {session_id!r}.")
            turn = self._get_chat_turn(session, turn_id)
            if turn.status != ChatTurnStatus.RUNNING:
                raise ChatTurnAlreadyResolvedError(
                    f"session {session_id!r}: turn {turn_id!r} is already "
                    f"{turn.status.value} and cannot be re-resolved."
                )
            turn.status = new_status
            if agent_message is not None:
                turn.agent_message = agent_message
            if error is not None:
                turn.error = error
            self._publish(
                session_id,
                {"type": event_type, "session_id": session_id, "turn_id": turn_id},
            )
            return turn

    def complete_chat_turn(self, session_id: str, turn_id: str, agent_message: str) -> ChatTurn:
        """Mark a RUNNING chat turn COMPLETED with the agent's final reply text.

        Raises UnknownSessionError, UnknownChatTurnError, ChatTurnAlreadyResolvedError."""
        return self._resolve_chat_turn(
            session_id,
            turn_id,
            ChatTurnStatus.COMPLETED,
            "chat_turn_completed",
            agent_message=agent_message,
        )

    def fail_chat_turn(self, session_id: str, turn_id: str, error: str) -> ChatTurn:
        """Mark a RUNNING chat turn FAILED with an error message.

        Raises UnknownSessionError, UnknownChatTurnError, ChatTurnAlreadyResolvedError."""
        return self._resolve_chat_turn(
            session_id, turn_id, ChatTurnStatus.FAILED, "chat_turn_failed", error=error
        )

    def interrupt_chat_turn(self, session_id: str, turn_id: str) -> ChatTurn:
        """Mark a RUNNING chat turn INTERRUPTED (the user hit Stop).

        Raises UnknownSessionError, UnknownChatTurnError, ChatTurnAlreadyResolvedError."""
        return self._resolve_chat_turn(
            session_id, turn_id, ChatTurnStatus.INTERRUPTED, "chat_turn_interrupted"
        )

    def set_chat_thread_id(self, session_id: str, thread_id: str) -> None:
        """Record the spawned CLI's own resume/thread id on the session's ChatState, so the
        next turn continues the same backend conversation instead of starting fresh. Does not
        publish an event -- the next narration/turn event on the same turn already triggers a
        refresh that picks this up.

        Raises
        ------
        UnknownSessionError
            If no session with that id exists.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise UnknownSessionError(f"no session with id {session_id!r}.")
            session.collab.chat.backend_thread_id = thread_id

    def set_chat_persona(self, session_id: str, persona_slug: str | None) -> None:
        """Set or clear the active persona on the session's chat state, and publish a
        ``persona_changed`` event.

        Raises
        ------
        UnknownSessionError
            If no session with that id exists.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise UnknownSessionError(f"no session with id {session_id!r}.")
            session.collab.chat.active_persona = persona_slug
            self._publish(
                session_id,
                {"type": "persona_changed", "session_id": session_id, "persona": persona_slug},
            )

    def end_chat(self, session_id: str) -> GraphSession:
        """Clear the session's active chat backend, thread id, and active persona so a new
        backend can be started. Turn history is kept. Callers should interrupt any RUNNING
        turn (see interrupt_chat_turn) before calling this -- end_chat does not itself check
        for one.

        Raises
        ------
        UnknownSessionError
            If no session with that id exists.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise UnknownSessionError(f"no session with id {session_id!r}.")
            session.collab.chat.backend = None
            session.collab.chat.backend_thread_id = None
            session.collab.chat.active_persona = None
            self._publish(session_id, {"type": "chat_ended", "session_id": session_id})
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
