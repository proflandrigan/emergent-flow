"""
emergentflow.collab.gates
~~~~~~~~~~~~~~~~~~~~~~~~~
Shards' checkpoint pattern (Epic 14 Story 9): a ``Gate`` marks a workflow
checkpoint an agent opens and the human (or another agent) closes/skips, with
``Decision`` s recording what was decided along the way. Lives on
``CollaborationState.gates``, BESIDE the graph, never on it. This module is
never imported by ``emergentflow/__init__.py`` or ``emergentflow/ir/graph.py``.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from emergentflow.ir.common import new_id


class GateError(Exception):
    """Base class for all gate errors."""


class UnknownGateError(GateError):
    """Raised when a gate id does not exist on a session."""


class GateAlreadyResolvedError(GateError):
    """Raised when close/skip targets a gate that is no longer OPEN.

    Mirrors ProposalAlreadyResolvedError's one-shot transition discipline
    (emergentflow/collab/session.py): a gate's status transition is one-shot --
    once closed or skipped, it cannot be re-resolved, so a stale double-close
    (or a close racing a skip) never silently flips an already-decided gate.
    """


class GateKind(str, Enum):
    """The checkpoint flavor a Gate represents (Shards' vocabulary)."""

    PHASE = "phase"
    CONFIRM = "confirm"
    HANDOFF = "handoff"
    EXECUTE = "execute"
    FINAL = "final"


class GateStatus(str, Enum):
    """Lifecycle status of a Gate."""

    OPEN = "open"
    CLOSED = "closed"
    SKIPPED = "skipped"


class Decision(BaseModel):
    """One recorded decision on a Gate's timeline (human or agent)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=new_id)
    author: str
    text: str


class Gate(BaseModel):
    """A workflow checkpoint on a session's CollaborationState.

    ``decisions`` accumulate over the gate's OPEN lifetime; once ``status`` moves to
    CLOSED or SKIPPED it is final (GateAlreadyResolvedError guards re-transition at the
    SessionStore level, not on this model itself -- the model stays a plain data container,
    same division of labor as ReviewThread/StoredProposal).
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=new_id)
    phase: str
    kind: GateKind
    description: str
    status: GateStatus = GateStatus.OPEN
    decisions: list[Decision] = Field(default_factory=list)
