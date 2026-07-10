"""
tests/test_acceptance_demo_agent_builds.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Epic 14, Story 12 — "agent builds, human accepts" acceptance demo: a pytest
"agent" (an HTTP client following the call sequence documented in
agents/emergent-flow-collaborator.md) seeds a session with a load_csv -> describe
graph, proposes extending it with a parallel stats.describe + series viz.plot pair
(built from live /catalog data), gets a clean diagnostics verdict, "the human"
accepts, and the resulting graph compiles to ruff-clean Python AND executes to
real results via the standard (non-session) routes. No LLM anywhere — the test IS
the agent, proving Story 12's payoff needs nothing but an HTTP client.
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


def test_agent_builds_describe_and_chart_pair_and_human_accepts(client: TestClient) -> None:
    # --- Step 1: seed session with load_csv -> describe ---
    catalog = client.get("/catalog").json()
    describe_spec = _catalog_spec(catalog, "stats.describe")
    plot_spec = _catalog_spec(catalog, "viz.plot")

    n2 = _node_from_catalog_spec(
        describe_spec,
        node_id="n2",
        port_ids={"frame": "p2-in", "summary": "p2-out"},
        param_overrides={},
        position={"x": 260.0, "y": 0.0},
    )

    seed_graph = {
        "paradigm": "functional",
        "nodes": {"n1": _load_csv_node(), "n2": n2},
        "edges": {
            "e1": {
                "id": "e1",
                "source": {"node_id": "n1", "port_id": "p1"},
                "target": {"node_id": "n2", "port_id": "p2-in"},
            },
        },
    }
    session = client.post("/sessions", json={"graph": seed_graph}).json()
    session_id = session["id"]
    base_version = session["version"]
    assert base_version == 0

    # --- Step 2: agent discovers the session via GET /sessions ---
    listed = client.get("/sessions").json()["sessions"]
    assert any(s["id"] == session_id for s in listed)

    # --- Step 3: read /catalog and build the stats.describe + viz.plot pair ---
    n3 = _node_from_catalog_spec(
        describe_spec,
        node_id="n3",
        port_ids={"frame": "p3-in", "summary": "p3-out"},
        param_overrides={},
        position={"x": 520.0, "y": 0.0},
    )
    n3["label"] = "Describe (extension)"

    plot_out_port_name = next(p["name"] for p in plot_spec["ports"] if p["direction"] == "out")

    n4 = _node_from_catalog_spec(
        plot_spec,
        node_id="n4",
        port_ids={"frame": "p4-in", plot_out_port_name: "p4-out"},
        param_overrides={"chart": "histogram", "encoding": {"x": "score"}},
        position={"x": 520.0, "y": 160.0},
    )

    new_edges = {
        "e2": {
            "id": "e2",
            "source": {"node_id": "n1", "port_id": "p1"},
            "target": {"node_id": "n3", "port_id": "p3-in"},
        },
        "e3": {
            "id": "e3",
            "source": {"node_id": "n3", "port_id": "p3-out"},
            "target": {"node_id": "n4", "port_id": "p4-in"},
        },
    }

    # --- Step 4: pre-flight the FULL candidate graph ---
    candidate_graph = {
        "paradigm": "functional",
        "nodes": {"n1": _load_csv_node(), "n2": n2, "n3": n3, "n4": n4},
        "edges": {
            "e1": {
                "id": "e1",
                "source": {"node_id": "n1", "port_id": "p1"},
                "target": {"node_id": "n2", "port_id": "p2-in"},
            },
            **new_edges,
        },
    }
    preflight = client.post("/validate", json=candidate_graph)
    assert preflight.status_code == 200, preflight.text
    assert preflight.json()["diagnostics"]["diagnostics"] == []

    preflight_compile = client.post("/compile", json=candidate_graph)
    assert preflight_compile.status_code == 200, preflight_compile.text
    assert "import emergentflow as ef" in preflight_compile.json()["code"]

    # --- Step 5: submit the proposal as a GraphMutation ---
    mutation = {
        "base_version": base_version,
        "add_nodes": [n3, n4],
        "add_edges": [
            {"id": eid, "source": e["source"], "target": e["target"]}
            for eid, e in new_edges.items()
        ],
        "description": "Add parallel describe + series histogram chart",
        "author": "emergent-flow-collaborator",
    }
    proposal_resp = client.post(f"/sessions/{session_id}/proposals", json=mutation)
    assert proposal_resp.status_code == 200, proposal_resp.text
    proposal = proposal_resp.json()
    assert proposal["status"] == "pending"
    assert proposal["diagnostics"]["diagnostics"] == []

    # --- Step 6: "the human" accepts ---
    accepted = client.post(f"/sessions/{session_id}/proposals/{proposal['id']}/accept")
    assert accepted.status_code == 200, accepted.text
    accepted_session = accepted.json()
    assert accepted_session["version"] == base_version + 1
    assert set(accepted_session["graph"]["nodes"].keys()) == {"n1", "n2", "n3", "n4"}

    # --- Step 7: accepted graph compiles to ruff-clean .py ---
    final_graph = accepted_session["graph"]

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

    # --- Step 8: accepted graph executes to real results ---
    executed = client.post("/execute", json=final_graph)
    assert executed.status_code == 200, executed.text
    body = executed.json()
    for node_id in ("n1", "n2", "n3", "n4"):
        assert body["statuses"][node_id]["status"] == "ok", body["statuses"][node_id]
    assert body["results"]["n1"]["frame"]["kind"] == "table"
    assert body["results"]["n2"]["summary"]["kind"] == "table"
    assert body["results"]["n3"]["summary"]["kind"] == "table"
    assert plot_out_port_name in body["results"]["n4"]
