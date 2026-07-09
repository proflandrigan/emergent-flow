"""
tests/test_agent_review_flow.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Epic 14, Story 6 -- the scripted-agent review acceptance test: a pytest "agent" (an HTTP client
following agents/emergent-flow-collaborator.md's Review workflow section) posts two findings
(one info, one warning with an attached fix) on a seeded graph, "the human" applies the fix via
the ordinary proposal machinery (Story 4 -- zero new apply code), and the graph validates clean
afterward. No LLM anywhere -- the test IS the agent.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from emergentflow.collab import session as session_mod
from emergentflow.server.app import configure_session_auth, create_app


@pytest.fixture(autouse=True)
def _fresh_session_store(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(session_mod, "_default_store", None)
    configure_session_auth(required=False)


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def _seed_graph() -> dict[str, Any]:
    """A single data.load_csv node whose encoding param is set to a stale value -- the
    "flaw" the reviewer will flag and fix."""
    return {
        "paradigm": "functional",
        "nodes": {
            "n1": {
                "id": "n1",
                "type": "data.load_csv",
                "label": "Load CSV",
                "paradigm": "functional",
                "params": [
                    {"name": "path", "type_token": "str", "value": "a.csv", "default": None},
                    {
                        "name": "encoding",
                        "type_token": "str",
                        "value": "latin-1",
                        "default": "utf-8",
                    },
                ],
                "ports": [
                    {
                        "id": "p1",
                        "name": "frame",
                        "direction": "out",
                        "data_type": "DataFrame",
                        "cardinality": "one",
                    }
                ],
                "position": {"x": 0.0, "y": 0.0},
                "group_id": None,
            }
        },
        "edges": {},
    }


def test_agent_reviews_and_human_applies_the_fix(client: TestClient) -> None:
    session = client.post("/sessions", json={"graph": _seed_graph()}).json()
    session_id = session["id"]
    version = session["version"]

    # --- The agent posts an INFO finding: no fix needed, just an observation. ---
    info_resp = client.post(
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
    assert info_resp.status_code == 200, info_resp.text
    info_thread = info_resp.json()
    assert info_thread["status"] == "open"
    assert info_thread["fix"] is None
    assert info_thread["findings"][0]["severity"] == "info"

    # --- The agent posts a WARNING finding WITH a mechanical fix attached. ---
    fix_mutation = {
        "base_version": version,
        "set_params": {"n1": {"encoding": "utf-8"}},
        "description": "Pin CSV encoding to utf-8 explicitly",
        "author": "data_modeller",
    }
    warning_resp = client.post(
        f"/sessions/{session_id}/reviews",
        json={
            "author": "data_modeller",
            "findings": [
                {
                    "severity": "warning",
                    "code": "encoding_stale",
                    "message": "encoding is pinned to latin-1; recommend utf-8.",
                    "node_id": "n1",
                    "source": "data_modeller",
                }
            ],
            "fix": fix_mutation,
        },
    )
    assert warning_resp.status_code == 200, warning_resp.text
    warning_thread = warning_resp.json()
    assert warning_thread["fix"] is not None
    review_id = warning_thread["id"]

    # --- "The human" replies, then applies the fix -- an ORDINARY proposal accept, zero new
    # apply code (Story 6's explicit requirement, Story 4's machinery unchanged). ---
    reply_resp = client.post(
        f"/sessions/{session_id}/reviews/{review_id}/comments",
        json={"author": "human", "text": "Good catch, applying now."},
    )
    assert reply_resp.status_code == 200, reply_resp.text
    assert reply_resp.json()["comments"][-1]["text"] == "Good catch, applying now."

    proposal = client.post(f"/sessions/{session_id}/proposals", json=fix_mutation).json()
    assert proposal["diagnostics"]["diagnostics"] == []

    accepted = client.post(f"/sessions/{session_id}/proposals/{proposal['id']}/accept").json()
    encoding_param = next(
        p for p in accepted["graph"]["nodes"]["n1"]["params"] if p["name"] == "encoding"
    )
    assert encoding_param["value"] == "utf-8"

    # --- Re-validate: the graph is clean after the fix. ---
    revalidated = client.post("/validate", json=accepted["graph"])
    assert revalidated.status_code == 200, revalidated.text
    assert revalidated.json()["diagnostics"]["diagnostics"] == []


def test_review_rejects_a_finding_anchored_to_an_unknown_node(client: TestClient) -> None:
    session_id = client.post("/sessions", json={"graph": _seed_graph()}).json()["id"]

    resp = client.post(
        f"/sessions/{session_id}/reviews",
        json={
            "author": "data_modeller",
            "findings": [
                {
                    "severity": "warning",
                    "code": "c",
                    "message": "m",
                    "node_id": "does-not-exist",
                }
            ],
        },
    )

    assert resp.status_code == 422, resp.text
