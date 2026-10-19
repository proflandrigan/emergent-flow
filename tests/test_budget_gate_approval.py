"""Closing a budget gate must approve exactly one over-budget session run."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from emergentflow.collab import session as session_mod
from emergentflow.server.app import configure_session_auth, create_app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(session_mod, "_default_store", None)
    monkeypatch.setenv("EMERGENTFLOW_BUDGET_CEILING_USD", "-1")  # any run is over budget
    configure_session_auth(required=False)
    return TestClient(create_app())


def test_closed_budget_gate_approves_one_run(client: TestClient) -> None:
    sid = client.post("/sessions", json={}).json()["id"]
    first = client.post(f"/sessions/{sid}/execute", json={}).json()
    assert first["budget_exceeded"] is True
    assert client.post(f"/sessions/{sid}/gates/{first['gate_id']}/close").status_code == 200

    approved = client.post(f"/sessions/{sid}/execute", json={}).json()
    assert "budget_exceeded" not in approved  # the approved run executed

    # The approval is spent: the next over-budget run opens a new gate.
    third = client.post(f"/sessions/{sid}/execute", json={}).json()
    assert third["budget_exceeded"] is True
    assert third["gate_id"] != first["gate_id"]
