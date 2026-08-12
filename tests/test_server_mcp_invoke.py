"""
tests/test_server_mcp_invoke.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Task 06a -- server-side MCP invocation routes: ``GET /mcp/tools`` lists every
tool exposed by ``create_mcp_server()`` with its JSON input schema, and
``POST /mcp/invoke`` runs any tool by name with JSON arguments and returns the
structured result. Mirrors tests/test_server_sessions.py's structure and
conventions (the "agent" is the HTTP client; no LLM anywhere).
"""

from __future__ import annotations

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


def _create_session(client: TestClient) -> str:
    return client.post("/sessions", json={}).json()["id"]


def test_mcp_tools_lists_tools(client: TestClient) -> None:
    r = client.get("/mcp/tools")
    assert r.status_code == 200, r.text
    body = r.json()
    tools = body["tools"]
    names = {t["name"] for t in tools}
    assert {"add_node", "connect_ports", "execute_session_tool"} <= names
    # Every tool carries its JSON input schema.
    for tool in tools:
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool
        assert isinstance(tool["inputSchema"], dict)


def test_mcp_invoke_add_node(client: TestClient) -> None:
    session_id = _create_session(client)
    r = client.post(
        "/mcp/invoke",
        json={
            "tool_name": "add_node",
            "arguments": {
                "session_id": session_id,
                "node_type": "data.load_csv",
                "params": {"path": "a.csv"},
            },
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["session_id"] == session_id
    assert "checkpoint_id" in body
    assert "node_id" in body

    # The session graph now contains the new node.
    session = client.get(f"/sessions/{session_id}").json()
    assert body["node_id"] in session["graph"]["nodes"]


def test_mcp_invoke_unknown_tool(client: TestClient) -> None:
    r = client.post(
        "/mcp/invoke",
        json={"tool_name": "no_such_tool", "arguments": {}},
    )
    assert r.status_code == 422, r.text
    assert "error" in r.json()


def test_mcp_invoke_tool_error(client: TestClient) -> None:
    session_id = _create_session(client)
    r = client.post(
        "/mcp/invoke",
        json={
            "tool_name": "add_node",
            "arguments": {
                "session_id": session_id,
                "node_type": "no.such.node",
            },
        },
    )
    assert r.status_code == 422, r.text
    assert "error" in r.json()


def test_mcp_invoke_requires_auth_when_auth_enabled() -> None:
    configure_session_auth(required=True, token="secret")
    try:
        app = create_app()
        with TestClient(app) as auth_client:
            # Without a token both routes are rejected.
            assert auth_client.get("/mcp/tools").status_code == 401
            assert (
                auth_client.post("/mcp/invoke", json={"tool_name": "list_sessions"}).status_code
                == 401
            )

            # With the token they succeed.
            assert (
                auth_client.get(
                    "/mcp/tools", headers={"Authorization": "Bearer secret"}
                ).status_code
                == 200
            )
            r = auth_client.post(
                "/mcp/invoke",
                json={"tool_name": "list_sessions", "arguments": {}},
                headers={"Authorization": "Bearer secret"},
            )
            assert r.status_code == 200, r.text
    finally:
        configure_session_auth(required=False)
