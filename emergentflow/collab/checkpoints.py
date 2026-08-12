"""
emergentflow.collab.checkpoints
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Checkpoint model (Epic 14 Story 10): the primitive that makes every agent edit
auto-applied, versioned, and reversible. A ``Checkpoint`` records a mutation
that was applied directly to a session's graph (kind EDIT) or a mutation that
reversed an earlier one (kind REVERT), together with a full snapshot of the
graph *before* that mutation/revert landed, so ``SessionStore.revert_checkpoint``
can restore the graph to any prior state.

Lives on ``CollaborationState.checkpoints``, BESIDE the graph, never on it
(epic invariant): this module is never imported by ``emergentflow/__init__.py``
or ``emergentflow/ir/graph.py``.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from emergentflow.ir.common import new_id
from emergentflow.ir.graph import Graph
from emergentflow.ir.mutation import GraphMutation


class CheckpointKind(str, Enum):
    """The flavor of a Checkpoint: an applied edit, or a revert of an earlier one."""

    EDIT = "edit"
    REVERT = "revert"


class Checkpoint(BaseModel):
    """One recorded graph transition on a session's CollaborationState.

    ``previous_graph`` is a full snapshot of the graph *before* the mutation
    (or revert) landed, so a revert can restore it exactly. ``base_version`` is
    the session version the checkpoint was computed against; ``resulting_version``
    is the session version after the mutation/revert.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=new_id)
    kind: CheckpointKind
    author: str = "agent"
    description: str = ""
    timestamp: float = Field(default_factory=lambda: __import__("time").time())
    base_version: int
    mutation: GraphMutation
    previous_graph: Graph
    resulting_version: int
