"""
tests/test_server_sessions.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Epic 14, Story 3 — graph sessions on the server: full HTTP lifecycle over the
ASGI test client. The "agent" in every test here is literally the HTTP client
-- no LLM anywhere, proving Mode A collaboration needs nothing more than an
HTTP client that speaks this surface.
"""

from __future__ import annotations

import json
import sys
import threading
import time

import pytest
from fastapi.testclient import TestClient

from emergentflow.collab import session as session_mod
from emergentflow.collab.agents.base import AdapterEvent, AgentAdapter, register_adapter
from emergentflow.server.app import configure_session_auth, create_app


@pytest.fixture(autouse=True)
def _fresh_session_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate the process-wide default SessionStore per test (the
    _fresh_default_cache precedent, tests/test_server.py) so sessions created
    by one test never leak into another, and reset the auth gate to its
    default (disabled) so tests never interfere with each other's auth state.
    """
    monkeypatch.setattr(session_mod, "_default_store", None)
    configure_session_auth(required=False)


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


LOAD_CSV_NODE = {
    "id": "n1",
    "type": "data.load_csv",
    "label": "Load",
    "paradigm": "functional",
    "params": [{"name": "path", "type_token": "str", "value": "a.csv", "default": None}],
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


def _seed_graph() -> dict:
    return {"nodes": {"n1": LOAD_CSV_NODE}, "edges": {}}


class TestSessionLifecycle:
    def test_create_empty_session(self, client: TestClient) -> None:
        r = client.post("/sessions", json={})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["version"] == 0
        assert body["graph"]["nodes"] == {}
        assert body["proposals"] == {}
        assert body["open_in_ui"] == f"http://127.0.0.1:8765/?session={body['id']}"

    def test_create_session_with_seed_graph(self, client: TestClient) -> None:
        r = client.post("/sessions", json={"graph": _seed_graph()})
        assert r.status_code == 200, r.text
        assert "n1" in r.json()["graph"]["nodes"]

    def test_get_session(self, client: TestClient) -> None:
        session_id = client.post("/sessions", json={}).json()["id"]
        r = client.get(f"/sessions/{session_id}")
        assert r.status_code == 200, r.text
        assert r.json()["id"] == session_id

    def test_get_unknown_session_404(self, client: TestClient) -> None:
        r = client.get("/sessions/does-not-exist")
        assert r.status_code == 404, r.text

    def test_delete_session(self, client: TestClient) -> None:
        session_id = client.post("/sessions", json={}).json()["id"]
        r = client.delete(f"/sessions/{session_id}")
        assert r.status_code == 200, r.text
        assert client.get(f"/sessions/{session_id}").status_code == 404

    def test_delete_unknown_session_404(self, client: TestClient) -> None:
        r = client.delete("/sessions/does-not-exist")
        assert r.status_code == 404, r.text


class TestReplaceGraph:
    def test_replace_graph_bumps_version(self, client: TestClient) -> None:
        session_id = client.post("/sessions", json={}).json()["id"]
        r = client.put(
            f"/sessions/{session_id}/graph",
            json={"graph": _seed_graph(), "expected_version": 0},
        )
        assert r.status_code == 200, r.text
        assert r.json()["version"] == 1
        assert "n1" in r.json()["graph"]["nodes"]

    def test_replace_graph_stale_version_409(self, client: TestClient) -> None:
        session_id = client.post("/sessions", json={}).json()["id"]
        r = client.put(
            f"/sessions/{session_id}/graph",
            json={"graph": _seed_graph(), "expected_version": 5},
        )
        assert r.status_code == 409, r.text

    def test_replace_graph_unknown_session_404(self, client: TestClient) -> None:
        r = client.put(
            "/sessions/does-not-exist/graph",
            json={"graph": _seed_graph(), "expected_version": 0},
        )
        assert r.status_code == 404, r.text

    def test_concurrent_writers_only_one_succeeds(self, client: TestClient) -> None:
        # Both writers race to replace the SAME session's graph against the
        # SAME expected_version=0. Exactly one must succeed (200); the other
        # must see a 409 (its expected_version is now stale) -- optimistic
        # concurrency, never a silent last-write-wins.
        session_id = client.post("/sessions", json={}).json()["id"]
        results: list[int] = []
        barrier = threading.Barrier(2)

        def _writer() -> None:
            barrier.wait()
            r = client.put(
                f"/sessions/{session_id}/graph",
                json={"graph": _seed_graph(), "expected_version": 0},
            )
            results.append(r.status_code)

        threads = [threading.Thread(target=_writer) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        assert sorted(results) == [200, 409]
        # The session settled at version 1 -- exactly one write landed.
        assert client.get(f"/sessions/{session_id}").json()["version"] == 1


class TestProposals:
    def test_propose_accept_lifecycle(self, client: TestClient) -> None:
        session_id = client.post("/sessions", json={"graph": _seed_graph()}).json()["id"]

        r = client.post(
            f"/sessions/{session_id}/proposals",
            json={"base_version": 0, "remove_nodes": ["n1"], "author": "agent-x"},
        )
        assert r.status_code == 200, r.text
        proposal = r.json()
        assert proposal["status"] == "pending"
        assert proposal["diagnostics"]["diagnostics"] == []
        proposal_id = proposal["id"]

        r = client.post(f"/sessions/{session_id}/proposals/{proposal_id}/accept")
        assert r.status_code == 200, r.text
        session = r.json()
        assert session["version"] == 1
        assert "n1" not in session["graph"]["nodes"]
        assert session["proposals"][proposal_id]["status"] == "accepted"

    def test_propose_reject_lifecycle(self, client: TestClient) -> None:
        session_id = client.post("/sessions", json={}).json()["id"]
        r = client.post(f"/sessions/{session_id}/proposals", json={"base_version": 0})
        proposal_id = r.json()["id"]

        r = client.post(f"/sessions/{session_id}/proposals/{proposal_id}/reject")
        assert r.status_code == 200, r.text
        session = r.json()
        # Rejecting must NOT bump the version.
        assert session["version"] == 0
        assert session["proposals"][proposal_id]["status"] == "rejected"

    def test_propose_against_moved_graph_rejected(self, client: TestClient) -> None:
        # A proposal computed against version 0, submitted AFTER the graph
        # moved to version 1 (via an accepted proposal), must be rejected
        # with a stale-version 409 -- never silently applied against the
        # wrong base.
        session_id = client.post("/sessions", json={"graph": _seed_graph()}).json()["id"]
        first = client.post(
            f"/sessions/{session_id}/proposals", json={"base_version": 0, "description": "first"}
        ).json()
        client.post(f"/sessions/{session_id}/proposals/{first['id']}/accept")
        assert client.get(f"/sessions/{session_id}").json()["version"] == 1

        r = client.post(
            f"/sessions/{session_id}/proposals",
            json={"base_version": 0, "description": "stale"},
        )
        assert r.status_code == 409, r.text

    def test_accept_already_rejected_proposal_409(self, client: TestClient) -> None:
        # A REJECTED proposal must never later be accepted -- its base_version
        # still matches the (unmoved) session version, so only an explicit
        # status check catches this; without it the "rejected" mutation would
        # silently apply.
        session_id = client.post("/sessions", json={"graph": _seed_graph()}).json()["id"]
        proposal_id = client.post(
            f"/sessions/{session_id}/proposals", json={"base_version": 0, "remove_nodes": ["n1"]}
        ).json()["id"]
        client.post(f"/sessions/{session_id}/proposals/{proposal_id}/reject")

        r = client.post(f"/sessions/{session_id}/proposals/{proposal_id}/accept")
        assert r.status_code == 409, r.text
        session = client.get(f"/sessions/{session_id}").json()
        assert session["version"] == 0
        assert "n1" in session["graph"]["nodes"]
        assert session["proposals"][proposal_id]["status"] == "rejected"

    def test_reject_already_accepted_proposal_409(self, client: TestClient) -> None:
        # An ACCEPTED proposal's mutation is already baked into the graph --
        # rejecting it afterward must not be allowed to flip its status back,
        # which would leave the session's proposal state contradicting its
        # own graph.
        session_id = client.post("/sessions", json={"graph": _seed_graph()}).json()["id"]
        proposal_id = client.post(
            f"/sessions/{session_id}/proposals", json={"base_version": 0, "remove_nodes": ["n1"]}
        ).json()["id"]
        client.post(f"/sessions/{session_id}/proposals/{proposal_id}/accept")

        r = client.post(f"/sessions/{session_id}/proposals/{proposal_id}/reject")
        assert r.status_code == 409, r.text
        session = client.get(f"/sessions/{session_id}").json()
        assert session["proposals"][proposal_id]["status"] == "accepted"

    def test_accept_unknown_proposal_404(self, client: TestClient) -> None:
        session_id = client.post("/sessions", json={}).json()["id"]
        r = client.post(f"/sessions/{session_id}/proposals/does-not-exist/accept")
        assert r.status_code == 404, r.text

    def test_reject_unknown_proposal_404(self, client: TestClient) -> None:
        session_id = client.post("/sessions", json={}).json()["id"]
        r = client.post(f"/sessions/{session_id}/proposals/does-not-exist/reject")
        assert r.status_code == 404, r.text

    def test_propose_unknown_session_404(self, client: TestClient) -> None:
        r = client.post("/sessions/does-not-exist/proposals", json={"base_version": 0})
        assert r.status_code == 404, r.text

    def test_propose_invalid_mutation_yields_diagnostics_not_error(
        self, client: TestClient
    ) -> None:
        # remove_nodes targeting a node that doesn't exist: apply_mutation
        # would raise MutationError, folded by propose_diagnostics into an
        # error diagnostic -- the proposal itself is still stored at 200, not
        # a 422/500.
        session_id = client.post("/sessions", json={}).json()["id"]
        r = client.post(
            f"/sessions/{session_id}/proposals",
            json={"base_version": 0, "remove_nodes": ["does-not-exist"]},
        )
        assert r.status_code == 200, r.text
        diagnostics = r.json()["diagnostics"]["diagnostics"]
        assert len(diagnostics) == 1
        assert diagnostics[0]["code"] == "mutation_error"


class TestSSEEvents:
    def test_unknown_session_events_404(self, client: TestClient) -> None:
        r = client.get("/sessions/does-not-exist/events")
        assert r.status_code == 404, r.text

    def test_events_observed_for_proposal_transitions(self, client: TestClient) -> None:
        session_id = client.post("/sessions", json={}).json()["id"]

        observed: list[dict] = []

        def _watch() -> None:
            # Subscribe directly through the SessionStore rather than over
            # HTTP SSE, because Starlette's TestClient event-loop executor
            # shuts down during cross-thread streaming and causes a
            # RuntimeError on run_in_executor -- the SSE route itself is
            # correct (tested manually), but this transport layer isn't
            # reliable under TestClient multi-threaded usage.
            store = session_mod.get_default_store()
            q = store.subscribe(session_id)
            try:
                while len(observed) < 2:
                    observed.append(q.get(timeout=5.0))
            finally:
                store.unsubscribe(session_id, q)

        # daemon=True: if this test ever legitimately fails (an event never
        # arrives), q.get(timeout=5.0) still raises queue.Empty and the thread
        # exits -- but daemon=True also ensures a genuinely stuck thread can
        # never block pytest's process exit, only this test's own assertion.
        watcher = threading.Thread(target=_watch, daemon=True)
        watcher.start()
        time.sleep(0.3)

        proposal_id = client.post(
            f"/sessions/{session_id}/proposals", json={"base_version": 0}
        ).json()["id"]
        client.post(f"/sessions/{session_id}/proposals/{proposal_id}/accept")

        watcher.join(timeout=5.0)
        assert not watcher.is_alive(), "SSE watcher did not observe both events in time"
        assert [e["type"] for e in observed] == ["proposal_added", "proposal_accepted"]


class TestSessionAuth:
    def test_auth_required_rejects_without_token(self, client: TestClient) -> None:
        configure_session_auth(required=True, token="secret")
        try:
            r = client.post("/sessions", json={})
            assert r.status_code == 401, r.text
        finally:
            configure_session_auth(required=False)

    def test_auth_required_accepts_correct_token(self, client: TestClient) -> None:
        configure_session_auth(required=True, token="secret")
        try:
            r = client.post("/sessions", json={}, headers={"Authorization": "Bearer secret"})
            assert r.status_code == 200, r.text
        finally:
            configure_session_auth(required=False)


def test_list_sessions_returns_every_active_session(client: TestClient) -> None:
    r1 = client.post("/sessions", json={})
    r2 = client.post("/sessions", json={})
    assert r1.status_code == 200
    assert r2.status_code == 200
    id1, id2 = r1.json()["id"], r2.json()["id"]

    resp = client.get("/sessions")

    assert resp.status_code == 200
    ids = {s["id"] for s in resp.json()["sessions"]}
    assert ids == {id1, id2}


def test_list_sessions_is_empty_when_no_sessions_exist(client: TestClient) -> None:
    resp = client.get("/sessions")

    assert resp.status_code == 200
    assert resp.json() == {"sessions": []}


def test_list_sessions_returns_full_session_documents(client: TestClient) -> None:
    created = client.post("/sessions", json={}).json()

    resp = client.get("/sessions")

    listed = resp.json()["sessions"][0]
    assert listed["version"] == created["version"]
    assert "graph" in listed
    assert "proposals" in listed


def test_list_sessions_requires_bearer_token_when_auth_is_required() -> None:
    from emergentflow.server.app import configure_session_auth

    configure_session_auth(required=True, token="secret")
    try:
        app = create_app()
        with TestClient(app) as auth_client:
            resp = auth_client.get("/sessions")
            assert resp.status_code == 401

            resp_ok = auth_client.get("/sessions", headers={"Authorization": "Bearer secret"})
            assert resp_ok.status_code == 200
    finally:
        configure_session_auth(required=False)


class TestSessionReviews:
    def test_create_review_with_anchored_finding(self, client: TestClient) -> None:
        session_id = client.post("/sessions", json={"graph": _seed_graph()}).json()["id"]

        r = client.post(
            f"/sessions/{session_id}/reviews",
            json={
                "author": "ml_engineer",
                "findings": [
                    {
                        "severity": "info",
                        "code": "grain_check",
                        "message": "looks fine",
                        "node_id": "n1",
                    }
                ],
            },
        )

        assert r.status_code == 200, r.text
        body = r.json()
        assert body["author"] == "ml_engineer"
        assert body["status"] == "open"
        assert len(body["findings"]) == 1

    def test_create_review_rejects_unanchored_finding(self, client: TestClient) -> None:
        session_id = client.post("/sessions", json={"graph": _seed_graph()}).json()["id"]

        r = client.post(
            f"/sessions/{session_id}/reviews",
            json={
                "author": "ml_engineer",
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

        assert r.status_code == 422, r.text
        assert r.json()["error"].startswith("anchor_error:")

    def test_create_review_unknown_session_404(self, client: TestClient) -> None:
        r = client.post("/sessions/does-not-exist/reviews", json={"author": "ml_engineer"})
        assert r.status_code == 404, r.text

    def test_list_reviews(self, client: TestClient) -> None:
        session_id = client.post("/sessions", json={"graph": _seed_graph()}).json()["id"]
        client.post(f"/sessions/{session_id}/reviews", json={"author": "a"})
        client.post(f"/sessions/{session_id}/reviews", json={"author": "b"})

        r = client.get(f"/sessions/{session_id}/reviews")

        assert r.status_code == 200, r.text
        authors = {t["author"] for t in r.json()["reviews"]}
        assert authors == {"a", "b"}

    def test_list_reviews_empty(self, client: TestClient) -> None:
        session_id = client.post("/sessions", json={}).json()["id"]

        r = client.get(f"/sessions/{session_id}/reviews")

        assert r.status_code == 200, r.text
        assert r.json() == {"reviews": []}

    def test_add_review_comment(self, client: TestClient) -> None:
        session_id = client.post("/sessions", json={"graph": _seed_graph()}).json()["id"]
        review_id = client.post(
            f"/sessions/{session_id}/reviews", json={"author": "ml_engineer"}
        ).json()["id"]

        r = client.post(
            f"/sessions/{session_id}/reviews/{review_id}/comments",
            json={"author": "human", "text": "thanks, fixing now"},
        )

        assert r.status_code == 200, r.text
        comments = r.json()["comments"]
        assert len(comments) == 1
        assert comments[0]["text"] == "thanks, fixing now"

    def test_add_review_comment_unknown_review_404(self, client: TestClient) -> None:
        session_id = client.post("/sessions", json={}).json()["id"]

        r = client.post(
            f"/sessions/{session_id}/reviews/does-not-exist/comments",
            json={"author": "human", "text": "hi"},
        )

        assert r.status_code == 404, r.text

    def test_review_events_observed(self, client: TestClient) -> None:
        session_id = client.post("/sessions", json={"graph": _seed_graph()}).json()["id"]

        observed: list[dict] = []

        def _watch() -> None:
            store = session_mod.get_default_store()
            q = store.subscribe(session_id)
            try:
                while len(observed) < 2:
                    observed.append(q.get(timeout=5.0))
            finally:
                store.unsubscribe(session_id, q)

        watcher = threading.Thread(target=_watch, daemon=True)
        watcher.start()
        time.sleep(0.3)

        review_id = client.post(
            f"/sessions/{session_id}/reviews", json={"author": "ml_engineer"}
        ).json()["id"]
        client.post(
            f"/sessions/{session_id}/reviews/{review_id}/comments",
            json={"author": "human", "text": "ok"},
        )

        watcher.join(timeout=5.0)
        assert not watcher.is_alive(), "SSE watcher did not observe both events in time"
        assert [e["type"] for e in observed] == ["review_added", "review_comment_added"]


class TestSessionGates:
    def test_create_gate(self, client: TestClient) -> None:
        session_id = client.post("/sessions", json={}).json()["id"]

        r = client.post(
            f"/sessions/{session_id}/gates",
            json={
                "phase": "train",
                "kind": "phase",
                "description": "training phase",
            },
        )

        assert r.status_code == 200, r.text
        body = r.json()
        assert body["phase"] == "train"
        assert body["kind"] == "phase"
        assert body["status"] == "open"

    def test_list_gates_empty(self, client: TestClient) -> None:
        session_id = client.post("/sessions", json={}).json()["id"]

        r = client.get(f"/sessions/{session_id}/gates")

        assert r.status_code == 200, r.text
        assert r.json() == {"gates": []}

    def test_list_gates(self, client: TestClient) -> None:
        session_id = client.post("/sessions", json={}).json()["id"]
        client.post(
            f"/sessions/{session_id}/gates",
            json={"phase": "a", "kind": "phase", "description": "first"},
        )
        client.post(
            f"/sessions/{session_id}/gates",
            json={"phase": "b", "kind": "confirm", "description": "second"},
        )

        r = client.get(f"/sessions/{session_id}/gates")

        assert r.status_code == 200, r.text
        phases = [g["phase"] for g in r.json()["gates"]]
        assert set(phases) == {"a", "b"}

    def test_create_gate_unknown_session_404(self, client: TestClient) -> None:
        r = client.post(
            "/sessions/does-not-exist/gates",
            json={"phase": "x", "kind": "phase", "description": "x"},
        )
        assert r.status_code == 404, r.text

    def test_close_gate(self, client: TestClient) -> None:
        session_id = client.post("/sessions", json={}).json()["id"]
        gate_id = client.post(
            f"/sessions/{session_id}/gates",
            json={"phase": "train", "kind": "phase", "description": "train"},
        ).json()["id"]

        r = client.post(f"/sessions/{session_id}/gates/{gate_id}/close")

        assert r.status_code == 200, r.text
        assert r.json()["status"] == "closed"

    def test_close_already_closed_gate_409(self, client: TestClient) -> None:
        session_id = client.post("/sessions", json={}).json()["id"]
        gate_id = client.post(
            f"/sessions/{session_id}/gates",
            json={"phase": "train", "kind": "phase", "description": "train"},
        ).json()["id"]
        client.post(f"/sessions/{session_id}/gates/{gate_id}/close")

        r = client.post(f"/sessions/{session_id}/gates/{gate_id}/close")

        assert r.status_code == 409, r.text
        assert "gate_already_resolved:" in r.json()["error"]

    def test_skip_gate(self, client: TestClient) -> None:
        session_id = client.post("/sessions", json={}).json()["id"]
        gate_id = client.post(
            f"/sessions/{session_id}/gates",
            json={"phase": "train", "kind": "phase", "description": "train"},
        ).json()["id"]

        r = client.post(f"/sessions/{session_id}/gates/{gate_id}/skip")

        assert r.status_code == 200, r.text
        assert r.json()["status"] == "skipped"

    def test_close_unknown_gate_404(self, client: TestClient) -> None:
        session_id = client.post("/sessions", json={}).json()["id"]
        r = client.post(f"/sessions/{session_id}/gates/does-not-exist/close")
        assert r.status_code == 404, r.text

    def test_skip_unknown_gate_404(self, client: TestClient) -> None:
        session_id = client.post("/sessions", json={}).json()["id"]
        r = client.post(f"/sessions/{session_id}/gates/does-not-exist/skip")
        assert r.status_code == 404, r.text

    def test_add_decision(self, client: TestClient) -> None:
        session_id = client.post("/sessions", json={}).json()["id"]
        gate_id = client.post(
            f"/sessions/{session_id}/gates",
            json={"phase": "train", "kind": "phase", "description": "train"},
        ).json()["id"]

        r = client.post(
            f"/sessions/{session_id}/gates/{gate_id}/decisions",
            json={"author": "human", "text": "proceed"},
        )

        assert r.status_code == 200, r.text
        assert len(r.json()["decisions"]) == 1
        assert r.json()["decisions"][0]["text"] == "proceed"

    def test_add_decision_unknown_gate_404(self, client: TestClient) -> None:
        session_id = client.post("/sessions", json={}).json()["id"]
        r = client.post(
            f"/sessions/{session_id}/gates/does-not-exist/decisions",
            json={"author": "human", "text": "hi"},
        )
        assert r.status_code == 404, r.text

    def test_session_compile_409_when_gate_open(self, client: TestClient) -> None:
        session_id = client.post("/sessions", json={"graph": _seed_graph()}).json()["id"]
        gate_id = client.post(
            f"/sessions/{session_id}/gates",
            json={"phase": "train", "kind": "phase", "description": "checkpoint"},
        ).json()["id"]

        r = client.post(f"/sessions/{session_id}/compile")

        assert r.status_code == 409, r.text
        assert "gates_open:" in r.json()["error"]
        assert gate_id in r.json()["error"]
        assert "train" in r.json()["error"]

    def test_session_execute_409_when_gate_open(self, client: TestClient) -> None:
        session_id = client.post("/sessions", json={"graph": _seed_graph()}).json()["id"]
        client.post(
            f"/sessions/{session_id}/gates",
            json={"phase": "train", "kind": "phase", "description": "checkpoint"},
        )

        r = client.post(f"/sessions/{session_id}/execute")

        assert r.status_code == 409, r.text
        assert "gates_open:" in r.json()["error"]

    def test_gated_session_compiles_after_gate_closed(self, client: TestClient) -> None:
        session_id = client.post("/sessions", json={"graph": _seed_graph()}).json()["id"]
        gate_id = client.post(
            f"/sessions/{session_id}/gates",
            json={"phase": "review", "kind": "confirm", "description": "review step"},
        ).json()["id"]

        r_blocked = client.post(f"/sessions/{session_id}/compile")
        assert r_blocked.status_code == 409

        client.post(f"/sessions/{session_id}/gates/{gate_id}/close")
        r_ok = client.post(f"/sessions/{session_id}/compile")

        assert r_ok.status_code == 200, r_ok.text
        assert "code" in r_ok.json()

    def test_skip_clears_block_for_compile(self, client: TestClient) -> None:
        session_id = client.post("/sessions", json={"graph": _seed_graph()}).json()["id"]
        gate_id = client.post(
            f"/sessions/{session_id}/gates",
            json={"phase": "review", "kind": "confirm", "description": "review step"},
        ).json()["id"]

        client.post(f"/sessions/{session_id}/gates/{gate_id}/skip")
        r = client.post(f"/sessions/{session_id}/compile")

        assert r.status_code == 200, r.text

    def test_two_open_gates_both_named_in_409(self, client: TestClient) -> None:
        session_id = client.post("/sessions", json={"graph": _seed_graph()}).json()["id"]
        g1 = client.post(
            f"/sessions/{session_id}/gates",
            json={"phase": "p1", "kind": "phase", "description": "first"},
        ).json()
        g2 = client.post(
            f"/sessions/{session_id}/gates",
            json={"phase": "p2", "kind": "confirm", "description": "second"},
        ).json()

        r = client.post(f"/sessions/{session_id}/compile")

        assert r.status_code == 409, r.text
        error = r.json()["error"]
        assert g1["id"] in error
        assert g2["id"] in error
        assert "2 open gate(s)" in error

    def test_payload_only_compile_unaffected_by_gates(self, client: TestClient) -> None:
        session_id = client.post("/sessions", json={"graph": _seed_graph()}).json()["id"]
        client.post(
            f"/sessions/{session_id}/gates",
            json={"phase": "blocking", "kind": "phase", "description": "blocking gate"},
        )

        r = client.post("/compile", json=_seed_graph())

        assert r.status_code == 200, r.text
        assert "code" in r.json()

    def test_session_compile_unknown_session_404(self, client: TestClient) -> None:
        r = client.post("/sessions/does-not-exist/compile")
        assert r.status_code == 404, r.text

    def test_session_execute_unknown_session_404(self, client: TestClient) -> None:
        r = client.post("/sessions/does-not-exist/execute")
        assert r.status_code == 404, r.text

    def test_gate_events_observed(self, client: TestClient) -> None:
        session_id = client.post("/sessions", json={}).json()["id"]

        observed: list[dict] = []

        def _watch() -> None:
            store = session_mod.get_default_store()
            q = store.subscribe(session_id)
            try:
                while len(observed) < 3:
                    observed.append(q.get(timeout=5.0))
            finally:
                store.unsubscribe(session_id, q)

        watcher = threading.Thread(target=_watch, daemon=True)
        watcher.start()
        time.sleep(0.3)

        gate_id = client.post(
            f"/sessions/{session_id}/gates",
            json={"phase": "train", "kind": "phase", "description": "train"},
        ).json()["id"]
        client.post(
            f"/sessions/{session_id}/gates/{gate_id}/decisions",
            json={"author": "human", "text": "proceed"},
        )
        client.post(f"/sessions/{session_id}/gates/{gate_id}/close")

        watcher.join(timeout=5.0)
        assert not watcher.is_alive(), "SSE watcher did not observe all events in time"
        assert [e["type"] for e in observed] == [
            "gate_opened",
            "decision_added",
            "gate_closed",
        ]


_FAKE_HAPPY_CHAT_SCRIPT = "import json\nprint(json.dumps({'type': 'text', 'text': 'All set.'}))\n"

_FAKE_SLOW_CHAT_SCRIPT = "import time\ntime.sleep(30)\n"


class _FakeHttpChatAdapter(AgentAdapter):
    """Base for test-only adapters: spawns `python -c <SCRIPT>` and parses simple
    `{"type": ..., "text": ...}` JSON lines directly into an AdapterEvent."""

    cli_executable = sys.executable
    SCRIPT = ""

    def build_command(self, *, prompt: str, resume_id: str | None) -> list[str]:
        return [sys.executable, "-c", self.SCRIPT]

    def parse_line(self, raw_line: str) -> AdapterEvent | None:
        line = raw_line.strip()
        if not line:
            return None
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            return None
        return AdapterEvent(kind=data["type"], text=data["text"])


@register_adapter
class _HappyHttpChatAdapter(_FakeHttpChatAdapter):
    name = "fake-http-chat-happy"
    SCRIPT = _FAKE_HAPPY_CHAT_SCRIPT


@register_adapter
class _SlowHttpChatAdapter(_FakeHttpChatAdapter):
    name = "fake-http-chat-slow"
    SCRIPT = _FAKE_SLOW_CHAT_SCRIPT


def _wait_for_chat_status(
    client: TestClient, session_id: str, turn_id: str, timeout: float = 5.0
) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        session = client.get(f"/sessions/{session_id}").json()
        turn = next(t for t in session["collab"]["chat"]["turns"] if t["id"] == turn_id)
        if turn["status"] != "running":
            return turn
        time.sleep(0.05)
    raise TimeoutError(f"turn {turn_id} did not resolve within {timeout}s")


class TestSessionChat:
    def test_start_chat_requires_backend_field(self, client: TestClient) -> None:
        session_id = client.post("/sessions", json={}).json()["id"]
        r = client.post(f"/sessions/{session_id}/chat", json={"message": "hi"})
        assert r.status_code == 400, r.text

    def test_start_chat_requires_message_field(self, client: TestClient) -> None:
        session_id = client.post("/sessions", json={}).json()["id"]
        r = client.post(f"/sessions/{session_id}/chat", json={"backend": "fake-http-chat-happy"})
        assert r.status_code == 400, r.text

    def test_start_chat_unknown_session_404(self, client: TestClient) -> None:
        r = client.post(
            "/sessions/does-not-exist/chat",
            json={"backend": "fake-http-chat-happy", "message": "hi"},
        )
        assert r.status_code == 404, r.text

    def test_start_chat_unavailable_backend_422(self, client: TestClient) -> None:
        session_id = client.post("/sessions", json={}).json()["id"]
        r = client.post(
            f"/sessions/{session_id}/chat",
            json={"backend": "no-such-backend", "message": "hi"},
        )
        assert r.status_code == 422, r.text

    def test_start_chat_happy_path_completes(self, client: TestClient) -> None:
        session_id = client.post("/sessions", json={}).json()["id"]
        r = client.post(
            f"/sessions/{session_id}/chat",
            json={"backend": "fake-http-chat-happy", "message": "hello"},
        )
        assert r.status_code == 200, r.text
        turn_id = r.json()["id"]
        assert r.json()["status"] == "running"

        turn = _wait_for_chat_status(client, session_id, turn_id)
        assert turn["status"] == "completed"
        assert turn["agent_message"] == "All set."

        session = client.get(f"/sessions/{session_id}").json()
        assert session["collab"]["chat"]["backend"] == "fake-http-chat-happy"

    def test_starting_a_second_chat_while_first_is_running_returns_409(
        self, client: TestClient
    ) -> None:
        session_id = client.post("/sessions", json={}).json()["id"]
        client.post(
            f"/sessions/{session_id}/chat",
            json={"backend": "fake-http-chat-slow", "message": "hi"},
        )
        r = client.post(
            f"/sessions/{session_id}/chat",
            json={"backend": "fake-http-chat-slow", "message": "again"},
        )
        assert r.status_code == 409, r.text
        # Cleanup: stop the slow turn so its subprocess doesn't linger past the test.
        turn_id = client.get(f"/sessions/{session_id}").json()["collab"]["chat"]["turns"][0]["id"]
        client.post(f"/sessions/{session_id}/chat/{turn_id}/stop")

    def test_stop_chat_interrupts_running_turn(self, client: TestClient) -> None:
        session_id = client.post("/sessions", json={}).json()["id"]
        r = client.post(
            f"/sessions/{session_id}/chat",
            json={"backend": "fake-http-chat-slow", "message": "hi"},
        )
        turn_id = r.json()["id"]
        time.sleep(0.1)

        stop_response = client.post(f"/sessions/{session_id}/chat/{turn_id}/stop")
        assert stop_response.status_code == 200, stop_response.text
        assert stop_response.json()["status"] == "interrupted"

    def test_stop_chat_unknown_turn_404(self, client: TestClient) -> None:
        session_id = client.post("/sessions", json={}).json()["id"]
        r = client.post(f"/sessions/{session_id}/chat/no-such-turn/stop")
        assert r.status_code == 404, r.text

    def test_end_chat_clears_backend(self, client: TestClient) -> None:
        session_id = client.post("/sessions", json={}).json()["id"]
        r = client.post(
            f"/sessions/{session_id}/chat",
            json={"backend": "fake-http-chat-happy", "message": "hello"},
        )
        turn_id = r.json()["id"]
        _wait_for_chat_status(client, session_id, turn_id)

        end_response = client.post(f"/sessions/{session_id}/chat/end")
        assert end_response.status_code == 200, end_response.text
        assert end_response.json()["collab"]["chat"]["backend"] is None

    def test_list_agents_includes_fake_test_backends(self, client: TestClient) -> None:
        r = client.get("/agents")
        assert r.status_code == 200, r.text
        assert "fake-http-chat-happy" in r.json()["agents"]
