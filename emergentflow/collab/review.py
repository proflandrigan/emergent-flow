"""
emergentflow.collab.review
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Review threads (Epic 14 Story 6): the other half of two-way collaboration. Where a
GraphMutation proposal is "an agent builds", a ReviewThread is "an agent critiques" -- findings
are ordinary Diagnostic objects (the Story 6 Severity.INFO/source extension) anchored to real
graph elements via their existing node_id/edge_id/port_id fields, so the canvas renders review
findings through the SAME diagnostics path ef.validate output already uses -- no parallel
annotation system. A finding with an attached ``fix`` GraphMutation offers a one-click "apply fix"
that is an ORDINARY proposal accept (Story 4 machinery) -- this module adds zero new apply code.

CollaborationState lives on GraphSession.collab, BESIDE the graph, never on it (epic invariant):
this module is never imported by emergentflow/__init__.py or emergentflow/ir/graph.py.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from emergentflow.codegen.validation import Diagnostic
from emergentflow.ir.common import new_id
from emergentflow.ir.graph import Graph
from emergentflow.ir.mutation import GraphMutation


class AnchorError(Exception):
    """Raised when a review finding's node_id/edge_id/port_id doesn't resolve against the
    session's graph -- the server rejects unanchored findings rather than storing a review
    thread that points at nothing (or, worse, at some OTHER graph's element)."""


class ReviewStatus(str, Enum):
    """Lifecycle status of a review thread."""

    OPEN = "open"
    RESOLVED = "resolved"


class ReviewComment(BaseModel):
    """A single reply on a review thread (human or agent)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=new_id)
    author: str
    text: str


class ReviewThread(BaseModel):
    """An agent's (or human's) review of the session graph.

    ``findings`` are ordinary ``Diagnostic`` objects anchored to real graph elements.
    ``fix`` is an optional one-click-apply ``GraphMutation`` -- applying it is an ORDINARY
    proposal accept (Story 4), not new apply code.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=new_id)
    author: str
    findings: list[Diagnostic] = Field(default_factory=list)
    comments: list[ReviewComment] = Field(default_factory=list)
    fix: GraphMutation | None = None
    status: ReviewStatus = ReviewStatus.OPEN


class CollaborationState(BaseModel):
    """Session-scoped collaboration state beyond the graph itself.

    Lives on ``GraphSession.collab`` (``emergentflow/collab/session.py``), BESIDE the graph,
    never a ``Graph`` field. Holds review threads today; Story 9 (gates, out of scope here)
    extends this same model with a ``gates`` list later -- do not add one now.
    """

    model_config = ConfigDict(extra="forbid")

    reviews: dict[str, ReviewThread] = Field(default_factory=dict)


def validate_anchors(graph: Graph, findings: list[Diagnostic]) -> None:
    """Raise AnchorError if any *findings* entry anchors to a node/edge/port id that does not
    exist in *graph*. A finding with all three anchor fields None (a graph-wide comment) always
    passes -- there is nothing to resolve.

    Pure: does not mutate *graph* or *findings*.
    """
    port_ids = {port.id for node in graph.nodes.values() for port in node.ports}
    for finding in findings:
        if finding.node_id is not None and finding.node_id not in graph.nodes:
            raise AnchorError(
                f"finding anchors to unknown node_id {finding.node_id!r} "
                f"(not present in the session's graph)."
            )
        if finding.edge_id is not None and finding.edge_id not in graph.edges:
            raise AnchorError(
                f"finding anchors to unknown edge_id {finding.edge_id!r} "
                f"(not present in the session's graph)."
            )
        if finding.port_id is not None and finding.port_id not in port_ids:
            raise AnchorError(
                f"finding anchors to unknown port_id {finding.port_id!r} "
                f"(not present in the session's graph)."
            )
