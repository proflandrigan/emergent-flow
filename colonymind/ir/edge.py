"""
colonymind.ir.edge
~~~~~~~~~~~~~~~~~~
Edge model connecting OUT ports on source nodes to IN ports on target nodes.
Edges reference endpoints by id (node id + port id) for CRDT-friendliness.

This module provides:
  - PortRef: an endpoint reference (node_id + port_id).
  - Edge: an edge with source/target PortRefs, optional type-compatibility metadata.

Note: structural cross-reference validation (whether referenced nodes/ports exist)
is done at the Graph level (Task 07), not here. This task only validates that
endpoint ids are non-empty strings.
"""

from pydantic import Field, field_validator

from .common import IRId, IRModel, new_id


class PortRef(IRModel):
    """An endpoint reference: node_id + port_id.

    Used to identify one side of an edge (source or target).
    Both node_id and port_id must be non-empty strings.
    """

    node_id: IRId = Field(..., description="ID of the node containing the port.")
    port_id: IRId = Field(..., description="ID of the port on the node.")

    @field_validator("node_id")
    @classmethod
    def node_id_must_be_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError(
                "PortRef.node_id must be a non-empty, non-whitespace string; "
                "received an empty or blank value."
            )
        return v

    @field_validator("port_id")
    @classmethod
    def port_id_must_be_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError(
                "PortRef.port_id must be a non-empty, non-whitespace string; "
                "received an empty or blank value."
            )
        return v


class Edge(IRModel):
    """An edge connecting an OUT port on a source node to an IN port on a target node.

    Edges reference endpoints by id (node_id + port_id) for CRDT-friendliness,
    not by object reference. Each edge has a unique stable id.

    Attributes:
        id: Stable unique identifier for this edge.
        source: PortRef identifying the OUT-side endpoint.
        target: PortRef identifying the IN-side endpoint.
        type_compatible: Optional type-compatibility metadata. None means "not yet
            checked" (or unknown/unregistered token). Populated by
            ``cm.apply_type_compatibility`` from a ``cm.validate`` result, recording
            whether source/target data-type tokens were found compatible.

    Note: Structural validation of whether referenced nodes/ports exist is handled
    by the Graph model (Task 07), which has full node/port context.
    """

    id: IRId = Field(default_factory=new_id, description="Stable unique identifier for this edge.")
    source: PortRef = Field(..., description="The OUT-side endpoint.")
    target: PortRef = Field(..., description="The IN-side endpoint.")
    type_compatible: bool | None = Field(
        default=None,
        description='Type-compatibility metadata. None="not yet checked". '
        "Set to bool by cm.apply_type_compatibility from a cm.validate result.",
    )
