"""
tests/test_collab_personas.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Epic 14, Story 7 — AgentPersona catalog: flat registry unit tests.

The registry is process-global module state; ``_fresh_persona_registry`` resets
``_PERSONAS`` before every test so registrations never leak between cases.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from emergentflow.collab import personas as personas_mod
from emergentflow.collab.personas import (
    AgentPersona,
    UnknownPersonaError,
    get_persona,
    list_personas,
    register_persona,
)


@pytest.fixture(autouse=True)
def _fresh_persona_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate the process-wide persona registry per test."""
    monkeypatch.setattr(personas_mod, "_PERSONAS", {})


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_persona(**overrides: object) -> AgentPersona:
    defaults: dict[str, object] = {
        "slug": "test-persona",
        "label": "Test Persona",
        "description": "A persona for testing.",
    }
    defaults.update(overrides)
    return AgentPersona(**defaults)


# ---------------------------------------------------------------------------
# Register + round-trip
# ---------------------------------------------------------------------------


class TestRegisterAndGet:
    def test_round_trip(self) -> None:
        persona = _make_persona()
        register_persona(persona)
        retrieved = get_persona("test-persona")
        assert retrieved == persona

    def test_get_unknown_raises(self) -> None:
        with pytest.raises(UnknownPersonaError):
            get_persona("does-not-exist")

    def test_duplicate_slug_raises(self) -> None:
        register_persona(_make_persona())
        with pytest.raises(ValueError, match="already registered"):
            register_persona(_make_persona())

    def test_list_returns_sorted(self) -> None:
        register_persona(_make_persona(slug="z-persona", label="Z", description="Z desc"))
        register_persona(_make_persona(slug="a-persona", label="A", description="A desc"))
        register_persona(_make_persona(slug="m-persona", label="M", description="M desc"))
        slugs = [p.slug for p in list_personas()]
        assert slugs == ["a-persona", "m-persona", "z-persona"]

    def test_list_returns_empty_when_nothing_registered(self) -> None:
        assert list_personas() == []


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidation:
    def test_empty_slug_raises(self) -> None:
        with pytest.raises(ValidationError) as exc:
            _make_persona(slug="")
        assert "non-empty" in str(exc.value)

    def test_whitespace_slug_raises(self) -> None:
        with pytest.raises(ValidationError) as exc:
            _make_persona(slug="   ")
        assert "non-empty" in str(exc.value)

    def test_empty_label_raises(self) -> None:
        with pytest.raises(ValidationError) as exc:
            _make_persona(label="")
        assert "non-empty" in str(exc.value)

    def test_whitespace_label_raises(self) -> None:
        with pytest.raises(ValidationError) as exc:
            _make_persona(label="  \t  ")
        assert "non-empty" in str(exc.value)

    def test_empty_description_raises(self) -> None:
        with pytest.raises(ValidationError) as exc:
            _make_persona(description="")
        assert "non-empty" in str(exc.value)

    def test_whitespace_description_raises(self) -> None:
        with pytest.raises(ValidationError) as exc:
            _make_persona(description="   ")
        assert "non-empty" in str(exc.value)


# ---------------------------------------------------------------------------
# JSON round-trip
# ---------------------------------------------------------------------------


class TestJsonRoundTrip:
    def test_required_fields_only(self) -> None:
        persona = AgentPersona(slug="minimal", label="Minimal", description="Just the basics")
        dumped = persona.model_dump(mode="json")
        restored = AgentPersona.model_validate(dumped)
        assert restored == persona
        assert restored.node_families == []

    def test_all_fields(self) -> None:
        persona = AgentPersona(
            slug="full",
            label="Full Persona",
            description="All fields populated.",
            node_families=["data", "stats"],
            system_prompt="You are a data expert.",
            source_path="agents/data-modeller.md",
        )
        dumped = persona.model_dump(mode="json")
        restored = AgentPersona.model_validate(dumped)
        assert restored == persona

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AgentPersona.model_validate(
                {
                    "slug": "x",
                    "label": "X",
                    "description": "X desc",
                    "unknown_field": "should not be allowed",
                }
            )


# ---------------------------------------------------------------------------
# Built-in personas (persona_defs)
# ---------------------------------------------------------------------------


class TestRegisterBuiltinPersonas:
    def test_registers_all_personas(self) -> None:
        from emergentflow.collab.persona_defs import register_builtin_personas

        register_builtin_personas()
        dm = get_persona("data_modeller")
        assert dm.label == "Data Modeller"
        assert dm.node_families == ["data"]
        assert dm.source_path == "agents/data-modeller.md"

        rs = get_persona("researcher")
        assert rs.label == "Researcher"
        assert rs.node_families == ["stats"]
        assert rs.source_path == "agents/researcher.md"

    def test_idempotent_second_call_does_not_duplicate(self) -> None:
        from emergentflow.collab.persona_defs import register_builtin_personas

        register_builtin_personas()
        register_builtin_personas()  # must not raise
        assert len(list_personas()) == 4

    def test_registers_data_scientist(self) -> None:
        from emergentflow.collab.persona_defs import register_builtin_personas

        register_builtin_personas()
        ds = get_persona("data_scientist")
        assert ds.label == "Data Scientist"
        assert ds.node_families == ["data", "stats", "ml"]
        assert ds.source_path == "agents/data-scientist.md"

    def test_registers_ml_engineer(self) -> None:
        from emergentflow.collab.persona_defs import register_builtin_personas

        register_builtin_personas()
        me = get_persona("ml_engineer")
        assert me.label == "ML Engineer"
        assert me.node_families == ["ml", "recommend"]
        assert me.source_path == "agents/ml-engineer.md"

    def test_researcher_description_updated(self) -> None:
        from emergentflow.collab.persona_defs import register_builtin_personas

        register_builtin_personas()
        rs = get_persona("researcher")
        assert rs.description == (
            "Reviews stats nodes for methodology soundness — assumptions, power, multiple "
            "comparisons, distribution assessment."
        )

    def test_list_personas_returns_all_four(self) -> None:
        from emergentflow.collab.persona_defs import register_builtin_personas

        register_builtin_personas()
        slugs = [p.slug for p in list_personas()]
        assert slugs == ["data_modeller", "data_scientist", "ml_engineer", "researcher"]
