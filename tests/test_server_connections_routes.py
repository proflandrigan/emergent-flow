"""Tests for connection profile CRUD routes (Task 03)."""

from __future__ import annotations

import tomllib
from pathlib import Path

from fastapi.testclient import TestClient

from emergentflow.server import app


def _test_client(connections_path: Path, monkeypatch) -> TestClient:
    monkeypatch.setenv("EMERGENTFLOW_CONNECTIONS", str(connections_path))
    return TestClient(app)


def test_get_connections_empty(tmp_path, monkeypatch) -> None:
    client = _test_client(tmp_path / "connections.toml", monkeypatch)
    resp = client.get("/connections")
    assert resp.status_code == 200
    assert resp.json() == {"connections": []}


def test_post_warehouse_creates(tmp_path, monkeypatch) -> None:
    client = _test_client(tmp_path / "connections.toml", monkeypatch)
    body = {"name": "my_pg", "dialect": "postgres", "kind": "warehouse"}
    resp = client.post("/connections", json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["kind"] == "warehouse"
    assert data["name"] == "my_pg"
    assert data["dialect"] == "postgres"

    get_resp = client.get("/connections")
    names = [c["name"] for c in get_resp.json()["connections"]]
    assert "my_pg" in names


def test_post_llm_creates(tmp_path, monkeypatch) -> None:
    client = _test_client(tmp_path / "connections.toml", monkeypatch)
    body = {
        "name": "my_llm",
        "kind": "llm",
        "provider": "openai",
        "api_key_env": "OPENAI_API_KEY",
    }
    resp = client.post("/connections", json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["kind"] == "llm"
    assert data["provider"] == "openai"
    assert data["api_key_env"] == "OPENAI_API_KEY"

    client.post(
        "/connections",
        json={"name": "my_pg", "dialect": "duckdb", "kind": "warehouse"},
    )
    get_resp = client.get("/connections")
    conns = get_resp.json()["connections"]
    kinds = {c["name"]: c["kind"] for c in conns}
    assert kinds["my_llm"] == "llm"
    assert kinds["my_pg"] == "warehouse"


def test_post_duplicate_name_is_422(tmp_path, monkeypatch) -> None:
    client = _test_client(tmp_path / "connections.toml", monkeypatch)
    body = {"name": "dup", "dialect": "duckdb"}
    resp1 = client.post("/connections", json=body)
    assert resp1.status_code == 200
    resp2 = client.post("/connections", json=body)
    assert resp2.status_code == 422
    assert "already exists" in resp2.json()["error"]


def test_put_updates_field(tmp_path, monkeypatch) -> None:
    client = _test_client(tmp_path / "connections.toml", monkeypatch)
    client.post(
        "/connections",
        json={"name": "pg1", "dialect": "postgres", "kind": "warehouse"},
    )
    resp = client.put(
        "/connections/pg1",
        json={"dialect": "duckdb", "kind": "warehouse"},
    )
    assert resp.status_code == 200
    assert resp.json()["dialect"] == "duckdb"

    get_resp = client.get("/connections")
    pg1 = next(c for c in get_resp.json()["connections"] if c["name"] == "pg1")
    assert pg1["dialect"] == "duckdb"


def test_put_omits_kind_keeps_existing(tmp_path, monkeypatch) -> None:
    client = _test_client(tmp_path / "connections.toml", monkeypatch)
    client.post(
        "/connections",
        json={
            "name": "my_llm",
            "kind": "llm",
            "provider": "anthropic",
            "api_key_env": "ANTHROPIC_API_KEY",
        },
    )
    resp = client.put(
        "/connections/my_llm",
        json={"provider": "openai", "api_key_env": "NEW_ENV"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["kind"] == "llm"
    assert data["provider"] == "openai"
    assert data["api_key_env"] == "NEW_ENV"


def test_put_unknown_name_is_404(tmp_path, monkeypatch) -> None:
    client = _test_client(tmp_path / "connections.toml", monkeypatch)
    resp = client.put(
        "/connections/nonexistent",
        json={"dialect": "duckdb"},
    )
    assert resp.status_code == 404
    assert "No connection profile" in resp.json()["error"]


def test_delete_removes(tmp_path, monkeypatch) -> None:
    client = _test_client(tmp_path / "connections.toml", monkeypatch)
    client.post("/connections", json={"name": "del_me", "dialect": "duckdb"})
    resp = client.delete("/connections/del_me")
    assert resp.status_code == 200
    assert resp.json() == {"deleted": "del_me"}

    get_resp = client.get("/connections")
    assert get_resp.json() == {"connections": []}


def test_delete_unknown_name_is_404(tmp_path, monkeypatch) -> None:
    client = _test_client(tmp_path / "connections.toml", monkeypatch)
    resp = client.delete("/connections/ghost")
    assert resp.status_code == 404
    assert "No connection profile" in resp.json()["error"]


def test_test_route_rejects_llm_profile_with_clear_message(tmp_path, monkeypatch) -> None:
    client = _test_client(tmp_path / "connections.toml", monkeypatch)
    client.post(
        "/connections",
        json={"name": "my_llm", "kind": "llm", "provider": "openai", "api_key_env": "OPENAI_API_KEY"},
    )
    resp = client.post("/connections/my_llm/test")
    assert resp.status_code == 422
    assert "not a warehouse profile" in resp.json()["error"]



def test_persistence_on_disk(tmp_path, monkeypatch) -> None:
    toml_path = tmp_path / "connections.toml"
    client = _test_client(toml_path, monkeypatch)
    client.post(
        "/connections",
        json={"name": "persist_me", "dialect": "duckdb", "kind": "warehouse"},
    )
    client.put(
        "/connections/persist_me",
        json={"dialect": "postgres"},
    )

    assert toml_path.exists()
    with toml_path.open("rb") as fh:
        raw = tomllib.load(fh)
    assert "persist_me" in raw
    assert raw["persist_me"]["dialect"] == "postgres"

    client.delete("/connections/persist_me")
    with toml_path.open("rb") as fh:
        raw = tomllib.load(fh)
    assert "persist_me" not in raw
