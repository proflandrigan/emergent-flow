"""
tests/test_server_execute_session_run.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Task 08a — a full (non-partial) session execute persists a run and returns a real
``run_id`` that the collaboration read-back tools can fetch via ``get_default_runs()``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from emergentflow.collab import session as session_mod
from emergentflow.server.app import create_app
from emergentflow.server.runs import get_default_runs


@pytest.fixture(autouse=True)
def _fresh_session_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate the process-wide default SessionStore per test (mirror
    ``test_server_sessions.py``)."""
    monkeypatch.setattr(session_mod, "_default_store", None)


@pytest.fixture(autouse=True)
def _fresh_runs_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate the process-wide default RunStore per test into tmp_path so the
    server's execute never touches the repo's real ``.ef-runs/`` directory."""
    import emergentflow.server.runs as runs_mod

    monkeypatch.setattr(runs_mod, "_default_runs", None)
    monkeypatch.setattr(runs_mod, "_configured_runs_root", tmp_path)


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_session_execute_returns_persisted_run_id(client: TestClient) -> None:
    """A full session execute returns a non-empty ``run_id`` that get_payloads reads back."""
    session_id = client.post("/sessions", json={"graph": {"nodes": {}, "edges": {}}}).json()["id"]

    r = client.post(f"/sessions/{session_id}/execute", json={})

    assert r.status_code == 200, r.text
    body = r.json()
    run_id = body["run_id"]
    assert isinstance(run_id, str)
    assert run_id != ""

    payloads = get_default_runs().get_payloads(run_id)
    assert isinstance(payloads, dict)
