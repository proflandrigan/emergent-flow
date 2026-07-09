"""
tests/test_server_sessions.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Epic 14, Story 3 — graph sessions on the server: full HTTP lifecycle over the
ASGI test client. The "agent" in every test here is literally the HTTP client
-- no LLM anywhere, proving Mode A collaboration needs nothing more than an
HTTP client that speaks this surface.
"""

from __future__ import annotations

import threading
import time

import pytest
from fastapi.testclient import TestClient

from emergentflow.collab import session as session_mod
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
