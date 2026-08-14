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

    def test_create_session_bare(self) -> None:
        from emergentflow.collab.mcp import create_mcp_server

        mcp = create_mcp_server()
        result = _run_async(_call_tool(mcp, "create_session", {}))
        assert isinstance(result["id"], str) and result["id"]
        assert result["open_in_ui"] == f"http://127.0.0.1:8765/?session={result['id']}"
        assert session_mod.get_default_store().get(result["id"]) is not None

    def test_create_session_seeded_with_graph(self) -> None:
        from emergentflow.collab.mcp import create_mcp_server

        trivial: dict[str, Any] = {"nodes": {}, "edges": {}}

        mcp = create_mcp_server()
        result = _run_async(_call_tool(mcp, "create_session", {"graph": trivial}))
        assert isinstance(result["id"], str) and result["id"]
        session = session_mod.get_default_store().get(result["id"])
        assert session is not None
        assert session.graph.model_dump()["nodes"] == {}

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
        assert result.get("run_id")

        # A full (non-partial) run is persisted, so the agent can read its results
        # back by run_id -- confirming the run_id is real, not a placeholder.
        readback = _run_async(_call_tool(mcp, "get_results", {"run_id": result["run_id"]}))
        assert readback["run_id"] == result["run_id"]
        assert "results" in readback
        assert "error" not in readback

    def test_execute_session_tool_publishes_run_completed(self) -> None:
        """Executing a session run publishes a ``run_completed`` SSE event with the run_id."""
        from emergentflow.collab.mcp import create_mcp_server

        store = session_mod.get_default_store()
        session = store.create()
        q = store.subscribe(session.id)

        mcp = create_mcp_server()
        result = _run_async(_call_tool(mcp, "execute_session_tool", {"session_id": session.id}))
        assert isinstance(result, dict)
        assert result.get("run_id")

        # Drain the subscriber queue until a run_completed event for this run arrives.
        matches = None
        for _ in range(5):
            event = q.get(timeout=1.0)
            if event.get("type") == "run_completed":
                matches = event
                break
        assert matches is not None
        assert matches["run_id"] == result["run_id"]

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

    def test_await_verdict_rejects_negative_timeout(self) -> None:
        """A negative timeout_seconds must be rejected up front (surfaced as ToolError)."""
        from fastmcp.exceptions import ToolError

        from emergentflow.collab.mcp import create_mcp_server

        session = session_mod.get_default_store().create()
        mutation = GraphMutation(base_version=0)
        proposal = session_mod.get_default_store().add_proposal(session.id, mutation)

        mcp = create_mcp_server()
        with pytest.raises(ToolError):
            _run_async(
                _call_tool(
                    mcp,
                    "await_verdict",
                    {
                        "session_id": session.id,
                        "proposal_id": proposal.id,
                        "timeout_seconds": -1,
                    },
                )
            )

    def test_await_verdict_times_out_immediately_on_zero_deadline(self) -> None:
        """A timeout_seconds of 0.0 on an unresolved proposal times out immediately."""
        from emergentflow.collab.mcp import create_mcp_server

        session = session_mod.get_default_store().create()
        mutation = GraphMutation(base_version=0)
        proposal = session_mod.get_default_store().add_proposal(session.id, mutation)

        mcp = create_mcp_server()
        result = _run_async(
            _call_tool(
                mcp,
                "await_verdict",
                {"session_id": session.id, "proposal_id": proposal.id, "timeout_seconds": 0.0},
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


class TestEditingTools:
    """Exercise the fine-grained graph-editing tools (Task 03)."""

    def _add_node(
        self, mcp, session_id: str, node_type: str, params: dict[str, Any] | None = None
    ) -> dict:
        arguments: dict[str, Any] = {"session_id": session_id, "node_type": node_type}
        if params is not None:
            arguments["params"] = params
        return _run_async(_call_tool(mcp, "add_node", arguments))

    def test_add_node(self) -> None:
        from emergentflow.collab.mcp import create_mcp_server

        session = session_mod.get_default_store().create()
        mcp = create_mcp_server()

        result = self._add_node(mcp, session.id, "data.load_csv", {"path": "a.csv"})
        assert result["session_id"] == session.id
        assert result["version"] == 1
        assert "checkpoint_id" in result
        assert "node_id" in result

        stored = session_mod.get_default_store().get(session.id)
        assert result["node_id"] in stored.graph.nodes
        assert stored.graph.nodes[result["node_id"]].type == "data.load_csv"

    def test_connect_ports(self) -> None:
        from emergentflow.collab.mcp import create_mcp_server

        session = session_mod.get_default_store().create()
        mcp = create_mcp_server()

        source = self._add_node(mcp, session.id, "data.load_csv", {"path": "a.csv"})
        target = self._add_node(
            mcp,
            session.id,
            "script.custom_code",
            {"code": "def transform(value):\n    return value"},
        )

        result = _run_async(
            _call_tool(
                mcp,
                "connect_ports",
                {
                    "session_id": session.id,
                    "source_node_id": source["node_id"],
                    "source_port_name": "frame",
                    "target_node_id": target["node_id"],
                    "target_port_name": "value",
                },
            )
        )
        assert result["session_id"] == session.id
        assert "checkpoint_id" in result
        assert "edge_id" in result

        stored = session_mod.get_default_store().get(session.id)
        assert result["edge_id"] in stored.graph.edges
        edge = stored.graph.edges[result["edge_id"]]
        assert edge.source.node_id == source["node_id"]
        assert edge.target.node_id == target["node_id"]

    def test_connect_ports_prefers_out_for_source_same_named_ports(self) -> None:
        from emergentflow.collab.mcp import create_mcp_server
        from emergentflow.ir.common import Direction

        session = session_mod.get_default_store().create()
        mcp = create_mcp_server()

        source = self._add_node(mcp, session.id, "clean.explode_lists", {"columns": ["items"]})
        target = self._add_node(
            mcp,
            session.id,
            "script.custom_code",
            {"code": "def transform(value):\n    return value"},
        )

        stored = session_mod.get_default_store().get(session.id)
        source_node = stored.graph.nodes[source["node_id"]]
        frame_out_port = next(
            p for p in source_node.ports if p.name == "frame" and p.direction == Direction.OUT
        )

        result = _run_async(
            _call_tool(
                mcp,
                "connect_ports",
                {
                    "session_id": session.id,
                    "source_node_id": source["node_id"],
                    "source_port_name": "frame",
                    "target_node_id": target["node_id"],
                    "target_port_name": "value",
                },
            )
        )
        assert result["session_id"] == session.id
        assert "checkpoint_id" in result
        assert "edge_id" in result

        stored = session_mod.get_default_store().get(session.id)
        edge = stored.graph.edges[result["edge_id"]]
        assert edge.source.node_id == source["node_id"]
        assert edge.source.port_id == frame_out_port.id
        assert edge.target.node_id == target["node_id"]

    def test_set_param(self) -> None:
        from emergentflow.collab.mcp import create_mcp_server

        session = session_mod.get_default_store().create()
        mcp = create_mcp_server()

        added = self._add_node(mcp, session.id, "data.load_csv", {"path": "a.csv"})
        node_id = added["node_id"]

        result = _run_async(
            _call_tool(
                mcp,
                "set_param",
                {
                    "session_id": session.id,
                    "node_id": node_id,
                    "param_name": "encoding",
                    "value": "latin-1",
                },
            )
        )
        assert result["version"] == 2
        assert result["node_id"] == node_id

        stored = session_mod.get_default_store().get(session.id)
        node = stored.graph.nodes[node_id]
        params = {p.name: p.value for p in node.params}
        assert params["encoding"] == "latin-1"

    def test_delete_node(self) -> None:
        from emergentflow.collab.mcp import create_mcp_server

        session = session_mod.get_default_store().create()
        mcp = create_mcp_server()

        source = self._add_node(mcp, session.id, "data.load_csv", {"path": "a.csv"})
        target = self._add_node(
            mcp,
            session.id,
            "script.custom_code",
            {"code": "def transform(value):\n    return value"},
        )
        conn = _run_async(
            _call_tool(
                mcp,
                "connect_ports",
                {
                    "session_id": session.id,
                    "source_node_id": source["node_id"],
                    "source_port_name": "frame",
                    "target_node_id": target["node_id"],
                    "target_port_name": "value",
                },
            )
        )

        result = _run_async(
            _call_tool(mcp, "delete_node", {"session_id": session.id, "node_id": source["node_id"]})
        )
        assert result["node_id"] == source["node_id"]

        stored = session_mod.get_default_store().get(session.id)
        assert source["node_id"] not in stored.graph.nodes
        assert conn["edge_id"] not in stored.graph.edges
        # The target node survives.
        assert target["node_id"] in stored.graph.nodes

    def test_add_note(self) -> None:
        from emergentflow.collab.mcp import create_mcp_server

        session = session_mod.get_default_store().create()
        mcp = create_mcp_server()

        anchor = self._add_node(mcp, session.id, "data.load_csv", {"path": "a.csv"})

        result = _run_async(
            _call_tool(
                mcp,
                "add_note",
                {
                    "session_id": session.id,
                    "content": "hello note",
                    "anchor_id": anchor["node_id"],
                },
            )
        )
        assert result["session_id"] == session.id
        assert "checkpoint_id" in result
        assert "node_id" in result

        stored = session_mod.get_default_store().get(session.id)
        note = stored.graph.nodes[result["node_id"]]
        assert note.type == "notes.markdown"
        params = {p.name: p.value for p in note.params}
        assert params["content"] == "hello note"
        assert params["anchor_id"] == anchor["node_id"]
        assert params["color"] == "yellow"

    def test_delete_edge(self) -> None:
        from emergentflow.collab.mcp import create_mcp_server

        session = session_mod.get_default_store().create()
        mcp = create_mcp_server()

        source = self._add_node(mcp, session.id, "data.load_csv", {"path": "a.csv"})
        target = self._add_node(
            mcp,
            session.id,
            "script.custom_code",
            {"code": "def transform(value):\n    return value"},
        )
        conn = _run_async(
            _call_tool(
                mcp,
                "connect_ports",
                {
                    "session_id": session.id,
                    "source_node_id": source["node_id"],
                    "source_port_name": "frame",
                    "target_node_id": target["node_id"],
                    "target_port_name": "value",
                },
            )
        )

        result = _run_async(
            _call_tool(mcp, "delete_edge", {"session_id": session.id, "edge_id": conn["edge_id"]})
        )
        assert result["edge_id"] == conn["edge_id"]

        stored = session_mod.get_default_store().get(session.id)
        assert conn["edge_id"] not in stored.graph.edges
        # Both nodes survive.
        assert source["node_id"] in stored.graph.nodes
        assert target["node_id"] in stored.graph.nodes

    def test_delete_note(self) -> None:
        from emergentflow.collab.mcp import create_mcp_server

        session = session_mod.get_default_store().create()
        mcp = create_mcp_server()

        added = _run_async(
            _call_tool(
                mcp,
                "add_note",
                {"session_id": session.id, "content": "to be removed"},
            )
        )

        result = _run_async(
            _call_tool(
                mcp, "delete_note", {"session_id": session.id, "note_node_id": added["node_id"]}
            )
        )
        assert result["node_id"] == added["node_id"]

        stored = session_mod.get_default_store().get(session.id)
        assert added["node_id"] not in stored.graph.nodes

    def test_add_node_unknown_type_fails(self) -> None:
        from fastmcp.exceptions import ToolError

        from emergentflow.collab.mcp import create_mcp_server

        session = session_mod.get_default_store().create()
        mcp = create_mcp_server()

        with pytest.raises(ToolError):
            _run_async(
                _call_tool(
                    mcp, "add_node", {"session_id": session.id, "node_type": "does.not.exist"}
                )
            )


class TestExecutionTools:
    """Exercise the execution/introspection tools (Task 04)."""

    def test_execute_node_tool_runs_single_node(self) -> None:
        from emergentflow.collab.mcp import create_mcp_server

        session = session_mod.get_default_store().create()
        mcp = create_mcp_server()

        added = _run_async(
            _call_tool(
                mcp,
                "add_node",
                {
                    "session_id": session.id,
                    "node_type": "data.load_csv",
                    "params": {"path": "a.csv"},
                },
            )
        )

        result = _run_async(
            _call_tool(
                mcp,
                "execute_node_tool",
                {"session_id": session.id, "node_id": added["node_id"]},
            )
        )
        assert "payload_version" in result
        assert "results" in result
        assert "statuses" in result

    def test_execute_node_tool_unknown_session_fails(self) -> None:
        from fastmcp.exceptions import ToolError

        from emergentflow.collab.mcp import create_mcp_server

        mcp = create_mcp_server()
        with pytest.raises(ToolError):
            _run_async(
                _call_tool(
                    mcp,
                    "execute_node_tool",
                    {"session_id": "does-not-exist", "node_id": "n1"},
                )
            )

    def test_get_node_outputs_filters_payloads(self, tmp_path: Path) -> None:
        from emergentflow.collab.mcp import create_mcp_server
        from emergentflow.server.runs import get_default_runs

        run_id = get_default_runs().save(
            {"tag": "x", "graph_name": "g", "started_at": 1.0},
            {"name": "g"},
            {
                "n1": {"metric": {"kind": "scalar", "value": 1.5}},
                "n2": {"metric": {"kind": "scalar", "value": 2.5}},
            },
        )

        mcp = create_mcp_server()
        result = _run_async(
            _call_tool(mcp, "get_node_outputs", {"run_id": run_id, "node_ids": ["n1"]})
        )
        assert result["run_id"] == run_id
        assert set(result["outputs"].keys()) == {"n1"}
        assert result["outputs"]["n1"]["metric"]["value"] == 1.5

    def test_get_node_outputs_unknown_run_returns_error(self) -> None:
        from emergentflow.collab.mcp import create_mcp_server

        mcp = create_mcp_server()
        result = _run_async(
            _call_tool(
                mcp,
                "get_node_outputs",
                {"run_id": "2026-07-30T14-02-11Z-0000", "node_ids": ["n1"]},
            )
        )
        assert result == {"error": "Run '2026-07-30T14-02-11Z-0000' not found"}
