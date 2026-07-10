"""
emergentflow.collab.personas
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
AgentPersona catalog (Epic 14 Story 7): a flat, in-memory registry of collaborator
metadata — labels, descriptions, and system prompts — that the canvas renders as
"ask the ML Engineer" affordances. This is explicitly NOT the node registry
(``emergentflow/nodes/registry.py``): that indexes ``NodeDefinition`` *classes* with
codegen/execute Python behavior; a persona is pure serializable metadata.

Never imported by ``emergentflow/__init__.py``, ``emergentflow/ir/__init__.py``, or anything
under ``emergentflow/codegen/`` — collaboration is an additive, opt-in layer (ADR 0019).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AgentPersona(BaseModel):
    """A collaborator persona: metadata describing an "AI collaborator" that the canvas
    can render as "ask the ML Engineer" affordances and that Shards/Claude Code agents
    can discover.

    ``slug`` is the lookup key in the flat registry. ``label`` and ``description`` are
    human-facing display strings. ``node_families``, when set, constrains which node
    families this persona is relevant for (empty list = all families). ``system_prompt``
    (Mode B, Story 8) is used by the /consult endpoint; ``source_path`` (Mode A) is a
    relative path to a persona markdown file.
    """

    model_config = ConfigDict(extra="forbid")

    slug: str
    label: str
    description: str
    node_families: list[str] = Field(default_factory=list)
    system_prompt: str | None = None
    source_path: str | None = None

    @field_validator("slug", "label", "description")
    @classmethod
    def field_must_be_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError(
                "AgentPersona.slug/label/description must be non-empty, non-whitespace "
                "strings; received an empty or blank value."
            )
        return v


class UnknownPersonaError(Exception):
    """Raised when a persona slug does not exist in the registry."""


_PERSONAS: dict[str, AgentPersona] = {}


def register_persona(persona: AgentPersona) -> None:
    """Register *persona* under its slug. Raises ValueError on a duplicate slug."""
    if persona.slug in _PERSONAS:
        raise ValueError(f"a persona with slug {persona.slug!r} is already registered.")
    _PERSONAS[persona.slug] = persona


def get_persona(slug: str) -> AgentPersona:
    """Return the registered persona for *slug*.

    Raises UnknownPersonaError if no persona with that slug is registered.
    """
    if slug not in _PERSONAS:
        raise UnknownPersonaError(f"no persona with slug {slug!r} is registered.")
    return _PERSONAS[slug]


def list_personas() -> list[AgentPersona]:
    """Return every registered persona, sorted by slug for a deterministic listing."""
    return [_PERSONAS[slug] for slug in sorted(_PERSONAS)]
