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

import json
import queue
import time
from typing import Any
from urllib.parse import quote

# Shared base URL used to build the ``open_in_ui`` browser links on agent-created
# sessions. ``emergentflow.server.app`` imports this same value so the HTTP and MCP
# paths agree, and ``serve()`` overwrites it with the real bind host/port when a
# live server starts on a non-default address. The default matches the localhost
# bind the canvas normally runs on.
OPEN_IN_UI_BASE = "http://127.0.0.1:8765"

# True only inside a live ``emergentflow serve`` process (set by ``serve()``), i.e. when MCP tools
# run against the SAME session store the canvas reads. The in-process stdio server
# (``create_mcp_server().run()``) has its own store, so a focused link from it would open a
# session the canvas has never heard of; tools omit ``view_url`` in that case (issue #168).
CANVAS_ATTACHED = False

_REACH_ALIASES = {
    "up": "up",
    "upstream": "up",
    "down": "down",
    "downstream": "down",
    "both": "both",
}


def _encode_view_id(value: str) -> str:
    """Percent-encode one id for the view hash (``~`` and ``,`` are delimiters, so encode them)."""
    return quote(value, safe="").replace("~", "%7E")


def build_view_url(
    session_id: str,
    *,
    focus: str | list[str] | None = None,
    reach: str | None = None,
    route: tuple[str, str] | list[str] | None = None,
    lens: str | list[str] | None = None,
    edge: str | None = None,
    proposal: str | None = None,
    review: str | None = None,
    tour: str | None = None,
    step: int | None = None,
) -> str:
    """Return a canvas URL for *session_id*, optionally deep-linked to a view (issue #168).

    The view state lives in the URL hash, keys ``&``-separated in this fixed order:
    ``focus=<id>[,<id>...]``, ``reach=up|down|both`` (requires ``focus``),
    ``route=<from>~<to>``, ``lens=<fam>[~<fam>...]``, ``edge=<id>``, ``proposal=<id>``,
    ``review=<id>``, ``tour=<id>``, ``step=<n>`` (``step`` requires ``tour``; defaults to 0).
    Each id is percent-encoded individually (``~`` and ``,`` included).
    The hash is view state only -- it never carries or alters the graph IR.

    With no view arguments the result is byte-identical to the historical ``open_in_ui``
    (``<base>/?session=<id>``). The base is read at call time.
    """
    base = f"{OPEN_IN_UI_BASE}/?session={session_id}"
    focus_ids = [focus] if isinstance(focus, str) else list(focus or [])
    focus_ids = [f for f in focus_ids if f]
    lens_ids = [lens] if isinstance(lens, str) else list(lens or [])
    lens_ids = [x for x in lens_ids if x]

    reach_norm: str | None = None
    if reach:
        reach_norm = _REACH_ALIASES.get(reach.strip().lower())
        if reach_norm is None:
            raise ValueError(f"reach must be one of up, down, both; got {reach!r}")
        if not focus_ids:
            raise ValueError("reach requires focus")

    route_ids: list[str] = []
    if route is not None:
        route_ids = list(route)
        if len(route_ids) != 2 or not all(route_ids):
            raise ValueError("route must be a (from_id, to_id) pair")

    if step is not None:
        if not tour:
            raise ValueError("step requires tour")
        if isinstance(step, bool) or not isinstance(step, int) or step < 0:
            raise ValueError("step must be a non-negative integer")

    parts: list[str] = []
    if focus_ids:
        parts.append("focus=" + ",".join(_encode_view_id(f) for f in focus_ids))
    if reach_norm:
        parts.append(f"reach={reach_norm}")
    if route_ids:
        parts.append("route=" + "~".join(_encode_view_id(r) for r in route_ids))
    if lens_ids:
        parts.append("lens=" + "~".join(_encode_view_id(x) for x in lens_ids))
    if edge:
        parts.append("edge=" + _encode_view_id(edge))
    if proposal:
        parts.append("proposal=" + _encode_view_id(proposal))
    if review:
        parts.append("review=" + _encode_view_id(review))
    if tour:
        parts.append("tour=" + _encode_view_id(tour))
        parts.append(f"step={0 if step is None else step}")

    return base + "#" + "&".join(parts) if parts else base


