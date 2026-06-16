"""
colonymind.ir.params
~~~~~~~~~~~~~~~~~~~~
Typed, serializable parameter model for Colony Mind IR nodes.

A ``Param`` holds a named, typed parameter value.  Values are restricted to
JSON-native scalars, homogeneous lists/dicts, or ``ArtifactRef`` location
pointers (ADR 0004 — artifact bytes are never embedded).

The full type system lives in Epic 5; ``type_token`` is an opaque label for
now (e.g. ``"str"``, ``"int"``, ``"DataFrame"``).
"""

from typing import Union

from pydantic import field_validator
from typing_extensions import TypeAliasType

from .common import ArtifactRef, IRModel

# ---------------------------------------------------------------------------
# Value type alias
# ---------------------------------------------------------------------------

JsonScalar = Union[str, int, float, bool, None]

# ParamValue covers JSON-native data plus ArtifactRef (artifact location pointer).
# This is a *recursive* alias (lists/dicts of ParamValue). Pydantic v2 cannot build a
# core schema for a bare recursive ``Union`` alias under ``from __future__ import
# annotations`` (it recurses infinitely — see pydantic docs on named recursive types).
# ``TypeAliasType`` gives the alias a name so Pydantic can tie the recursive knot. This
# is the PEP-695-equivalent for Python 3.11, which lacks the native ``type`` statement.
# ArtifactRef is placed before list/dict: a serialized ArtifactRef is a JSON object that
# also validates as ``dict[str, ParamValue]``. Pydantic's smart union mode tie-breaks by
# declaration order, so ArtifactRef must precede dict to be preserved across a round-trip
# rather than decaying into a plain dict.
ParamValue = TypeAliasType(
    "ParamValue",
    "Union[JsonScalar, ArtifactRef, list[ParamValue], dict[str, ParamValue]]",
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
        Opaque declared-type label (e.g. ``"str"``, ``"int"``, ``"DataFrame"``).
        The real type system is Epic 5; this is a placeholder label only.
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
