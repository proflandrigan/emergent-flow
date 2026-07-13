"""
emergentflow.ir.port
~~~~~~~~~~~~~~~~~~
Port model — a typed connection point on a node.

A port is either IN (incoming edge) or OUT (outgoing edge) with a cardinality
constraint (ONE = single connection, MANY = fan-in/out allowed). The data_type
stays a plain string on the wire, but is validated against the type registry and
resolved by whole-graph inference during ``ef.validate`` (see
``emergentflow.types`` and ``docs/type-system-spec.md``). Per-dimension tensor
shape inference is deferred to roadmap Epic 10.
"""

from pydantic import Field, field_validator

from .common import Cardinality, Direction, IRId, IRModel, new_id


class Port(IRModel):
    """A typed connection point on a node.

    Attributes:
        id: Stable unique identifier (auto-generated via new_id()).
        name: Port name, unique within its node (required, non-empty).
        direction: IN or OUT (required).
        data_type: Data-type token (default "any"); validated against the type
            registry and resolved by inference during ``ef.validate``.
        cardinality: How many edges may attach (ONE or MANY; default ONE).
        label: Optional human-friendly display label for the port, copied from
            the originating ``PortSpec`` at instantiation time. Falls back to
            ``name`` for display when unset.
    """

    id: IRId = Field(default_factory=new_id)
    name: str
    direction: Direction
    data_type: str = "any"
    cardinality: Cardinality = Cardinality.ONE
    label: str | None = None

    @field_validator("name")
    @classmethod
    def name_must_be_non_empty(cls, v: str) -> str:
        """Ensure name is non-empty and non-whitespace."""
        if not v or not v.strip():
            raise ValueError(
                "Port.name must be a non-empty, non-whitespace string; "
                "received an empty or blank value."
            )
        return v
