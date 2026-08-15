"""Tests for warehouse-provisioned server routes (Epic 13 Story 10)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from emergentflow.server import app

_SPEC = {
    "source": "sales",
    "select": ["region"],
    "group_by": ["region"],
}


def test_connections_empty_on_fresh_install(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("EMERGENTFLOW_CONNECTIONS", str(tmp_path / "connections.toml"))
    with TestClient(app) as test_client:
        resp = test_client.get("/connections")
    assert resp.status_code == 200
    assert resp.json() == {"connections": []}


def test_compile_spec_returns_sql() -> None:
    with TestClient(app) as test_client:
        resp = test_client.post("/compile-spec", json={"spec": _SPEC, "dialect": "duckdb"})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["sql"], str)
    assert len(data["sql"]) > 0


def test_compile_spec_missing_dialect_is_422() -> None:
    with TestClient(app) as test_client:
        resp = test_client.post("/compile-spec", json={"spec": _SPEC})
    assert resp.status_code == 422
    assert "error" in resp.json()


def test_test_connection_unknown_profile_is_404(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("EMERGENTFLOW_CONNECTIONS", str(tmp_path / "connections.toml"))
    with TestClient(app) as test_client:
        resp = test_client.post("/connections/does_not_exist/test")
    assert resp.status_code == 404
    assert "error" in resp.json()
