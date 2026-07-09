"""
tests/test_agent_happy_path.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Epic 14, Story 5 — the scripted-agent acceptance test: a pytest "agent" (an HTTP client
following the exact call sequence documented in agents/emergent-flow-collaborator.md) joins a
seeded session, proposes a two-node addition (stats.describe + viz.plot, both wired from an
existing DataFrame output) built from live /catalog data, gets a clean diagnostics verdict,
"the human" accepts, and the resulting graph compiles AND executes real results via the standard
(non-session) /compile and /execute routes. No LLM anywhere -- the test IS the agent, proving
Mode A needs nothing but an HTTP client.
"""

from __future__ import annotations

import pathlib
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


def _load_csv_node() -> dict[str, Any]:
    """The seeded existing node: data.load_csv reading the bundled sample CSV for real."""
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


def _catalog_spec(catalog: dict[str, Any], node_type: str) -> dict[str, Any]:
    matches = [n for n in catalog["nodes"] if n["type"] == node_type]
    assert matches, f"expected {node_type!r} in /catalog"
    return matches[0]


def _node_from_catalog_spec(
    spec: dict[str, Any],
    *,
    node_id: str,
    port_ids: dict[str, str],
    param_overrides: dict[str, Any],
    position: dict[str, float],
) -> dict[str, Any]:
    """Build a full add_nodes entry from a live /catalog spec, the way an agent (or the canvas's
    addNodeFromSpec) would: one Param per catalog param (value = override or catalog default),
    one Port per catalog port with an explicit id the caller mints (port_ids maps port name ->
    the id to assign, since the agent must reference these same ids in add_edges)."""
    params = [
        {
            "name": p["name"],
            "type_token": p["type_token"],
            "value": param_overrides.get(p["name"], p["default"]),
            "default": p["default"],
        }
        for p in spec["params"]
    ]
    ports = [
        {
            "id": port_ids[p["name"]],
            "name": p["name"],
            "direction": p["direction"],
            "data_type": p["data_type"],
            "cardinality": p["cardinality"],
        }
        for p in spec["ports"]
    ]
    return {
        "id": node_id,
        "type": spec["type"],
        "label": spec["label"],
        "paradigm": spec["paradigm"],
        "params": params,
        "ports": ports,
        "position": position,
        "group_id": None,
    }


def test_agent_proposes_describe_and_plot_and_human_accepts(client: TestClient) -> None:
    # --- Step 1-2 (persona): find the server (it's `client`), create/seed a session. ---
    seed_graph = {"paradigm": "functional", "nodes": {"n1": _load_csv_node()}, "edges": {}}
    session = client.post("/sessions", json={"graph": seed_graph}).json()
    session_id = session["id"]
    base_version = session["version"]
    assert base_version == 0

    # An agent discovers the session via GET /sessions rather than being handed the id
    # out-of-band (the Story 5 discovery flow the persona file documents).
    listed = client.get("/sessions").json()["sessions"]
    assert any(s["id"] == session_id for s in listed)

    # --- Step 3 (persona): read the graph + catalog. ---
    catalog = client.get("/catalog").json()
    describe_spec = _catalog_spec(catalog, "stats.describe")
    plot_spec = _catalog_spec(catalog, "viz.plot")

    describe_node = _node_from_catalog_spec(
        describe_spec,
        node_id="n2",
        port_ids={"frame": "p2-in", "summary": "p2-out"},
        param_overrides={},
        position={"x": 260.0, "y": 0.0},
    )
    plot_node = _node_from_catalog_spec(
        plot_spec,
        node_id="n3",
        port_ids={"frame": "p3-in", "plot": "p3-out"},
        param_overrides={"chart": "histogram", "encoding": {"x": "score"}},
        position={"x": 260.0, "y": 160.0},
    )

    # Both new nodes wire from the SAME existing DataFrame output (n1's frame OUT port p1) --
    # "a two-node addition ... on an existing DataFrame output" (epic Story 5).
    edges = {
        "e1": {
            "id": "e1",
            "source": {"node_id": "n1", "port_id": "p1"},
            "target": {"node_id": "n2", "port_id": "p2-in"},
        },
        "e2": {
            "id": "e2",
            "source": {"node_id": "n1", "port_id": "p1"},
            "target": {"node_id": "n3", "port_id": "p3-in"},
        },
    }

    # --- Step 4 (persona): pre-flight the FULL candidate graph via /validate and /compile. ---
    candidate_graph = {
        "paradigm": "functional",
        "nodes": {"n1": _load_csv_node(), "n2": describe_node, "n3": plot_node},
        "edges": edges,
    }
    preflight = client.post("/validate", json=candidate_graph)
    assert preflight.status_code == 200, preflight.text
    assert preflight.json()["diagnostics"]["diagnostics"] == []

    preflight_compile = client.post("/compile", json=candidate_graph)
    assert preflight_compile.status_code == 200, preflight_compile.text
    assert "import emergentflow as ef" in preflight_compile.json()["code"]

    # --- Step 5 (persona): submit the proposal as a GraphMutation (delta, not full graph). ---
    mutation = {
        "base_version": base_version,
        "add_nodes": [describe_node, plot_node],
        "add_edges": [
            {"id": eid, "source": e["source"], "target": e["target"]} for eid, e in edges.items()
        ],
        "description": "Summarize and chart the loaded CSV",
        "author": "emergent-flow-collaborator",
    }
    proposal_resp = client.post(f"/sessions/{session_id}/proposals", json=mutation)
    assert proposal_resp.status_code == 200, proposal_resp.text
    proposal = proposal_resp.json()
    assert proposal["status"] == "pending"
    assert proposal["diagnostics"]["diagnostics"] == []

    # --- "The human" accepts. ---
    accepted = client.post(f"/sessions/{session_id}/proposals/{proposal['id']}/accept")
    assert accepted.status_code == 200, accepted.text
    accepted_session = accepted.json()
    assert accepted_session["version"] == base_version + 1
    assert set(accepted_session["graph"]["nodes"].keys()) == {"n1", "n2", "n3"}

    # --- The accepted graph is an ORDINARY graph: compiles + executes via the standard,
    # non-session routes -- ADR-0002 needs no new gate case for an agent-authored graph. ---
    final_graph = accepted_session["graph"]

    compiled = client.post("/compile", json=final_graph)
    assert compiled.status_code == 200, compiled.text
    assert "import emergentflow as ef" in compiled.json()["code"]

    executed = client.post("/execute", json=final_graph)
    assert executed.status_code == 200, executed.text
    body = executed.json()
    for node_id in ("n1", "n2", "n3"):
        assert body["statuses"][node_id]["status"] == "ok", body["statuses"][node_id]
    assert body["results"]["n1"]["frame"]["kind"] == "table"
    assert body["results"]["n2"]["summary"]["kind"] == "table"
    assert "plot" in body["results"]["n3"]
