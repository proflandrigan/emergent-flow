"""
colonymind.ir.node
~~~~~~~~~~~~~~~~~~
Node model — the central element of the Colony Mind graph IR.

Per ADR 0003 (Option A: unified nesting + paradigm tag), a node may optionally
own an inner sub-graph.  This single mechanism covers collapsible visual groups,
declarative nn.Module bodies, and agent graphs alike.  The codegen/executor
branches on the ``paradigm`` tag; the IR shape is uniform.

The ``subgraph`` field holds a forward reference to ``Graph`` (Task 07).
``Node.model_rebuild()`` is NOT called here — graph.py (Task 07) imports Node
and calls ``Node.model_rebuild()`` once ``Graph`` is defined, resolving the
forward reference at that point.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field, field_validator

from .common import IRId, IRModel, Paradigm, new_id
from .params import Param
from .port import Port

if TYPE_CHECKING:
    from .graph import Graph


# ---------------------------------------------------------------------------
# Position — canvas coordinates
# ---------------------------------------------------------------------------


class Position(IRModel):
    """2-D canvas coordinates for a node's visual placement."""

    x: float = 0.0
    y: float = 0.0


# ---------------------------------------------------------------------------
# Node — central IR element
# ---------------------------------------------------------------------------


class Node(IRModel):
    """A typed, parameterised node in the Colony Mind graph IR.

    Attributes
    ----------
    id:
        Stable unique identifier (auto-generated via ``new_id()``).
    type:
        Node type/family key, e.g. ``"data.load_csv"`` (required, non-empty).
    label:
        Optional human-friendly display label.
    paradigm:
        Which execution paradigm this node belongs to (default: FUNCTIONAL).
    params:
        Typed parameter values attached to this node.
    ports:
        The node's in/out connection points.
    position:
        Canvas coordinates (default: origin ``(0.0, 0.0)``).
    group_id:
        ID of the parent group/composite node this node belongs to, or
        ``None`` if this is a top-level node.
    subgraph:
        Optional inner graph for composite/module/agent nodes (Option A
        nesting from ADR 0003).  ``None`` for leaf nodes.  Forward-ref to
        ``Graph``; resolved by ``Node.model_rebuild()`` in Task 07
        (``colonymind/ir/graph.py``).
    """

    id: IRId = Field(default_factory=new_id)
    type: str
    label: str | None = None
    paradigm: Paradigm = Paradigm.FUNCTIONAL
    params: list[Param] = Field(default_factory=list)
    ports: list[Port] = Field(default_factory=list)
    position: Position = Field(default_factory=Position)
    group_id: IRId | None = None
    # Forward reference — Graph does not exist yet (Task 07).
    # Do NOT call Node.model_rebuild() here; graph.py resolves this ref.
    subgraph: "Graph | None" = None

    @field_validator("type")
    @classmethod
    def type_must_be_non_empty(cls, v: str) -> str:
        """Reject empty or whitespace-only type strings."""
        if not v or not v.strip():
            raise ValueError(
                "Node.type must be a non-empty, non-whitespace string; "
                "received an empty or blank value."
            )
        return v
