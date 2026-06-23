"""
colonymind.ir.params
~~~~~~~~~~~~~~~~~~~~
Typed, serializable parameter model for Colony Mind IR nodes.

A ``Param`` holds a named, typed parameter value.  Values are restricted to
JSON-native scalars, homogeneous lists/dicts, or ``ArtifactRef`` location
pointers (ADR 0004 — artifact bytes are never embedded).

``type_token`` is a declared-type label for the param value (e.g. ``"str"``,
``"int"``, ``"DataFrame"``). The connection type system (``colonymind.types``,
``docs/type-system-spec.md``) governs *port* ``data_type`` compatibility; param
``type_token`` is a descriptive label and is not part of that compatibility check.
"""

from typing import Annotated, Any, Union

from pydantic import Discriminator, Tag, field_validator
from typing_extensions import TypeAliasType

from .common import ARTIFACT_REF_KIND, ArtifactRef, IRModel

# ---------------------------------------------------------------------------
# Value type alias
# ---------------------------------------------------------------------------

JsonScalar = str | int | float | bool | None


def _param_value_discriminator(v: Any) -> str:
    """Route a ParamValue to the right union member.

    A serialized ArtifactRef is a JSON object that *also* validates as
    ``dict[str, ParamValue]``, so a plain config mapping shaped like an ArtifactRef
    (e.g. ``{"uri": "..."}``) would otherwise decay into — or masquerade as — an
    ArtifactRef across a round-trip. The fixed ``kind="artifact_ref"`` tag
    (``ArtifactRef.kind``) disambiguates: only mappings carrying that tag are parsed
    as ArtifactRef; every other mapping stays a plain mapping. This makes JSON
    round-trips lossless in both directions.
    """
    if isinstance(v, ArtifactRef):
        return "artifact_ref"
    if isinstance(v, dict):
        return "artifact_ref" if v.get("kind") == ARTIFACT_REF_KIND else "mapping"
    if isinstance(v, (list, tuple, set, frozenset)):
        # set/frozenset are not JSON-native; the sequence member lax-coerces them
        # to a list, preserving the prior "serializable, not identity" contract.
        return "sequence"
    return "scalar"


# ParamValue covers JSON-native data plus ArtifactRef (artifact location pointer).
# This is a *recursive* alias (lists/dicts of ParamValue). Pydantic v2 cannot build a
# core schema for a bare recursive ``Union`` alias under ``from __future__ import
# annotations`` (it recurses infinitely — see pydantic docs on named recursive types).
# ``TypeAliasType`` gives the alias a name so Pydantic can tie the recursive knot. This
# is the PEP-695-equivalent for Python 3.11, which lacks the native ``type`` statement.
# The members are a tagged (discriminated) union: ``_param_value_discriminator`` picks the
# member by inspecting the value, so ArtifactRef and plain mappings never collide.
ParamValue = TypeAliasType(
    "ParamValue",
    "Annotated[Union["
    "Annotated[JsonScalar, Tag('scalar')],"
    "Annotated[ArtifactRef, Tag('artifact_ref')],"
    "Annotated[list[ParamValue], Tag('sequence')],"
    "Annotated[dict[str, ParamValue], Tag('mapping')]"
    "], Discriminator(_param_value_discriminator)]",
)


# ---------------------------------------------------------------------------
# Param model
# ---------------------------------------------------------------------------


class Param(IRModel):
    """A single typed, defaulted, serializable parameter on an IR node.

    Fields
    ------
    name:
        Non-empty parameter name.
    type_token:
        Declared-type label (e.g. ``"str"``, ``"int"``, ``"DataFrame"``). A
        descriptive label for the param value, distinct from the port
        ``data_type`` tokens the connection type system validates.
    value:
        Current serializable value.  Defaults to ``None``.
    default:
        Default serializable value.  Defaults to ``None``.
    """

    name: str
    type_token: str
    value: ParamValue = None
    default: ParamValue = None

    @field_validator("name")
    @classmethod
    def name_must_be_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError(
                "Param.name must be a non-empty, non-whitespace string; "
                "received an empty or blank value."
            )
        return v

    @field_validator("type_token")
    @classmethod
    def type_token_must_be_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError(
                "Param.type_token must be a non-empty, non-whitespace string; "
                "received an empty or blank value."
            )
        return v


# Resolve forward references in the recursive ParamValue alias.
Param.model_rebuild()
