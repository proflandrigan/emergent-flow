"""
tests/test_agent_persona_review.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Epic 14, Story 7 — scripted-agent persona review tests: a pytest "agent" (an HTTP
client following agents/emergent-flow-collaborator.md's Review workflow) posts
findings using the built-in persona slugs and asserts the registry entry backing
that slug matches. No LLM anywhere — the test IS the agent.
"""

from __future__ import annotations

import pathlib
from typing import Any

import pytest
from fastapi.testclient import TestClient

from emergentflow.collab import personas as personas_mod
from emergentflow.collab import session as session_mod
from emergentflow.collab.persona_defs import register_builtin_personas
from emergentflow.collab.personas import get_persona
from emergentflow.server.app import configure_session_auth, create_app

SAMPLE_CSV = (
    pathlib.Path(__file__).resolve().parents[1] / "examples" / "vertical_slice" / "sample.csv"
)


@pytest.fixture(autouse=True)
def _fresh_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset both the session store and the persona registry per test, then register
    the two built-in personas so every test starts with exactly the expected set."""
    monkeypatch.setattr(session_mod, "_default_store", None)
    monkeypatch.setattr(personas_mod, "_PERSONAS", {})
    configure_session_auth(required=False)
    register_builtin_personas()


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def _load_csv_node() -> dict[str, Any]:
    return {
        "id": "n1",
        "type": "data.load_csv",
        "label": "Load CSV",
        "paradigm": "functional",
        "params": [
            {"name": "path", "type_token": "str", "value": str(SAMPLE_CSV), "default": None},
            {"name": "encoding", "type_token": "str", "value": "utf-8", "default": "utf-8"},
        ],
        "ports": [
            {
                "id": "p1",
                "name": "frame",
                "direction": "out",
                "data_type": "DataFrame",
                "cardinality": "one",
            },
        ],
        "position": {"x": 0.0, "y": 0.0},
        "group_id": None,
    }


def _stats_describe_node() -> dict[str, Any]:
    return {
        "id": "n2",
        "type": "stats.describe",
        "label": "Describe",
        "paradigm": "functional",
        "params": [
            {"name": "columns", "type_token": "list[str]", "value": None, "default": None},
        ],
        "ports": [
            {
                "id": "p2-in",
                "name": "frame",
                "direction": "in",
                "data_type": "DataFrame",
                "cardinality": "one",
            },
            {
                "id": "p2-out",
                "name": "summary",
                "direction": "out",
                "data_type": "DataFrame",
                "cardinality": "one",
            },
        ],
        "position": {"x": 260.0, "y": 0.0},
        "group_id": None,
    }


def test_data_modeller_reviews_a_data_node(client: TestClient) -> None:
    graph = {"paradigm": "functional", "nodes": {"n1": _load_csv_node()}, "edges": {}}
    session = client.post("/sessions", json={"graph": graph}).json()
    session_id = session["id"]

    resp = client.post(
        f"/sessions/{session_id}/reviews",
        json={
            "author": "data_modeller",
            "findings": [
                {
                    "severity": "info",
                    "code": "grain_check",
                    "message": "Single-node ingest -- grain is trivially one row per source row.",
                    "node_id": "n1",
                    "source": "data_modeller",
                }
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    thread = resp.json()
    assert thread["findings"][0]["source"] == "data_modeller"
    assert get_persona("data_modeller").node_families == ["data"]


def test_researcher_reviews_a_stats_node(client: TestClient) -> None:
    graph = {
        "paradigm": "functional",
        "nodes": {
            "n1": _load_csv_node(),
            "n2": _stats_describe_node(),
        },
        "edges": {
            "e1": {
                "id": "e1",
                "source": {"node_id": "n1", "port_id": "p1"},
                "target": {"node_id": "n2", "port_id": "p2-in"},
            }
        },
    }
    session = client.post("/sessions", json={"graph": graph}).json()
    session_id = session["id"]

    resp = client.post(
        f"/sessions/{session_id}/reviews",
        json={
            "author": "researcher",
            "findings": [
                {
                    "severity": "info",
                    "code": "describe_cols",
                    "message": "All numeric columns described -- restrict to known features.",
                    "node_id": "n2",
                    "source": "researcher",
                }
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    thread = resp.json()
    assert thread["findings"][0]["source"] == "researcher"
    assert get_persona("researcher").node_families == ["stats"]