def _with_view_url(result: dict[str, Any], session_id: str, **view: Any) -> dict[str, Any]:
    """Add a focused ``view_url`` to a mutating tool's *result* when a canvas shares the store.

    Omitted when ``CANVAS_ATTACHED`` is False (the stdio-only MCP server keeps its own session
    store, so the link would open a session the canvas never saw -- issue #168).
    """
    if CANVAS_ATTACHED:
        result["view_url"] = build_view_url(session_id, **view)
    return result


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

    from emergentflow.codegen.mermaid import to_mermaid
    from emergentflow.collab.review import ReviewThread
    from emergentflow.collab.session import OpenGatesError, UnknownProposalError
    from emergentflow.collab.session import get_default_store as get_default_session_store
    from emergentflow.collab.tours import Tour
    from emergentflow.ir.common import Direction, new_id
    from emergentflow.ir.edge import Edge, PortRef
    from emergentflow.ir.mutation import GraphMutation
    from emergentflow.ir.node import Position
    from emergentflow.nodes import registry as default_node_registry
    from emergentflow.server.service import (
        compile_graph,
        compile_session,  # ADD
        execute_node,  # ADD
        execute_session,  # ADD
        get_catalog,
        get_knowledge_entry,
        list_knowledge,
        save_knowledge,
        validate_graph,
    )

    @mcp.tool()
    def get_graph(session_id: str) -> dict:
        """Return the full session document for *session_id* (same as GET /sessions/{id})."""
        session = get_default_session_store().get(session_id)
        return session.model_dump(mode="json")

    @mcp.tool()
    def get_graph_mermaid(session_id: str, highlight: list[str] | None = None) -> dict:
        """Render the session's current graph as a Mermaid flowchart (ef.to_mermaid, issue #169).

        Returns {"mermaid": "<flowchart source>", "markdown": "```mermaid ...```"}. Paste
        ``markdown`` into a PR description, issue, or chat reply so reviewers see the pipeline
        as a diagram. ``highlight`` lists node ids to emphasise (e.g. the nodes you changed).
        """
        session = get_default_session_store().get(session_id)
        source = to_mermaid(session.graph, highlight=highlight or ())
        return {"mermaid": source, "markdown": f"```mermaid\n{source}```\n"}

    @mcp.tool()
    def list_sessions() -> dict:
        """List every active session (same as GET /sessions)."""
        sessions = get_default_session_store().list()
        return {"sessions": [s.model_dump(mode="json") for s in sessions]}

    @mcp.tool()
    def create_session(graph: dict | None = None) -> dict:
        """Create a collaboration session, optionally seeded with an IR *graph* dict.

        Returns the session document plus ``open_in_ui``: a ready-to-open browser URL of the
        form ``http://127.0.0.1:8765/?session=<id>`` that a human can click to view this
        session on the canvas. Use this rather than a raw ``POST /sessions`` when building a
        new flow through MCP.
        """
        import json

        from emergentflow.ir import deserialize_graph

        graph_obj = deserialize_graph(json.dumps(graph)) if graph is not None else None
        session = get_default_session_store().create(graph_obj)
        doc = session.model_dump(mode="json")
        doc["open_in_ui"] = build_view_url(session.id)
        return doc

    @mcp.tool()
    def view_link(
        session_id: str,
        focus: list[str] | None = None,
        reach: str | None = None,
        route: list[str] | None = None,
        lens: list[str] | None = None,
        edge: str | None = None,
        proposal: str | None = None,
        review: str | None = None,
        tour: str | None = None,
        step: int | None = None,
    ) -> dict:
        """Build a canvas deep link that opens *session_id* on a specific view (issue #168).

        *focus* is a list of node ids to select and centre; *reach* is ``up``, ``down`` or
        ``both`` (requires *focus*); *route* is ``[from_id, to_id]``; *lens* is a list of
        family names; *edge*, *proposal* and *review* are ids to open; *tour* is a guided-tour
        id and *step* the zero-based step to open (requires *tour*; defaults to 0). End a
        turn with this link instead of a prose recap so the human lands on the change.

        Returns ``{"view_url", "canvas_reachable", "note"}``; when ``canvas_reachable`` is
        False this MCP server is not running inside ``emergentflow serve`` and the link only
        works if the human's canvas shares this session store.
        """
        get_default_session_store().get(session_id)  # raises for an unknown session
        url = build_view_url(
            session_id,
            focus=focus,
            reach=reach,
            route=route,
            lens=lens,
            edge=edge,
            proposal=proposal,
            review=review,
            tour=tour,
            step=step,
        )
        note = (
            "Open this link in the canvas served by `emergentflow serve`."
            if CANVAS_ATTACHED
            else "This MCP server is not attached to a running canvas (stdio mode keeps its own "
            "session store); the link only resolves if the canvas shares this session. Use the "
            "HTTP bridge (`emergentflow.collab.mcp_bridge`) for working links."
        )
        return {"view_url": url, "canvas_reachable": CANVAS_ATTACHED, "note": note}

    @mcp.tool()
    def get_catalog_tool() -> dict:
        """Return the versioned node catalog (same as GET /catalog)."""
        return get_catalog()

    @mcp.tool()
    def validate_graph_tool(graph: dict) -> dict:
        """Validate an IR graph and return diagnostics (same as POST /validate)."""
        return validate_graph(graph)

    @mcp.tool()
    def run_validity_checks_tool(graph: dict) -> dict:
        """Run validity rules over a graph and return findings.

        Checks for issues like data leakage, train/test contamination, and
        methodological errors. Returns a list of findings with rule_id, severity,
        message, and implicated node_ids.
        """
        import json

        from emergentflow.ir import deserialize_graph
        from emergentflow.validity.runner import run_validity_checks

        graph_obj = deserialize_graph(json.dumps(graph))
        findings = run_validity_checks(graph_obj)
        return {
            "findings": [
                {
                    "rule_id": f.rule_id,
                    "severity": f.severity,
                    "message": f.message,
                    "node_id": f.node_id,
                    "related_node_ids": f.related_node_ids or [],
                }
                for f in findings
            ]
        }

    @mcp.tool()
    def compile_preview(graph: dict) -> dict:
        """Compile an IR graph to Python code (same as POST /compile)."""
        return compile_graph(graph)

    @mcp.tool()
    def compile_session_tool(session_id: str) -> dict:
        """Compile the session's current graph to Python code (same as POST /sessions/{id}/compile).

        Returns {"code": "..."} on success, or {"blocked_by_gates": [...]} if any gate is OPEN.
        """
        try:
            return compile_session(session_id)
        except OpenGatesError as exc:
            return {
                "blocked_by_gates": [
                    {
                        "gate_id": g.id,
                        "phase": g.phase,
                        "kind": g.kind.value,
                        "description": g.description,
                    }
                    for g in exc.open_gates
                ]
            }

    @mcp.tool()
    def execute_session_tool(
        session_id: str,
        run_to: list[str] | None = None,
        run_from: list[str] | None = None,
        run_only: list[str] | None = None,
    ) -> dict:
        """Execute the session's current graph (same as POST /sessions/{id}/execute).

        Optional partial-execution scopes (mutually exclusive):
        - run_to: execute up to and including these node ids
        - run_from: execute from these node ids onward
        - run_only: execute only these node ids

        Returns {"payload_version", "results", "statuses"} on success,
        or {"blocked_by_gates": [...]} if any gate is OPEN.

        Reply with the metric that answers the question and a canvas link, not this payload; check
        ``statuses`` before saying the run succeeded.
        """
        payload: dict[str, Any] = {}
        if run_to is not None:
            payload["run_to"] = run_to
        if run_from is not None:
            payload["run_from"] = run_from
        if run_only is not None:
            payload["run_only"] = run_only
        try:
            return execute_session(session_id, payload)
        except OpenGatesError as exc:
            return {
                "blocked_by_gates": [
                    {
                        "gate_id": g.id,
                        "phase": g.phase,
                        "kind": g.kind.value,
                        "description": g.description,
                    }
                    for g in exc.open_gates
                ]
            }

    @mcp.tool()
    def get_results(run_id: str) -> dict:
        """Fetch execution results for a run, digested for agent consumption.

        Returns bounded summaries: scalars verbatim, tables as shape+head,
        images as presence markers. Raises UnknownRunError if run_id doesn't exist.

        Quote the conclusion (metric, split, baseline) in your reply, not the digest.
        """
        from emergentflow.collab.digest import digest_results
        from emergentflow.server.runs import UnknownRunError, get_default_runs

        try:
            run_store = get_default_runs()
            payloads = run_store.get_payloads(run_id)
            return {
                "run_id": run_id,
                "results": digest_results(payloads),
            }
        except UnknownRunError:
            return {"error": f"Run {run_id!r} not found"}

    @mcp.tool()
    def execute_node_tool(
        session_id: str,
        node_id: str,
        inputs: dict[str, Any] | None = None,
    ) -> dict:
        """Execute a single node in *session_id*'s graph (same as POST /execute_node).

        Runs only that node's ``execute()`` with caller-supplied upstream ``inputs``
        (keyed by IN-port name) and returns the same ``{"payload_version", "results",
        "statuses"}`` shape as the HTTP route. Raises ``UnknownSessionError`` for an
        unknown session and ``CodegenError`` for a bad envelope / unknown node id /
        non-FUNCTIONAL node.
        """
        session = get_default_session_store().get(session_id)
        payload = {
            "graph": session.graph.model_dump(mode="json"),
            "run_node": node_id,
            "inputs": inputs if inputs is not None else {},
        }
        return execute_node(payload)

    @mcp.tool()
    def get_node_outputs(
        run_id: str,
        node_ids: list[str],
    ) -> dict:
        """Fetch raw execution payloads for specific nodes in a run.

        Returns ``{"run_id", "outputs": {node_id: {port_name: payload}}}`` for the
        requested ``node_ids`` that exist in the run, so the agent can read scalars
        and tables directly without parsing the whole result payload. Returns
        ``{"error": ...}`` if *run_id* doesn't exist.
        """
        from emergentflow.server.runs import UnknownRunError, get_default_runs

        try:
            payloads = get_default_runs().get_payloads(run_id)
        except UnknownRunError:
            return {"error": f"Run {run_id!r} not found"}
        return {
            "run_id": run_id,
            "outputs": {node_id: payloads[node_id] for node_id in node_ids if node_id in payloads},
        }

    @mcp.tool()
    def fetch_artifact(handle: str) -> dict:
        """Fetch the raw bytes of an artifact by handle.

        Artifact handles are returned by get_results in digest form (e.g.,
        "image:800x600", "html:12345bytes"). This tool retrieves the full artifact.

        Note: Full artifact storage is not yet implemented. This tool returns a
        placeholder response. Future work will wire this to .ef-artifacts/ storage.
        """
        return {
            "error": "Artifact fetching not yet implemented",
            "handle": handle,
            "message": (
                "Full artifact storage requires wiring the execution pipeline to save "
                "artifacts to .ef-artifacts/ and mapping handles to file paths. "
                "For now, use the digest summaries from get_results."
            ),
        }

    @mcp.tool()
    def get_metric(run_id: str, node_id: str, metric_name: str) -> dict:
        """Extract a named scalar metric from a run's payloads.

        Returns {"run_id", "node_id", "metric_name", "value"} or error if not found.

        Say which split the metric came from; a training-set metric must be disclosed as such.
        """
        from emergentflow.collab.metrics import extract_metric
        from emergentflow.server.runs import UnknownRunError, get_default_runs

        try:
            run_store = get_default_runs()
            payloads = run_store.get_payloads(run_id)
            value = extract_metric(payloads, node_id, metric_name)

            if value is None:
                return {
                    "error": f"Metric {metric_name!r} not found in node {node_id!r}",
                    "run_id": run_id,
                    "node_id": node_id,
                    "metric_name": metric_name,
                }

            return {
                "run_id": run_id,
                "node_id": node_id,
                "metric_name": metric_name,
                "value": value,
            }
        except UnknownRunError:
            return {"error": f"Run {run_id!r} not found"}

    @mcp.tool()
    def compare_runs(
        run_id_a: str,
        run_id_b: str,
        node_id: str,
        metric_name: str,
    ) -> dict:
        """Compare a metric across two runs.

        Returns {"before", "after", "delta", "delta_pct"} or error.
        """
        from emergentflow.collab.metrics import compare_metrics, extract_metric
        from emergentflow.server.runs import UnknownRunError, get_default_runs

        try:
            run_store = get_default_runs()
            payloads_a = run_store.get_payloads(run_id_a)
            payloads_b = run_store.get_payloads(run_id_b)

            value_a = extract_metric(payloads_a, node_id, metric_name)
            value_b = extract_metric(payloads_b, node_id, metric_name)

            comparison = compare_metrics(value_a, value_b)
            comparison["run_id_a"] = run_id_a
            comparison["run_id_b"] = run_id_b
            comparison["node_id"] = node_id
            comparison["metric_name"] = metric_name

            return comparison
        except UnknownRunError as exc:
            return {"error": str(exc)}

    @mcp.tool()
    def record_attempt_tool(
        session_id: str,
        mutation_id: str,
        run_id: str | None = None,
        metric_name: str | None = None,
        metric_value: float | int | None = None,
        verdict: str = "pending",
        hypothesis: str = "",
    ) -> dict:
        """Record an experiment attempt in the session's attempt ledger.

        Writes an ``Attempt`` to ``GraphSession.collab.attempts`` (the closed-loop ledger:
        mutation -> run -> metric -> verdict) and publishes an ``attempt_recorded`` event so
        the canvas timeline reflects it. Returns the stored Attempt dict.
        """
        from emergentflow.collab.review import Attempt, AttemptVerdict
        from emergentflow.collab.session import get_default_store

        try:
            verdict_enum = AttemptVerdict(verdict)
        except ValueError:
            expected = ", ".join(v.value for v in AttemptVerdict)
            raise ValueError(f"invalid verdict {verdict!r}; expected one of {expected}") from None
        attempt = Attempt(
            mutation_id=mutation_id,
            run_id=run_id,
            metric_name=metric_name,
            metric_value=metric_value,
            verdict=verdict_enum,
            hypothesis=hypothesis,
        )
        stored = get_default_store().record_attempt(session_id, attempt)
        return stored.model_dump(mode="json")

    @mcp.tool()
    def save_knowledge_tool(entry: dict) -> dict:
        """Save a knowledge entry (same as POST /knowledge)."""
        return save_knowledge(entry)

    @mcp.tool()
    def list_knowledge_tool(
        in_type: str | None = None,
        out_type: str | None = None,
        tag: str | None = None,
    ) -> dict:
        """List knowledge entries by in_type/out_type/tag (same as GET /knowledge)."""
        return list_knowledge(in_type=in_type, out_type=out_type, tag=tag)

    @mcp.tool()
    def get_knowledge_entry_tool(slug: str) -> dict:
        """Return a single knowledge entry by slug (same as GET /knowledge/{slug})."""
        return get_knowledge_entry(slug)

    @mcp.tool()
    def propose_mutation(session_id: str, mutation: dict) -> dict:
        """Propose a graph mutation on *session_id* (same as POST /sessions/{id}/proposals).

        Returns the proposal plus ``view_url`` (a canvas link focused on the change) when a
        live canvas shares the session store.

        Lead your reply with ``view_url``; the change is pending until the human accepts it.
        """
        mutation_obj = GraphMutation.model_validate(mutation)
        proposal = get_default_session_store().add_proposal(session_id, mutation_obj)
        return _with_view_url(proposal.model_dump(mode="json"), session_id, proposal=proposal.id)

    @mcp.tool()
    def post_review(session_id: str, review: dict) -> dict:
        """Post a review thread on *session_id* (same as POST /sessions/{id}/reviews)."""
        thread = ReviewThread.model_validate(review)
        result = get_default_session_store().add_review(session_id, thread)
        return result.model_dump(mode="json")

    @mcp.tool()
    def set_tour(session_id: str, tour: dict) -> dict:
        """Create or replace a guided tour on *session_id* (issue #171).

        Payload: ``title``, ``conclusion`` (markdown, shown first), ``author`` and ``steps``,
        each step ``{focus: [node ids], reach?: up|down|both, route?: [from, to], note:
        markdown, unknowns: [str]}``. The same tour ``id`` replaces the existing tour, never
        duplicates it. Every focus/route id must be a top-level node of the current graph or
        the call fails naming all missing ids. Returns the stored tour, plus ``view_url``
        (``#tour=<id>&step=0``) when a canvas is attached.
        """
        stored = get_default_session_store().upsert_tour(session_id, Tour.model_validate(tour))
        return _with_view_url(stored.model_dump(mode="json"), session_id, tour=stored.id, step=0)

    @mcp.tool()
    def list_tours(session_id: str) -> dict:
        """List the guided tours on *session_id*, ordered by id.

        Each tour carries a ``view_url`` when a canvas is attached.
        """
        tours = get_default_session_store().list_tours(session_id)
        return {
            "tours": [
                _with_view_url(t.model_dump(mode="json"), session_id, tour=t.id, step=0)
                for t in tours
            ]
        }

    @mcp.tool()
    def await_verdict(session_id: str, proposal_id: str, timeout_seconds: float = 30.0) -> dict:
        """Long-poll for a proposal verdict on *session_id* (same as the SSE events route).

        Subscribes to the session's event queue BEFORE checking the proposal's current
        status, so a verdict that lands between the check and the subscribe is never
        missed -- then waits up to *timeout_seconds* for a ``proposal_accepted`` or
        ``proposal_rejected`` event whose ``proposal_id`` matches. Returns immediately
        if the proposal already has a verdict (e.g. it was resolved before this tool was
        called) or when a matching event arrives, else ``{"status": "timeout", ...}``
        once the deadline is exceeded. Raises ``UnknownProposalError`` immediately for an
        unknown *proposal_id* rather than blocking for the full timeout. The wait is
        capped at 600 seconds, and a negative *timeout_seconds* raises ``ValueError``.
        """
        if timeout_seconds < 0:
            raise ValueError("timeout_seconds must be non-negative")
        timeout_seconds = min(timeout_seconds, 600.0)
        store = get_default_session_store()
        q = store.subscribe(session_id)
        start = time.monotonic()
        try:
            if proposal_id not in store.get(session_id).proposals:
                raise UnknownProposalError(
                    f"no proposal with id {proposal_id!r} on session {session_id!r}."
                )
            proposal = store.get(session_id).proposals[proposal_id]
            if proposal.status.value != "pending":
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

    # ------------------------------------------------------------------
    # Fine-grained graph-editing tools (Task 03)
    #
    # Each tool builds a GraphMutation and applies it directly through
    # SessionStore.apply_direct_mutation, so the UI sees a graph_changed
    # event and a checkpoint is recorded automatically. Every success
    # response carries the common shape {session_id, version,
    # checkpoint_id} plus tool-specific id fields. Validation/session
    # errors (UnknownSessionError, StaleVersionError, MutationError,
    # KeyError for unknown node types) propagate so FastMCP surfaces a
    # ToolError; only expected "not found" port lookups are caught and
    # re-raised as ValueError.
    # ------------------------------------------------------------------

    def _find_port(node, port_name: str, direction: Direction | None = None):
        """Return the port on *node* named *port_name*, preferring *direction* if given.

        Some node types expose an in-port and an out-port with the same name (e.g.
        ``clean.explode_lists`` has an in ``frame`` and an out ``frame``), so a bare name
        match is ambiguous. When *direction* is supplied, prefer a port whose name AND
        direction match; fall back to a same-name port of any direction only if needed.
        """
        if direction is not None:
            for port in node.ports:
                if port.name == port_name and port.direction == direction:
                    return port
        for port in node.ports:
            if port.name == port_name:
                return port
        raise ValueError(
            f"node {node.id!r} ({node.type}) has no port named {port_name!r}; "
            f"available ports: {sorted(p.name for p in node.ports)!r}"
        )

    def _normalize_result_card_blocks(
        graph: Any, blocks: list[dict]
    ) -> tuple[list[dict], list[tuple[str, str]]]:
        """Validate agent-friendly result-card *blocks* and convert to the stored format.

        Returns ``(stored_blocks, pairs)`` where ``pairs`` is the unique, ordered list of
        referenced ``(node_id, port_name)`` OUT ports. Raises ``ValueError`` on bad input.
        """
        stored: list[dict] = []
        pairs: list[tuple[str, str]] = []
        for i, block in enumerate(blocks):
            if not isinstance(block, dict):
                raise ValueError(f"block {i} must be an object, got {type(block).__name__}")
            kind = block.get("kind")
            if kind == "markdown":
                text = block.get("text")
                if not isinstance(text, str):
                    raise ValueError(f"block {i}: markdown block requires a string 'text'")
                stored.append({"kind": "markdown", "text": text})
            elif kind == "result":
                node_id = block.get("node_id")
                port_name = block.get("port_name")
                if not isinstance(node_id, str) or not node_id:
                    raise ValueError(f"block {i}: result block requires 'node_id'")
                if not isinstance(port_name, str) or not port_name:
                    raise ValueError(f"block {i}: result block requires 'port_name'")
                if node_id not in graph.nodes:
                    raise ValueError(f"block {i}: unknown node_id {node_id!r}")
                port = _find_port(graph.nodes[node_id], port_name, Direction.OUT)
                if port.direction != Direction.OUT:
                    raise ValueError(
                        f"block {i}: port {port_name!r} on node {node_id!r} is not an OUT port"
                    )
                stored.append(
                    {
                        "kind": "result",
                        "source": f"{node_id}:{port_name}",
                        "caption": str(block.get("caption") or ""),
                    }
                )
                if (node_id, port_name) not in pairs:
                    pairs.append((node_id, port_name))
            else:
                raise ValueError(
                    f"block {i}: unknown kind {kind!r}; expected 'markdown' or 'result'"
                )
        return stored, pairs

    def _apply_mutation(
        session_id: str,
        mutation: GraphMutation,
        *,
        extra: dict[str, Any] | None = None,
    ) -> dict:
        """Apply *mutation* directly to *session_id* and return the common success shape.

        *mutation* carries its own ``author``/``description`` and a ``base_version``
        that ``apply_direct_mutation`` checks against the session's current version.
        Returns ``{session_id, version, checkpoint_id}`` plus any tool-specific
        ``extra`` id fields.
        """
        session, checkpoint = get_default_session_store().apply_direct_mutation(
            session_id,
            mutation,
            author=mutation.author,
            description=mutation.description,
        )
        result: dict[str, Any] = {
            "session_id": session_id,
            "version": session.version,
            "checkpoint_id": checkpoint.id,
        }
        if extra:
            result.update(extra)
        return result

    @mcp.tool()
    def add_node(
        session_id: str,
        node_type: str,
        *,
        label: str | None = None,
        params: dict[str, Any] | None = None,
        position: dict[str, float] | None = None,
        author: str = "agent",
        reason: str = "",
    ) -> dict:
        """Add a node of *node_type* to *session_id*'s graph.

        *params* are JSON-native param overrides passed straight to the node
        definition's ``instantiate``. *position* optionally overrides the
        node's canvas coordinates. Returns the common success shape plus the
        new ``node_id``, plus ``view_url`` (a canvas link focused on the change) when a
        live canvas shares the session store.
        """
        store = get_default_session_store()
        session = store.get(session_id)
        definition_cls = default_node_registry.get(node_type)
        node = definition_cls().instantiate(label=label or definition_cls.label, **(params or {}))
        if position is not None:
            node.position = Position(x=position["x"], y=position["y"])
        mutation = GraphMutation(
            base_version=session.version,
            add_nodes=[node],
            description=reason,
            author=author,
        )
        return _with_view_url(
            _apply_mutation(session_id, mutation, extra={"node_id": node.id}),
            session_id,
            focus=node.id,
        )

    @mcp.tool()
    def connect_ports(
        session_id: str,
        source_node_id: str,
        source_port_name: str,
        target_node_id: str,
        target_port_name: str,
        *,
        author: str = "agent",
        reason: str = "",
    ) -> dict:
        """Connect an OUT port on *source_node_id* to an IN port on *target_node_id*.

        Port names are resolved to their IR port ids before the edge is built.
        Returns the common success shape plus the new ``edge_id``, plus ``view_url`` (a
        canvas link focused on the change) when a live canvas shares the session store.
        """
        store = get_default_session_store()
        session = store.get(session_id)
        graph = session.graph
        source_node = graph.nodes[source_node_id]
        target_node = graph.nodes[target_node_id]
        source_port = _find_port(source_node, source_port_name, Direction.OUT)
        target_port = _find_port(target_node, target_port_name, Direction.IN)
        edge = Edge(
            id=new_id(),
            source=PortRef(node_id=source_node_id, port_id=source_port.id),
            target=PortRef(node_id=target_node_id, port_id=target_port.id),
        )
        mutation = GraphMutation(
            base_version=session.version,
            add_edges=[edge],
            description=reason,
            author=author,
        )
        return _with_view_url(
            _apply_mutation(session_id, mutation, extra={"edge_id": edge.id}),
            session_id,
            focus=[source_node_id, target_node_id],
            edge=edge.id,
        )

    @mcp.tool()
    def set_param(
        session_id: str,
        node_id: str,
        param_name: str,
        value: Any,
        *,
        author: str = "agent",
        reason: str = "",
    ) -> dict:
        """Set *param_name* to *value* on *node_id* in *session_id*'s graph.

        Returns the common success shape plus the edited ``node_id``, plus ``view_url`` (a
        canvas link focused on the change) when a live canvas shares the session store.
        """
        store = get_default_session_store()
        session = store.get(session_id)
        mutation = GraphMutation(
            base_version=session.version,
            set_params={node_id: {param_name: value}},
            description=reason,
            author=author,
        )
        return _with_view_url(
            _apply_mutation(session_id, mutation, extra={"node_id": node_id}),
            session_id,
            focus=node_id,
        )

    @mcp.tool()
    def delete_node(
        session_id: str,
        node_id: str,
        *,
        author: str = "agent",
        reason: str = "",
    ) -> dict:
        """Delete *node_id* from *session_id*'s graph, along with every incident edge.

        Returns the common success shape plus the removed ``node_id``.
        """
        store = get_default_session_store()
        session = store.get(session_id)
        graph = session.graph
        edge_ids = [
            edge_id
            for edge_id, edge in graph.edges.items()
            if edge.source.node_id == node_id or edge.target.node_id == node_id
        ]
        mutation = GraphMutation(
            base_version=session.version,
            remove_nodes=[node_id],
            remove_edges=edge_ids,
            description=reason,
            author=author,
        )
        return _apply_mutation(session_id, mutation, extra={"node_id": node_id})

    @mcp.tool()
    def delete_edge(
        session_id: str,
        edge_id: str,
        *,
        author: str = "agent",
        reason: str = "",
    ) -> dict:
        """Delete *edge_id* from *session_id*'s graph.

        Returns the common success shape plus the removed ``edge_id``.
        """
        store = get_default_session_store()
        session = store.get(session_id)
        mutation = GraphMutation(
            base_version=session.version,
            remove_edges=[edge_id],
            description=reason,
            author=author,
        )
        return _apply_mutation(session_id, mutation, extra={"edge_id": edge_id})

    @mcp.tool()
    def add_note(
        session_id: str,
        content: str,
        *,
        anchor_id: str | None = None,
        color: str = "yellow",
        kind: str = "note",
        position: dict[str, float] | None = None,
        author: str = "agent",
        reason: str = "",
    ) -> dict:
        """Add a ``notes.markdown`` annotation node to *session_id*'s graph.

        *kind* is ``"note"`` (default) or ``"open-question"`` -- an open question renders with a
        ``?`` "Open question" badge whatever its *color* (``"orange"`` is the conventional
        swatch). *anchor_id* ties it to a node or edge; *position* (``{"x", "y"}``) places it,
        ideally beside the anchored node. *reason* is audit text on the mutation, not a note
        param. Returns the common success shape plus the new ``node_id``, plus ``view_url``
        (a canvas link focused on the note) when a live canvas shares the session store.

        For an unverified assumption or open question, anchor the note to the affected node so it
        stays visible on the canvas; mention it beside the claim in your reply.
        """
        store = get_default_session_store()
        session = store.get(session_id)
        definition = default_node_registry.get("notes.markdown")()
        note = definition.instantiate(content=content, anchor_id=anchor_id, color=color, kind=kind)
        errors = definition.validate_param_values(note)
        if errors:
            raise ValueError("; ".join(errors))
        if position is not None:
            note.position = Position(x=position["x"], y=position["y"])
        description = reason or f"Added note: {content[:80]}"
        mutation = GraphMutation(
            base_version=session.version,
            add_nodes=[note],
            description=description,
            author=author,
        )
        return _with_view_url(
            _apply_mutation(session_id, mutation, extra={"node_id": note.id}),
            session_id,
            focus=note.id,
        )

    @mcp.tool()
    def delete_note(
        session_id: str,
        note_node_id: str,
        *,
        author: str = "agent",
        reason: str = "",
    ) -> dict:
        """Delete the ``notes.markdown`` node *note_node_id* from *session_id*'s graph.

        Returns the common success shape plus the removed ``node_id``.
        """
        store = get_default_session_store()
        session = store.get(session_id)
        mutation = GraphMutation(
            base_version=session.version,
            remove_nodes=[note_node_id],
            description=reason,
            author=author,
        )
        return _apply_mutation(session_id, mutation, extra={"node_id": note_node_id})

    @mcp.tool()
    def add_result_card(
        session_id: str,
        title: str = "Results",
        blocks: list[dict] | None = None,
        *,
        author: str = "agent",
        reason: str = "",
    ) -> dict:
        """Add a ``reports.result_card`` node to *session_id*'s graph.

        *blocks* is a list of ``{"kind": "markdown", "text": ...}`` or
        ``{"kind": "result", "node_id": ..., "port_name": ..., "caption": ...}`` dicts.
        Each referenced OUT port is wired into the card's ``results`` IN port in the same
        mutation. Returns the common success shape plus the new ``node_id``, plus
        ``view_url`` (a canvas link focused on the change) when a live canvas shares the
        session store.

        Lead your reply with ``view_url`` and put the conclusion in the first markdown block.
        """
        store = get_default_session_store()
        session = store.get(session_id)
        graph = session.graph
        stored_blocks, pairs = _normalize_result_card_blocks(graph, blocks or [])
        card = default_node_registry.get("reports.result_card")().instantiate(
            title=title, blocks_json=json.dumps(stored_blocks)
        )
        in_port = _find_port(card, "results", Direction.IN)
        edges = [
            Edge(
                id=new_id(),
                source=PortRef(
                    node_id=src_id,
                    port_id=_find_port(graph.nodes[src_id], port_name, Direction.OUT).id,
                ),
                target=PortRef(node_id=card.id, port_id=in_port.id),
            )
            for src_id, port_name in pairs
        ]
        mutation = GraphMutation(
            base_version=session.version,
            add_nodes=[card],
            add_edges=edges,
            description=reason or f"Added result card: {title}",
            author=author,
        )
        return _with_view_url(
            _apply_mutation(session_id, mutation, extra={"node_id": card.id}),
            session_id,
            focus=card.id,
        )

    @mcp.tool()
    def set_result_card(
        session_id: str,
        card_node_id: str,
        blocks: list[dict],
        title: str | None = None,
        *,
        author: str = "agent",
        reason: str = "",
    ) -> dict:
        """Replace the blocks (and optionally the title) of a ``reports.result_card`` node.

        Edges are added only for referenced OUT ports not already wired into the card.
        Returns the common success shape plus the edited ``node_id``.
        """
        store = get_default_session_store()
        session = store.get(session_id)
        graph = session.graph
        card = graph.nodes.get(card_node_id)
        if card is None:
            raise ValueError(f"node {card_node_id!r} not found in session {session_id!r}")
        if card.type != "reports.result_card":
            raise ValueError(
                f"node {card_node_id!r} is of type {card.type!r}, not 'reports.result_card'"
            )
        stored_blocks, pairs = _normalize_result_card_blocks(graph, blocks)
        in_port = _find_port(card, "results", Direction.IN)
        wired: set[tuple[str, str]] = set()
        for edge in graph.edges.values():
            if edge.target.node_id != card_node_id:
                continue
            src_node = graph.nodes.get(edge.source.node_id)
            if src_node is None:
                continue
            for port in src_node.ports:
                if port.id == edge.source.port_id:
                    wired.add((src_node.id, port.name))
        edges = [
            Edge(
                id=new_id(),
                source=PortRef(
                    node_id=src_id,
                    port_id=_find_port(graph.nodes[src_id], port_name, Direction.OUT).id,
                ),
                target=PortRef(node_id=card_node_id, port_id=in_port.id),
            )
            for src_id, port_name in pairs
            if (src_id, port_name) not in wired
        ]
        params: dict[str, Any] = {"blocks_json": json.dumps(stored_blocks)}
        if title is not None:
            params["title"] = title
        mutation = GraphMutation(
            base_version=session.version,
            add_edges=edges,
            set_params={card_node_id: params},
            description=reason or f"Updated result card: {card_node_id}",
            author=author,
        )
        return _apply_mutation(session_id, mutation, extra={"node_id": card_node_id})

    return mcp
