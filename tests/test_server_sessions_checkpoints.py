"""
tests/test_server_sessions_checkpoints.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Epic 14, Story 10 -- HTTP routes for direct apply & checkpoints over the
``/sessions/*`` API: ``POST .../apply``, ``POST .../checkpoints/{id}/revert``,
and ``GET .../checkpoints``. Mirrors tests/test_server_sessions.py's structure
and conventions (the "agent" is the HTTP client; no LLM anywhere).
"""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from emergentflow.collab import session as session_mod
from emergentflow.server.app import configure_session_auth, create_app


@pytest.fixture(autouse=True)
def _fresh_session_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate the process-wide default SessionStore per test and reset the
    auth gate to its default (disabled) so tests never interfere with each
    other's auth state.
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


def _add_nodes_mutation(base_version: int = 0) -> dict:
    return {"base_version": base_version, "add_nodes": [LOAD_CSV_NODE]}


class TestApplyDirectMutation:
    def test_apply_direct_mutation(self, client: TestClient) -> None:
        session_id = client.post("/sessions", json={}).json()["id"]

        observed: list[dict] = []

        def _watch() -> None:
            store = session_mod.get_default_store()
            q = store.subscribe(session_id)
            try:
                observed.append(q.get(timeout=5.0))
            finally:
                store.unsubscribe(session_id, q)

        watcher = threading.Thread(target=_watch, daemon=True)
        watcher.start()
        time.sleep(0.3)

        r = client.post(
            f"/sessions/{session_id}/apply",
            json={
                "mutation": _add_nodes_mutation(),
                "author": "agent-x",
                "reason": "add a csv node",
            },
        )

        assert r.status_code == 200, r.text
        session = r.json()
        assert session["version"] == 1
        assert "n1" in session["graph"]["nodes"]
        checkpoints = session["collab"]["checkpoints"]
        assert len(checkpoints) == 1
        cp = next(iter(checkpoints.values()))
        assert cp["kind"] == "edit"
        assert cp["author"] == "agent-x"
        assert cp["description"] == "add a csv node"

        watcher.join(timeout=5.0)
        assert not watcher.is_alive(), "SSE watcher did not observe graph_changed in time"
        assert observed[0]["type"] == "graph_changed"
        assert observed[0]["version"] == 1

    def test_apply_direct_mutation_stale_version(self, client: TestClient) -> None:
        session_id = client.post("/sessions", json={}).json()["id"]
        client.post(f"/sessions/{session_id}/apply", json={"mutation": _add_nodes_mutation()})

        r = client.post(
            f"/sessions/{session_id}/apply",
            json={"mutation": _add_nodes_mutation(base_version=0)},
        )

        assert r.status_code == 409, r.text
        assert "stale_version:" in r.json()["error"]

    def test_apply_direct_mutation_unknown_session_404(self, client: TestClient) -> None:
        r = client.post("/sessions/does-not-exist/apply", json={"mutation": _add_nodes_mutation()})
        assert r.status_code == 404, r.text

    def test_apply_direct_mutation_invalid_body_400(self, client: TestClient) -> None:
        session_id = client.post("/sessions", json={}).json()["id"]
        r = client.post(
            f"/sessions/{session_id}/apply",
            content="{not-json",
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 400, r.text


class TestRevertCheckpoint:
    def test_revert_checkpoint(self, client: TestClient) -> None:
        session_id = client.post("/sessions", json={}).json()["id"]
        applied = client.post(
            f"/sessions/{session_id}/apply", json={"mutation": _add_nodes_mutation()}
        ).json()
        checkpoint_id = next(iter(applied["collab"]["checkpoints"]))
        assert "n1" in applied["graph"]["nodes"]

        r = client.post(f"/sessions/{session_id}/checkpoints/{checkpoint_id}/revert")

        assert r.status_code == 200, r.text
        session = r.json()
        assert session["version"] == 2
        assert "n1" not in session["graph"]["nodes"]
        kinds = [cp["kind"] for cp in session["collab"]["checkpoints"].values()]
        assert kinds == ["edit", "revert"]

    def test_revert_checkpoint_unknown(self, client: TestClient) -> None:
        session_id = client.post("/sessions", json={}).json()["id"]
        r = client.post(f"/sessions/{session_id}/checkpoints/does-not-exist/revert")
        assert r.status_code == 404, r.text

    def test_revert_checkpoint_unknown_session_404(self, client: TestClient) -> None:
        r = client.post("/sessions/does-not-exist/checkpoints/x/revert")
        assert r.status_code == 404, r.text


class TestListCheckpoints:
    def test_list_checkpoints(self, client: TestClient) -> None:
        session_id = client.post("/sessions", json={}).json()["id"]
        client.post(f"/sessions/{session_id}/apply", json={"mutation": _add_nodes_mutation()})

        r = client.get(f"/sessions/{session_id}/checkpoints")

        assert r.status_code == 200, r.text
        checkpoints = r.json()["checkpoints"]
        assert len(checkpoints) == 1
        assert checkpoints[0]["kind"] == "edit"
        assert "previous_graph" not in checkpoints[0]

    def test_list_checkpoints_empty(self, client: TestClient) -> None:
        session_id = client.post("/sessions", json={}).json()["id"]
        r = client.get(f"/sessions/{session_id}/checkpoints")
        assert r.status_code == 200, r.text
        assert r.json() == {"checkpoints": []}

    def test_list_checkpoints_unknown_session_404(self, client: TestClient) -> None:
        r = client.get("/sessions/does-not-exist/checkpoints")
        assert r.status_code == 404, r.text


class TestCheckpointAuth:
    def test_routes_require_bearer_token_when_auth_is_required(self) -> None:
        configure_session_auth(required=True, token="secret")
        try:
            app = create_app()
            with TestClient(app) as auth_client:
                session_id = auth_client.post(
                    "/sessions", headers={"Authorization": "Bearer secret"}
                ).json()["id"]

                for method, path, body in [
                    ("post", f"/sessions/{session_id}/apply", {"mutation": {"base_version": 0}}),
                    ("post", f"/sessions/{session_id}/checkpoints/x/revert", {}),
                    ("get", f"/sessions/{session_id}/checkpoints", None),
                ]:
                    kwargs: dict[str, Any] = {}
                    if body is not None:
                        kwargs["json"] = body
                    resp = getattr(auth_client, method)(path, **kwargs)
                    assert resp.status_code == 401, (method, path, resp.text)

                    resp_ok = getattr(auth_client, method)(
                        path, headers={"Authorization": "Bearer secret"}, **kwargs
                    )
                    assert resp_ok.status_code in (200, 404), (method, path, resp_ok.text)
        finally:
            configure_session_auth(required=False)
