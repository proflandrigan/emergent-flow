"""
emergentflow.collab.mcp
~~~~~~~~~~~~~~~~~~~~~~~
Thin MCP wrapper (Epic 14 Story 7) exposing the same collaboration capabilities
the HTTP routes (``emergentflow/server/app.py``) already call — "one behavior,
two doors."  No new logic lives here.

Every tool in this module delegates to the SAME underlying functions:
``emergentflow.collab.session.SessionStore`` for session state,
``emergentflow.server.service`` for catalog/validate/compile, and
``emergentflow.ir.mutation.GraphMutation`` / ``emergentflow.collab.review.ReviewThread``
for type-safe argument validation.

The ``fastmcp`` library is an **optional** dependency (the ``[mcp]`` extra).
``emergentflow.collab.mcp`` itself is importable without it installed; only
``create_mcp_server()`` raises a ``ModuleNotFoundError`` with an install hint.

Never imported by ``emergentflow/__init__.py`` or ``emergentflow/collab/__init__.py``
— collaboration state lives beside the graph (ADR 0019 / ADR 0007).
"""

from __future__ import annotations

import queue
import time
from typing import Any


def _import_fastmcp() -> Any:
    """Import fastmcp lazily; raise ModuleNotFoundError with an install hint if absent."""
    try:
        import fastmcp
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "emergentflow.collab.mcp needs the `mcp` extra "
            f"(missing dependency: {exc.name}).\n"
            "Install it with:  pip install 'emergentflow[mcp]'"
        ) from exc
    return fastmcp


def create_mcp_server() -> Any:
    """Build and return the FastMCP server exposing the Epic 14 collaboration tools.

    Raises ModuleNotFoundError (with an install hint) if the ``mcp`` extra is not installed.
    Every tool below delegates to the SAME functions the HTTP routes
    (``emergentflow/server/app.py``) already call — this module adds no new behavior.
    """
    fastmcp = _import_fastmcp()
    mcp = fastmcp.FastMCP("emergent-flow-collaboration")

    from emergentflow.collab.review import ReviewThread
    from emergentflow.collab.session import get_default_store as get_default_session_store
    from emergentflow.ir.mutation import GraphMutation
    from emergentflow.server.service import compile_graph, get_catalog, validate_graph

    @mcp.tool()
    def get_graph(session_id: str) -> dict:
        """Return the full session document for *session_id* (same as GET /sessions/{id})."""
        session = get_default_session_store().get(session_id)
        return session.model_dump(mode="json")

    @mcp.tool()
    def list_sessions() -> dict:
        """List every active session (same as GET /sessions)."""
        sessions = get_default_session_store().list()
        return {"sessions": [s.model_dump(mode="json") for s in sessions]}

    @mcp.tool()
    def get_catalog_tool() -> dict:
        """Return the versioned node catalog (same as GET /catalog)."""
        return get_catalog()

    @mcp.tool()
    def validate_graph_tool(graph: dict) -> dict:
        """Validate an IR graph and return diagnostics (same as POST /validate)."""
        return validate_graph(graph)

    @mcp.tool()
    def compile_preview(graph: dict) -> dict:
        """Compile an IR graph to Python code (same as POST /compile)."""
        return compile_graph(graph)

    @mcp.tool()
    def propose_mutation(session_id: str, mutation: dict) -> dict:
        """Propose a graph mutation on *session_id* (same as POST /sessions/{id}/proposals)."""
        mutation_obj = GraphMutation.model_validate(mutation)
        proposal = get_default_session_store().add_proposal(session_id, mutation_obj)
        return proposal.model_dump(mode="json")

    @mcp.tool()
    def post_review(session_id: str, review: dict) -> dict:
        """Post a review thread on *session_id* (same as POST /sessions/{id}/reviews)."""
        thread = ReviewThread.model_validate(review)
        result = get_default_session_store().add_review(session_id, thread)
        return result.model_dump(mode="json")

    @mcp.tool()
    def await_verdict(session_id: str, proposal_id: str, timeout_seconds: float = 30.0) -> dict:
        """Long-poll for a proposal verdict on *session_id* (same as the SSE events route).

        Subscribes to the session's event queue BEFORE checking the proposal's current
        status, so a verdict that lands between the check and the subscribe is never
        missed -- then waits up to *timeout_seconds* for a ``proposal_accepted`` or
        ``proposal_rejected`` event whose ``proposal_id`` matches. Returns immediately
        if the proposal already has a verdict (e.g. it was resolved before this tool was
        called) or when a matching event arrives, else ``{"status": "timeout", ...}``
        once the deadline is exceeded.
        """
        store = get_default_session_store()
        q = store.subscribe(session_id)
        start = time.monotonic()
        try:
            proposal = store.get(session_id).proposals.get(proposal_id)
            if proposal is not None and proposal.status.value != "pending":
                return {
                    "status": proposal.status.value,
                    "session_id": session_id,
                    "proposal_id": proposal_id,
                }
            while True:
                remaining = timeout_seconds - (time.monotonic() - start)
                if remaining <= 0:
                    return {
                        "status": "timeout",
                        "session_id": session_id,
                        "proposal_id": proposal_id,
                    }
                try:
                    event = q.get(timeout=min(1.0, remaining))
                except queue.Empty:
                    continue
                if (
                    event["type"] in ("proposal_accepted", "proposal_rejected")
                    and event.get("proposal_id") == proposal_id
                ):
                    return {"status": event["type"].removeprefix("proposal_"), **event}
        finally:
            store.unsubscribe(session_id, q)

    return mcp
