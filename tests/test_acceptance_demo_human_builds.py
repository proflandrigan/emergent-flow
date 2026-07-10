"""
tests/test_acceptance_demo_human_builds.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Epic 14, Story 12 — "human builds, agent reviews" acceptance demo: a pytest "agent"
(an HTTP client following agents/emergent-flow-collaborator.md's Review workflow section)
posts two findings (one info, one warning with an attached fix) on a human-seeded graph
with a planted encoding flaw, "the human" applies the fix via the ordinary proposal
machinery, and the fixed graph re-validates clean, compiles to ruff-clean Python, AND
executes to real results. No LLM anywhere — the test IS the agent.
"""

from __future__ import annotations

import ast
import pathlib
import subprocess
import sys
from typing import Any

import pytest
from fastapi.testclient import TestClient

from emergentflow.collab import session as session_mod
from emergentflow.server.app import configure_session_auth, create_app

SAMPLE_CSV = (
    pathlib.Path(__file__).resolve().parents[1] / "examples" / "vertical_slice" / "sample.csv"
)


@pytest.fixture(autouse=True)
def _fresh_session_store(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(session_mod, "_default_store", None)
    configure_session_auth(required=False)


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def _seed_graph() -> dict[str, Any]:
    """A single data.load_csv node reading the real bundled CSV with a stale encoding --
    the "flaw" the reviewer will flag and fix."""
    return {
        "paradigm": "functional",
        "nodes": {
            "n1": {
                "id": "n1",
                "type": "data.load_csv",
                "label": "Load CSV",
                "paradigm": "functional",
                "params": [
                    {
                        "name": "path",
                        "type_token": "str",
                        "value": str(SAMPLE_CSV),
                        "default": None,
                    },
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


def test_human_builds_and_agent_reviews_then_fixed_graph_compiles_and_executes(
    client: TestClient,
) -> None:
    session = client.post("/sessions", json={"graph": _seed_graph()}).json()
    session_id = session["id"]
    version = session["version"]

    # --- The reviewer posts an INFO finding: no fix needed, just an observation. ---
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

    # --- The reviewer posts a WARNING finding WITH a mechanical fix attached. ---
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

    # --- "The human" replies, then applies the fix via ordinary proposal machinery. ---
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

    # --- NEW — the fixed graph compiles to ruff-clean .py ---
    final_graph = accepted["graph"]
    compiled = client.post("/compile", json=final_graph)
    assert compiled.status_code == 200, compiled.text
    code = compiled.json()["code"]
    ast.parse(code)

    proc = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--stdin-filename", "generated.py", "-"],
        input=code,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"ruff check failed:\n{proc.stdout}\n{proc.stderr}"

    # --- NEW — the fixed graph executes to real results ---
    executed = client.post("/execute", json=final_graph)
    assert executed.status_code == 200, executed.text
    body = executed.json()
    assert body["statuses"]["n1"]["status"] == "ok", body["statuses"]["n1"]
    assert body["results"]["n1"]["frame"]["kind"] == "table"
