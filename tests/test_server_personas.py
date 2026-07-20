"""
tests/test_server_personas.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Epic 14, Story 7 — AgentPersona catalog: server integration tests.

``GET /personas`` is a plain, unauthenticated GET returning static catalog
metadata (like ``/catalog``), so this file uses the same simple ``client``
fixture as ``tests/test_server_sessions.py`` — no auth, no session dependency.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from emergentflow.collab import personas as personas_mod
from emergentflow.server.app import create_app


@pytest.fixture(autouse=True)
def _fresh_persona_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate the process-wide persona registry per test."""
    monkeypatch.setattr(personas_mod, "_PERSONAS", {})


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_get_personas_returns_empty_list_when_nothing_registered(client: TestClient) -> None:
    r = client.get("/personas")
    assert r.status_code == 200, r.text
    assert r.json() == {"personas": []}


def test_get_personas_returns_all_builtins(client: TestClient) -> None:
    from emergentflow.collab.persona_defs import register_builtin_personas

    register_builtin_personas()
    r = client.get("/personas")
    assert r.status_code == 200, r.text
    body = r.json()
    slugs = [p["slug"] for p in body["personas"]]
    assert slugs == ["data_modeller", "data_scientist", "ml_engineer", "researcher"]
    for p in body["personas"]:
        assert "label" in p
        assert "description" in p
        assert "node_families" in p
