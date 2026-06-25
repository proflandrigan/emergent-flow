"""
emergentflow.ir.common
~~~~~~~~~~~~~~~~~~~~
Shared primitives for the Emergent Flow graph IR:
  - ID generation (CRDT-friendly stable opaque strings)
  - Core enums (Direction, Cardinality, Paradigm)
  - Shared base model (IRModel)
  - Artifact location reference (ArtifactRef)

ADR refs:
  - ADR 0003: two first-class paradigms
  - ADR 0004: artifact bytes are never embedded in the IR
"""

import uuid
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Discriminator tag identifying a serialized ArtifactRef. See ``ARTIFACT_REF_KIND``
# usage in ``emergentflow.ir.params`` — it lets a serialized ArtifactRef be told apart
# from a plain mapping that happens to share its shape, keeping round-trips lossless.
ARTIFACT_REF_KIND: Literal["artifact_ref"] = "artifact_ref"

# ---------------------------------------------------------------------------
# ID helpers
# ---------------------------------------------------------------------------

IRId = str  # opaque, stable string identifier


def new_id() -> IRId:
    """Generate a fresh stable IR identifier (UUID4 as string)."""
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Core enums — subclass (str, Enum) so they serialise as plain strings
# ---------------------------------------------------------------------------


class Direction(str, Enum):
    """Edge / port directionality."""

    IN = "in"
    OUT = "out"


class Cardinality(str, Enum):
    """How many connections a port / edge end accepts."""

    ONE = "one"
    MANY = "many"


class Paradigm(str, Enum):
    """First-class execution paradigms (ADR 0003)."""

    FUNCTIONAL = "functional"
    DECLARATIVE = "declarative"


# ---------------------------------------------------------------------------
# Shared base model
# ---------------------------------------------------------------------------


class IRModel(BaseModel):
    """Base for all IR models: strict, forbids unknown fields."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


# ---------------------------------------------------------------------------
# ArtifactRef — pointer to a large artifact stored outside the IR (ADR 0004)
# ---------------------------------------------------------------------------


class ArtifactRef(IRModel):
    """Reference to a large artifact stored outside the IR graph.

    Deliberately carries *no* bytes — only a location URI and an optional
    media-type hint.  Embedding artifact bytes in the IR is forbidden by
    ADR 0004.

    The ``kind`` field is a fixed discriminator tag (``"artifact_ref"``). It is
    always emitted on serialization so that an ArtifactRef can be distinguished
    from a plain mapping that happens to share its shape (e.g. a config dict with
    a ``uri`` key). ``ParamValue`` uses it to route deserialization, which keeps
    JSON round-trips lossless. It defaults, so construction stays ``ArtifactRef(uri=...)``.
    """

    kind: Literal["artifact_ref"] = Field(
        default=ARTIFACT_REF_KIND,
        description='Fixed discriminator tag; always "artifact_ref".',
    )
    uri: str = Field(..., description="Location of the artifact (path or object-store URI).")
    media_type: str | None = Field(
        default=None,
        description='Optional MIME hint, e.g. "application/parquet".',
    )

    @field_validator("uri")
    @classmethod
    def uri_must_be_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError(
                "ArtifactRef.uri must be a non-empty, non-whitespace string; "
                "received an empty or blank value."
            )
        return v
