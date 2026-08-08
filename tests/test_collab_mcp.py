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
from pathlib import Path
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


@pytest.fixture(autouse=True)
def _fresh_runs_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate the process-wide default RunStore per test into tmp_path so the
    read-back tools (get_results/get_metric/compare_runs) never touch the repo's
    real ``.ef-runs/`` directory.
    """
    import emergentflow.server.runs as runs_mod

    monkeypatch.setattr(runs_mod, "_default_runs", None)
    monkeypatch.setattr(runs_mod, "_configured_runs_root", tmp_path)


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

    def test_compile_session_tool(self) -> None:
        """compile_session_tool returns {"code": "..."} for a valid session."""
        from emergentflow.collab.mcp import create_mcp_server

        session = session_mod.get_default_store().create()

        mcp = create_mcp_server()
        result = _run_async(_call_tool(mcp, "compile_session_tool", {"session_id": session.id}))
        assert isinstance(result, dict)
        assert "code" in result

    def test_compile_session_tool_blocked_by_gates(self) -> None:
        """compile_session_tool returns {"blocked_by_gates": [...]} when gates are OPEN."""
        from emergentflow.collab.gates import Gate, GateKind
        from emergentflow.collab.mcp import create_mcp_server

        session = session_mod.get_default_store().create()
        # Open a gate to block compilation
        session_mod.get_default_store().open_gate(
            session.id,
            Gate(phase="test", kind=GateKind.PHASE, description="test gate"),
        )

        mcp = create_mcp_server()
        result = _run_async(_call_tool(mcp, "compile_session_tool", {"session_id": session.id}))
        assert isinstance(result, dict)
        assert "blocked_by_gates" in result
        assert len(result["blocked_by_gates"]) == 1
        assert result["blocked_by_gates"][0]["phase"] == "test"
        assert result["blocked_by_gates"][0]["kind"] == "phase"

    def test_execute_session_tool(self) -> None:
        """execute_session_tool returns results/statuses for a valid session."""
        from emergentflow.collab.mcp import create_mcp_server

        session = session_mod.get_default_store().create()

        mcp = create_mcp_server()
        result = _run_async(_call_tool(mcp, "execute_session_tool", {"session_id": session.id}))
        assert isinstance(result, dict)
        assert "results" in result
        assert "statuses" in result

    def test_execute_session_tool_blocked_by_gates(self) -> None:
        """execute_session_tool returns {"blocked_by_gates": [...]} when gates are OPEN."""
        from emergentflow.collab.gates import Gate, GateKind
        from emergentflow.collab.mcp import create_mcp_server

        session = session_mod.get_default_store().create()
        # Open a gate to block execution
        session_mod.get_default_store().open_gate(
            session.id,
            Gate(phase="test", kind=GateKind.EXECUTE, description="test execute gate"),
        )

        mcp = create_mcp_server()
        result = _run_async(_call_tool(mcp, "execute_session_tool", {"session_id": session.id}))
        assert isinstance(result, dict)
        assert "blocked_by_gates" in result
        assert len(result["blocked_by_gates"]) == 1
        assert result["blocked_by_gates"][0]["kind"] == "execute"

    def test_execute_session_tool_with_scope(self) -> None:
        """execute_session_tool accepts optional run_to/run_from/run_only scopes."""
        from emergentflow.collab.mcp import create_mcp_server

        session = session_mod.get_default_store().create()

        mcp = create_mcp_server()
        # run_to scope (empty graph, so no nodes to target, but validates the param passes through)
        result = _run_async(
            _call_tool(
                mcp,
                "execute_session_tool",
                {"session_id": session.id, "run_to": []},
            )
        )
        assert isinstance(result, dict)
        assert "results" in result

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

    def test_get_results_reads_persisted_payloads(self, tmp_path: Path) -> None:
        """get_results reads payloads.json (separate from run.json) -- regression for
        the closed-loop read-back being empty because it read the wrong file."""
        from emergentflow.collab.mcp import create_mcp_server
        from emergentflow.server.runs import get_default_runs

        run_id = get_default_runs().save(
            {"tag": "x", "graph_name": "g", "started_at": 1.0},
            {"name": "g"},
            {
                "n1": {
                    "metric": {"kind": "scalar", "value": 1.5},
                    "name": {"kind": "text", "value": "hi"},
                }
            },
        )

        mcp = create_mcp_server()
        result = _run_async(_call_tool(mcp, "get_results", {"run_id": run_id}))
        assert result["results"]["n1"]["metric"]["value"] == 1.5

    def test_get_metric_reads_persisted_payloads(self, tmp_path: Path) -> None:
        from emergentflow.collab.mcp import create_mcp_server
        from emergentflow.server.runs import get_default_runs

        run_id = get_default_runs().save(
            {"tag": "x", "graph_name": "g", "started_at": 1.0},
            {"name": "g"},
            {"n1": {"metric": {"kind": "scalar", "value": 1.5}}},
        )

        mcp = create_mcp_server()
        result = _run_async(
            _call_tool(
                mcp,
                "get_metric",
                {"run_id": run_id, "node_id": "n1", "metric_name": "metric"},
            )
        )
        assert result["value"] == 1.5

    def test_compare_runs_reads_persisted_payloads(self, tmp_path: Path) -> None:
        from emergentflow.collab.mcp import create_mcp_server
        from emergentflow.server.runs import get_default_runs

        store = get_default_runs()
        run_a = store.save(
            {"tag": "a", "graph_name": "g", "started_at": 1.0},
            {"name": "g"},
            {"n1": {"metric": {"kind": "scalar", "value": 1.5}}},
        )
        run_b = store.save(
            {"tag": "b", "graph_name": "g", "started_at": 2.0},
            {"name": "g"},
            {"n1": {"metric": {"kind": "scalar", "value": 2.5}}},
        )

        mcp = create_mcp_server()
        result = _run_async(
            _call_tool(
                mcp,
                "compare_runs",
                {
                    "run_id_a": run_a,
                    "run_id_b": run_b,
                    "node_id": "n1",
                    "metric_name": "metric",
                },
            )
        )
        assert result["before"] == 1.5
        assert result["after"] == 2.5
        assert result["delta"] == 1.0

    def test_record_attempt_tool(self, tmp_path: Path) -> None:
        from emergentflow.collab.mcp import create_mcp_server

        session = session_mod.get_default_store().create()

        mcp = create_mcp_server()
        result = _run_async(
            _call_tool(
                mcp,
                "record_attempt_tool",
                {
                    "session_id": session.id,
                    "mutation_id": "m1",
                    "run_id": "r1",
                    "metric_name": "accuracy",
                    "metric_value": 0.9,
                    "verdict": "kept",
                    "hypothesis": "increase lr",
                },
            )
        )
        assert result["mutation_id"] == "m1"
        assert result["metric_value"] == 0.9
        assert result["verdict"] == "kept"
        # The ledger is wired: the session can read the attempt back.
        attempts = session_mod.get_default_store().get(session.id).collab.attempts
        assert len(attempts) == 1
        stored = next(iter(attempts.values()))
        assert stored.mutation_id == "m1"
