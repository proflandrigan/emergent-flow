"""
tests/test_server_sessions_tours.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
REST routes ``/sessions/{id}/tours`` (guided tours, issue #171) over the ASGI test client.
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


def _node(node_id: str) -> dict[str, Any]:
    return {
        "id": node_id,
        "type": "data.load_csv",
        "label": node_id,
        "paradigm": "functional",
        "params": [{"name": "path", "type_token": "str", "value": "a.csv", "default": None}],
        "ports": [
            {
                "id": f"{node_id}_p",
                "name": "frame",
                "direction": "out",
                "data_type": "DataFrame",
                "cardinality": "one",
            }
        ],
        "position": {"x": 0.0, "y": 0.0},
        "group_id": None,
    }


def _new_session(client: TestClient) -> str:
    graph = {"nodes": {"n1": _node("n1"), "n2": _node("n2")}, "edges": {}}
    r = client.post("/sessions", json={"graph": graph})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _tour(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "title": "Tour",
        "conclusion": "Done.",
        "author": "agent",
        "steps": [{"focus": ["n1"], "note": "first"}, {"route": ["n1", "n2"], "note": "second"}],
    }
    body.update(overrides)
    return body


class TestTourRoutes:
    def test_create_list_and_duplicate(self, client: TestClient) -> None:
        sid = _new_session(client)
        r = client.post(f"/sessions/{sid}/tours", json=_tour())
        assert r.status_code == 200, r.text
        tour_id = r.json()["id"]
        assert tour_id

        listed = client.get(f"/sessions/{sid}/tours")
        assert listed.status_code == 200
        assert [t["id"] for t in listed.json()["tours"]] == [tour_id]

        dup = client.post(f"/sessions/{sid}/tours", json=_tour(id=tour_id))
        assert dup.status_code == 409, dup.text
        assert dup.json()["error"].startswith("duplicate_tour:")

    def test_missing_anchors_reported(self, client: TestClient) -> None:
        sid = _new_session(client)
        steps = [
            {"focus": ["nope1"], "note": "a"},
            {"focus": ["n1"], "note": "b"},
            {"focus": ["nope2"], "note": "c"},
        ]
        r = client.post(f"/sessions/{sid}/tours", json=_tour(steps=steps))
        assert r.status_code == 422, r.text
        body = r.json()
        assert body["error"].startswith("anchor_error:")
        assert body["missing"] == [
            {"step": 0, "node_id": "nope1"},
            {"step": 2, "node_id": "nope2"},
        ]
        assert client.get(f"/sessions/{sid}/tours").json()["tours"] == []

    def test_invalid_bodies(self, client: TestClient) -> None:
        sid = _new_session(client)
        bad_shape = _tour(steps=[{"route": ["n1", "n2"], "focus": ["n1"], "note": "x"}])
        assert client.post(f"/sessions/{sid}/tours", json=bad_shape).status_code == 422
        malformed = client.post(
            f"/sessions/{sid}/tours",
            content=b"{not json",
            headers={"Content-Type": "application/json"},
        )
        assert malformed.status_code == 400
        assert client.post(f"/sessions/{sid}/tours", json=[]).status_code == 400
        assert client.put(f"/sessions/{sid}/tours/x", json=[]).status_code == 400

    def test_put_replace_unknown_and_mismatch(self, client: TestClient) -> None:
        sid = _new_session(client)
        tour_id = client.post(f"/sessions/{sid}/tours", json=_tour()).json()["id"]

        r = client.put(f"/sessions/{sid}/tours/{tour_id}", json=_tour(title="Renamed"))
        assert r.status_code == 200, r.text
        assert r.json()["title"] == "Renamed"
        assert r.json()["id"] == tour_id

        assert client.put(f"/sessions/{sid}/tours/ghost", json=_tour()).status_code == 404

        mismatch = client.put(f"/sessions/{sid}/tours/{tour_id}", json=_tour(id="other"))
        assert mismatch.status_code == 422
        assert "tour id mismatch" in mismatch.json()["error"]

    def test_delete(self, client: TestClient) -> None:
        sid = _new_session(client)
        tour_id = client.post(f"/sessions/{sid}/tours", json=_tour()).json()["id"]
        r = client.delete(f"/sessions/{sid}/tours/{tour_id}")
        assert r.status_code == 200
        assert r.json() == {"deleted": tour_id}
        assert client.delete(f"/sessions/{sid}/tours/{tour_id}").status_code == 404

    def test_unknown_session(self, client: TestClient) -> None:
        assert client.get("/sessions/nope/tours").status_code == 404
        assert client.post("/sessions/nope/tours", json=_tour()).status_code == 404
        assert client.put("/sessions/nope/tours/t", json=_tour()).status_code == 404
        assert client.delete("/sessions/nope/tours/t").status_code == 404

    def test_list_sorted_by_id(self, client: TestClient) -> None:
        sid = _new_session(client)
        for tid in ("c", "a", "b"):
            assert client.post(f"/sessions/{sid}/tours", json=_tour(id=tid)).status_code == 200
        ids = [t["id"] for t in client.get(f"/sessions/{sid}/tours").json()["tours"]]
        assert ids == ["a", "b", "c"]

    def test_auth_required_on_all_routes(self, client: TestClient) -> None:
        sid = _new_session(client)
        client.post(f"/sessions/{sid}/tours", json=_tour(id="t1"))
        auth = {"Authorization": "Bearer secret"}
        configure_session_auth(required=True, token="secret")
        try:
            base = f"/sessions/{sid}/tours"
            calls = [
                ("get", base, None),
                ("post", base, _tour(id="t2")),
                ("put", f"{base}/t1", _tour(title="New")),
                ("delete", f"{base}/t1", None),
            ]
            for method, url, body in calls:
                kwargs: dict[str, Any] = {} if body is None else {"json": body}
                assert getattr(client, method)(url, **kwargs).status_code == 401, (method, url)
            for method, url, body in calls:
                kwargs = {} if body is None else {"json": body}
                r = getattr(client, method)(url, headers=auth, **kwargs)
                assert r.status_code == 200, (method, url, r.text)
        finally:
            configure_session_auth(required=False)

    def test_graph_and_version_unchanged(self, client: TestClient) -> None:
        sid = _new_session(client)
        before = client.get(f"/sessions/{sid}").json()
        tour_id = client.post(f"/sessions/{sid}/tours", json=_tour()).json()["id"]
        client.put(f"/sessions/{sid}/tours/{tour_id}", json=_tour(title="Again"))
        client.delete(f"/sessions/{sid}/tours/{tour_id}")
        after = client.get(f"/sessions/{sid}").json()
        assert after["graph"] == before["graph"]
        assert after["version"] == before["version"]


def test_slash_id_rejected_so_every_stored_tour_stays_deletable(client: TestClient) -> None:
    # A "/" id would be stored but unreachable by PUT/DELETE (405) once Starlette decodes %2F.
    sid = _new_session(client)
    r = client.post(f"/sessions/{sid}/tours", json=_tour(id="a/b"))
    assert r.status_code == 422, r.text
    assert client.get(f"/sessions/{sid}/tours").json()["tours"] == []
