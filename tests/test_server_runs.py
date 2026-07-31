"""Tests for the RunStore, run routes, and CLI run command."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from emergentflow.server.app import app
from emergentflow.server.runs import (
    RunStore,
    UnknownRunError,
    configure_runs,
    get_default_runs,
)

# ---------------------------------------------------------------------------
# RunStore unit tests
# ---------------------------------------------------------------------------


def test_save_and_get_round_trips(tmp_path: Path) -> None:
    store = RunStore(root=tmp_path, keep=50)
    run_data = {
        "run_id": "",
        "tag": "baseline",
        "graph_name": "Test Flow",
        "graph_hash": "abc123",
        "started_at": time.time(),
        "finished_at": time.time(),
        "duration_ms": 100,
        "node_count": 3,
        "statuses": {"n1": {"status": "ok", "elapsed_ms": 50}},
        "reproducibility": {"seeds": {}, "content_hashes": {}, "dependency_versions": {}},
        "sdk_version": "0.3.3",
    }
    graph_data = {"name": "Test Flow", "nodes": {}, "edges": {}}
    payloads_data = {}
    run_id = store.save(run_data, graph_data, payloads_data)

    result = store.get(run_id)
    assert result["run_id"] == run_id
    assert result["tag"] == "baseline"
    assert result["node_count"] == 3


def test_get_graph_returns_graph_json(tmp_path: Path) -> None:
    store = RunStore(root=tmp_path, keep=50)
    run_data = {
        "run_id": "",
        "tag": None,
        "graph_name": "",
        "graph_hash": "def456",
        "started_at": time.time(),
        "finished_at": time.time(),
        "duration_ms": 0,
        "node_count": 0,
        "statuses": {},
        "reproducibility": {"seeds": {}, "content_hashes": {}, "dependency_versions": {}},
        "sdk_version": "0.3.3",
    }
    graph_data = {"name": "Graph", "nodes": {"n1": {"type": "test"}}, "edges": {}}
    payloads_data = {}
    run_id = store.save(run_data, graph_data, payloads_data)

    result = store.get_graph(run_id)
    assert result["name"] == "Graph"
    assert "n1" in result["nodes"]


_VALID_RUN_ID = "2024-01-01T00-00-00Z-0000"


def test_get_unknown_raises(tmp_path: Path) -> None:
    store = RunStore(root=tmp_path, keep=50)
    with pytest.raises(UnknownRunError):
        store.get(_VALID_RUN_ID)


def test_get_graph_unknown_raises(tmp_path: Path) -> None:
    store = RunStore(root=tmp_path, keep=50)
    with pytest.raises(UnknownRunError):
        store.get_graph(_VALID_RUN_ID)


def test_delete_removes_entry(tmp_path: Path) -> None:
    store = RunStore(root=tmp_path, keep=50)
    run_data = {
        "run_id": "",
        "tag": None,
        "graph_name": "",
        "graph_hash": "",
        "started_at": time.time(),
        "finished_at": time.time(),
        "duration_ms": 0,
        "node_count": 0,
        "statuses": {},
        "reproducibility": {"seeds": {}, "content_hashes": {}, "dependency_versions": {}},
        "sdk_version": "0.3.3",
    }
    run_id = store.save(run_data, {}, {})
    store.delete(run_id)
    with pytest.raises(UnknownRunError):
        store.get(run_id)


def test_delete_unknown_raises(tmp_path: Path) -> None:
    store = RunStore(root=tmp_path, keep=50)
    with pytest.raises(UnknownRunError):
        store.delete(_VALID_RUN_ID)


def test_list_returns_entries_sorted_newest_first(tmp_path: Path) -> None:
    store = RunStore(root=tmp_path, keep=50)
    base = {
        "run_id": "",
        "tag": None,
        "graph_name": "",
        "graph_hash": "",
        "duration_ms": 0,
        "node_count": 0,
        "statuses": {},
        "reproducibility": {"seeds": {}, "content_hashes": {}, "dependency_versions": {}},
        "sdk_version": "0.3.3",
    }
    run_ids = []
    for i in range(3):
        data = {**base, "started_at": float(100 + i), "finished_at": float(100 + i)}
        run_id = store.save(data, {}, {})
        run_ids.append(run_id)

    result = store.list()
    assert len(result) == 3
    # Should be newest-first (last saved = run-2, run-1, run-0)
    assert result[0]["run_id"] == run_ids[-1]


def test_eviction_removes_oldest(tmp_path: Path) -> None:
    store = RunStore(root=tmp_path, keep=2)
    base = {
        "run_id": "",
        "tag": None,
        "graph_name": "",
        "graph_hash": "",
        "duration_ms": 0,
        "node_count": 0,
        "statuses": {},
        "reproducibility": {"seeds": {}, "content_hashes": {}, "dependency_versions": {}},
        "sdk_version": "0.3.3",
    }
    run_ids = []
    for i in range(3):
        data = {**base, "started_at": float(i), "finished_at": float(i)}
        run_id = store.save(data, {}, {})
        run_ids.append(run_id)

    # Only keep=2, so the first entry should be evicted
    with pytest.raises(UnknownRunError):
        store.get(run_ids[0])
    assert store.get(run_ids[1]) is not None
    assert store.get(run_ids[2]) is not None


def test_list_empty_returns_empty_list(tmp_path: Path) -> None:
    store = RunStore(root=tmp_path, keep=50)
    assert store.list() == []


def test_configure_runs_uses_configured_root(tmp_path: Path, monkeypatch) -> None:
    import emergentflow.server.runs as runs_mod

    monkeypatch.setattr(runs_mod, "_default_runs", None)
    monkeypatch.chdir(tmp_path)
    runs_root = tmp_path / ".ef-runs"
    configure_runs(runs_root, keep=10)
    store = get_default_runs()
    assert store.root == runs_root


def test_configure_runs_after_singleton_created_raises(tmp_path: Path, monkeypatch) -> None:
    import emergentflow.server.runs as runs_mod

    monkeypatch.setattr(runs_mod, "_default_runs", None)
    monkeypatch.chdir(tmp_path)
    get_default_runs()  # Force singleton creation
    with pytest.raises(RuntimeError, match="configure_runs"):
        configure_runs(tmp_path)


# ---------------------------------------------------------------------------
# Route integration tests
# ---------------------------------------------------------------------------


@pytest.fixture
def runs_client(tmp_path, monkeypatch) -> TestClient:
    """A TestClient wired to a tmp-backed RunStore."""
    import emergentflow.server.runs as runs_mod

    store = RunStore(tmp_path / "runs", keep=50)
    monkeypatch.setattr(runs_mod, "_default_runs", store)
    return TestClient(app)


def test_routes_list_empty(runs_client: TestClient) -> None:
    resp = runs_client.get("/runs")
    assert resp.status_code == 200
    data = resp.json()
    assert "runs" in data
    assert data["runs"] == []


def test_routes_get_unknown_returns_404(runs_client: TestClient) -> None:
    resp = runs_client.get(f"/runs/{_VALID_RUN_ID}")
    assert resp.status_code == 404


def test_routes_get_graph_unknown_returns_404(runs_client: TestClient) -> None:
    resp = runs_client.get(f"/runs/{_VALID_RUN_ID}/graph")
    assert resp.status_code == 404


def test_routes_delete_unknown_returns_404(runs_client: TestClient) -> None:
    resp = runs_client.delete(f"/runs/{_VALID_RUN_ID}")
    assert resp.status_code == 404


def test_routes_save_then_list_and_get(runs_client: TestClient) -> None:
    # Access the store from the fixture by patching the module
    import emergentflow.server.runs as runs_mod

    store = runs_mod._default_runs

    run_data = {
        "run_id": "",
        "tag": "test",
        "graph_name": "Route Test",
        "graph_hash": "abc",
        "started_at": 100.0,
        "finished_at": 200.0,
        "duration_ms": 100,
        "node_count": 2,
        "statuses": {},
        "reproducibility": {"seeds": {}, "content_hashes": {}, "dependency_versions": {}},
        "sdk_version": "0.3.3",
    }
    run_id = store.save(run_data, {"name": "Route Test", "nodes": {}, "edges": {}}, {})

    resp = runs_client.get("/runs")
    assert resp.status_code == 200
    runs = resp.json()["runs"]
    assert len(runs) == 1
    assert runs[0]["run_id"] == run_id

    resp = runs_client.get(f"/runs/{run_id}")
    assert resp.status_code == 200
    assert resp.json()["run_id"] == run_id

    resp = runs_client.get(f"/runs/{run_id}/graph")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Route Test"


def test_routes_save_then_delete(runs_client: TestClient) -> None:
    import emergentflow.server.runs as runs_mod

    store = runs_mod._default_runs

    run_data = {
        "run_id": "",
        "tag": None,
        "graph_name": "",
        "graph_hash": "",
        "started_at": 0,
        "finished_at": 0,
        "duration_ms": 0,
        "node_count": 0,
        "statuses": {},
        "reproducibility": {"seeds": {}, "content_hashes": {}, "dependency_versions": {}},
        "sdk_version": "0.3.3",
    }
    run_id = store.save(run_data, {}, {})

    resp = runs_client.delete(f"/runs/{run_id}")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}

    resp = runs_client.get(f"/runs/{run_id}")
    assert resp.status_code == 404
