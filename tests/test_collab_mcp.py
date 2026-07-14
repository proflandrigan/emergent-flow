"""
tests/test_collab_mcp.py
~~~~~~~~~~~~~~~~~~~~~~~~~
Tests for the MCP collaboration wrapper (Epic 14 Story 7): the fastmcp-based
tool server registered via ``create_mcp_server()``.

Two code paths:
1. Happy path — fastmcp IS installed (this test environment, after ``uv add
   fastmcp --optional mcp``): create the server and exercise every tool through
   fastmcp's in-memory ``Client``.
2. Absent-extra path — fastmcp NOT installed: the module itself is importable,
   only ``create_mcp_server()`` raises a ``ModuleNotFoundError`` with an install hint.
"""

from __future__ import annotations

import asyncio
import builtins
from typing import Any

import pytest

from emergentflow.collab import session as session_mod
from emergentflow.ir.mutation import GraphMutation


@pytest.fixture(autouse=True)
def _fresh_session_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate the process-wide default SessionStore per test (mirror
    ``test_server_sessions.py``'s ``_fresh_session_store``) so sessions created
    by one test never leak into another.
    """
    monkeypatch.setattr(session_mod, "_default_store", None)


# ---------------------------------------------------------------------------
# Absent-extra path
# ---------------------------------------------------------------------------


def test_import_without_extra_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    """The module itself must be importable even when ``fastmcp`` is absent."""
    real_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "fastmcp" or name.startswith("fastmcp."):
            raise ModuleNotFoundError("No module named 'fastmcp'", name="fastmcp")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    import emergentflow.collab.mcp  # noqa: F811

    assert emergentflow.collab.mcp is not None


def test_create_server_without_extra_prints_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    """Calling ``create_mcp_server()`` without ``fastmcp`` raises a
    ``ModuleNotFoundError`` containing the install hint.
    """
    real_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "fastmcp" or name.startswith("fastmcp."):
            raise ModuleNotFoundError("No module named 'fastmcp'", name="fastmcp")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    from emergentflow.collab.mcp import create_mcp_server

    with pytest.raises(ModuleNotFoundError) as exc_info:
        create_mcp_server()

    msg = str(exc_info.value)
    assert "emergentflow[mcp]" in msg
    assert "fastmcp" in msg


# ---------------------------------------------------------------------------
# Happy path — fastmcp installed
# ---------------------------------------------------------------------------


def _run_async(coro) -> Any:
    """Run an async coroutine synchronously for test convenience."""
    return asyncio.run(coro)


async def _call_tool(mcp_server, tool_name: str, arguments: dict[str, Any] | None = None):
    """Call a tool on *mcp_server* via fastmcp's in-memory Client and return
    the structured content (the tool's actual return value).
    """
    from fastmcp.client import Client

    client = Client(mcp_server)
    async with client:
        result = await client.call_tool(tool_name, arguments or {})
    return result.structured_content


class TestTools:
    """Exercise every tool registered by ``create_mcp_server()``."""

    def test_get_catalog(self) -> None:
        from emergentflow.collab.mcp import create_mcp_server

        mcp = create_mcp_server()
        result = _run_async(_call_tool(mcp, "get_catalog_tool"))
        assert isinstance(result, dict)
        assert "nodes" in result

    def test_list_sessions_empty(self) -> None:
        from emergentflow.collab.mcp import create_mcp_server

        mcp = create_mcp_server()
        result = _run_async(_call_tool(mcp, "list_sessions"))
        assert result == {"sessions": []}

    def test_list_sessions_non_empty(self) -> None:
        from emergentflow.collab.mcp import create_mcp_server

        session_mod.get_default_store().create()

        mcp = create_mcp_server()
        result = _run_async(_call_tool(mcp, "list_sessions"))
        assert isinstance(result, dict)
        assert len(result["sessions"]) == 1
        assert "id" in result["sessions"][0]
        assert "graph" in result["sessions"][0]

    def test_get_graph(self) -> None:
        from emergentflow.collab.mcp import create_mcp_server

        session = session_mod.get_default_store().create()

        mcp = create_mcp_server()
        result = _run_async(_call_tool(mcp, "get_graph", {"session_id": session.id}))
        assert isinstance(result, dict)
        assert result["id"] == session.id
        assert result["version"] == 0

    def test_get_graph_unknown_session(self) -> None:
        from fastmcp.exceptions import ToolError

        from emergentflow.collab.mcp import create_mcp_server

        mcp = create_mcp_server()
        with pytest.raises(ToolError):
            _run_async(_call_tool(mcp, "get_graph", {"session_id": "does-not-exist"}))

    def test_validate_graph(self) -> None:
        from emergentflow.collab.mcp import create_mcp_server

        trivial: dict[str, Any] = {"nodes": {}, "edges": {}}

        mcp = create_mcp_server()
        result = _run_async(_call_tool(mcp, "validate_graph_tool", {"graph": trivial}))
        assert isinstance(result, dict)
        assert "diagnostics" in result

    def test_compile_preview(self) -> None:
        from emergentflow.collab.mcp import create_mcp_server

        trivial: dict[str, Any] = {"nodes": {}, "edges": {}, "paradigm": "functional"}

        mcp = create_mcp_server()
        result = _run_async(_call_tool(mcp, "compile_preview", {"graph": trivial}))
        assert isinstance(result, dict)
        assert "code" in result

    def test_propose_mutation(self) -> None:
        from emergentflow.collab.mcp import create_mcp_server

        session = session_mod.get_default_store().create()

        mcp = create_mcp_server()
        result = _run_async(
            _call_tool(
                mcp, "propose_mutation", {"session_id": session.id, "mutation": {"base_version": 0}}
            )
        )
        assert isinstance(result, dict)
        assert result["status"] == "pending"
        assert "id" in result

    def test_post_review(self) -> None:
        from emergentflow.collab.mcp import create_mcp_server

        session = session_mod.get_default_store().create()

        mcp = create_mcp_server()
        result = _run_async(
            _call_tool(
                mcp, "post_review", {"session_id": session.id, "review": {"author": "test_bot"}}
            )
        )
        assert isinstance(result, dict)
        assert result["author"] == "test_bot"
        assert result["status"] == "open"

    def test_await_verdict_accepted(self) -> None:
        from emergentflow.collab.mcp import create_mcp_server

        session = session_mod.get_default_store().create()
        mutation = GraphMutation(base_version=0)
        proposal = session_mod.get_default_store().add_proposal(session.id, mutation)

        # Accept the proposal in a background thread after a short delay so
        # await_verdict's subscriber is already registered when the event fires.
        import threading

        def _accept_soon() -> None:
            import time

            time.sleep(0.15)
            session_mod.get_default_store().accept_proposal(session.id, proposal.id)

        threading.Thread(target=_accept_soon, daemon=True).start()

        mcp = create_mcp_server()
        result = _run_async(
            _call_tool(
                mcp,
                "await_verdict",
                {"session_id": session.id, "proposal_id": proposal.id, "timeout_seconds": 5.0},
            )
        )
        assert isinstance(result, dict)
        assert result["status"] == "accepted"
        assert result["proposal_id"] == proposal.id

    def test_await_verdict_already_resolved_before_call_returns_immediately(self) -> None:
        """A verdict landing BEFORE await_verdict subscribes must not read as a timeout.

        Regression test for the race the tool's subscribe-then-check ordering guards
        against: an agent that calls propose_mutation then await_verdict can lose the
        race to a fast accept/reject that already published its event to no one.
        """
        from emergentflow.collab.mcp import create_mcp_server

        session = session_mod.get_default_store().create()
        mutation = GraphMutation(base_version=0)
        proposal = session_mod.get_default_store().add_proposal(session.id, mutation)
        session_mod.get_default_store().accept_proposal(session.id, proposal.id)

        mcp = create_mcp_server()
        result = _run_async(
            _call_tool(
                mcp,
                "await_verdict",
                {"session_id": session.id, "proposal_id": proposal.id, "timeout_seconds": 0.2},
            )
        )
        assert isinstance(result, dict)
        assert result["status"] == "accepted"
        assert result["proposal_id"] == proposal.id

    def test_await_verdict_timeout(self) -> None:
        from emergentflow.collab.mcp import create_mcp_server

        session = session_mod.get_default_store().create()
        mutation = GraphMutation(base_version=0)
        proposal = session_mod.get_default_store().add_proposal(session.id, mutation)

        mcp = create_mcp_server()
        result = _run_async(
            _call_tool(
                mcp,
                "await_verdict",
                {"session_id": session.id, "proposal_id": proposal.id, "timeout_seconds": 0.2},
            )
        )
        assert isinstance(result, dict)
        assert result["status"] == "timeout"
        assert result["proposal_id"] == proposal.id

    def test_await_verdict_unknown_proposal_fails_fast(self) -> None:
        """An unknown proposal_id must raise immediately, not block for the full timeout.

        Regression test: await_verdict used to fall through into the poll loop for a
        nonexistent proposal_id (no early return, no matching event possible), blocking
        for the entire timeout_seconds window before returning an indistinguishable
        {"status": "timeout"}.
        """
        import time

        from fastmcp.exceptions import ToolError

        from emergentflow.collab.mcp import create_mcp_server

        session = session_mod.get_default_store().create()

        mcp = create_mcp_server()
        start = time.monotonic()
        with pytest.raises(ToolError):
            _run_async(
                _call_tool(
                    mcp,
                    "await_verdict",
                    {
                        "session_id": session.id,
                        "proposal_id": "does-not-exist",
                        "timeout_seconds": 5.0,
                    },
                )
            )
        assert time.monotonic() - start < 1.0
