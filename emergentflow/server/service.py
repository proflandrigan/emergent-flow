"""In-process service functions backing the local server (ADR 0013, §A6).

Pure-ish wrappers over the public ``ef.*`` entry points: each takes a parsed IR
graph (a JSON-native ``dict``) and returns a JSON-native ``dict``. There is no
HTTP here and no I/O of their own beyond what ``ef.execute`` performs, so they
are unit-testable without a running server and would be reused unchanged if the
transport is later upgraded from the stdlib server to FastAPI.

The happy path (§A6): the bundled app runs these *in-process* on localhost --
no Celery, no sandbox. Equivalence (ADR 0002) is unaffected; these only wrap the
already-tested pure functions and JSON-encode their results.
"""

from __future__ import annotations

import json
from typing import Any

from emergentflow import compile_to_code, execute, export_catalog, validate
from emergentflow.codegen.errors import CodegenError, UnboundInputError
from emergentflow.codegen.traversal import topological_sort
from emergentflow.codegen.validation import enforce_validation_gate
from emergentflow.codegen.wiring import WiringMap, build_wiring_map
from emergentflow.ir import Direction, Graph, Paradigm
from emergentflow.ir.schema import ir_json_schema
from emergentflow.ir.serialize import deserialize_graph
from emergentflow.nodes import get as get_node_definition
from emergentflow.server.payload import PAYLOAD_CONTRACT_VERSION, to_payload

# Per-node execution status reported to the canvas (Epic 4 Story 2). A node is
# "ok" if it ran, "error" if its execute() raised, "skipped" if an upstream node
# did not produce its inputs (error or skipped). Consumed by repo Epic 5 Story 8.
_STATUS_OK = "ok"
_STATUS_ERROR = "error"
_STATUS_SKIPPED = "skipped"


def _to_graph(payload: dict[str, Any]) -> Graph:
    # Route the dict back through deserialize_graph (rather than
    # Graph.model_validate) so the server applies the same schema-version checks
    # and migrations as the on-disk load path -- the two accept identical graphs.
    return deserialize_graph(json.dumps(payload))


def compile_graph(payload: dict[str, Any]) -> dict[str, Any]:
    """IR graph (as a dict) -> ``{"code": <generated Python>}``."""
    return {"code": compile_to_code(_to_graph(payload))}


def validate_graph(payload: dict[str, Any]) -> dict[str, Any]:
    """IR graph (as a dict) -> ``{"diagnostics": <Diagnostics, JSON-native>}``."""
    return {"diagnostics": validate(_to_graph(payload)).model_dump(mode="json")}


def get_schema() -> dict[str, Any]:
    """Return the IR JSON Schema (a serialized ``Graph``) for the canvas to consume.

    The canvas is a pure consumer of this contract (ADR 0013 Decision 3): it never imports
    ``emergentflow``; it reads this schema over HTTP (and at build time, see the export script).
    """
    return ir_json_schema()


def get_catalog() -> dict[str, Any]:
    """Return the versioned node catalog artifact (ADR 0015).

    Delegates to the single canonical builder ``ef.export_catalog`` so the server's
    ``GET /catalog``, the committed ``ui/src/generated/catalog.json``, and the SDK's
    ``ef.export_catalog()`` all serve byte-identical data -- one source of truth, no
    two-tier palette. Shape: ``{"catalog_version": <int>, "nodes": [<NodeSpec as JSON>, ...]}``,
    nodes sorted by ``type``. The palette (Epic 5 Story 3) and the schema-driven config
    panels (Story 4) render entirely from this -- no Python in the client.
    """
    return export_catalog()


def _ancestors(graph: Graph, targets: set[str], wiring_map: WiringMap) -> set[str]:
    """Return *targets* plus every node that transitively feeds their IN ports.

    The returned set is ancestor-closed: for any node in it, every node feeding
    one of its IN ports is also in it. This lets the functional walk run only the
    subgraph "up to and including" the targets ("run to here", Epic 4 Story 6)
    while the skip/dangling-input logic stays correct (every upstream source is present).
    """
    seen: set[str] = set()
    stack = list(targets)
    while stack:
        node_id = stack.pop()
        if node_id in seen:
            continue
        seen.add(node_id)
        node = graph.nodes[node_id]
        for port in node.ports:
            if port.direction != Direction.IN:
                continue
            for src in wiring_map.upstream(node.id, port.id):
                if src.node_id not in seen:
                    stack.append(src.node_id)
    return seen


def _execute_functional_with_status(
    graph: Graph,
    only: set[str] | None = None,
    wiring_map: WiringMap | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Walk a FUNCTIONAL graph node by node, capturing a per-node run status.

    Mirrors ``emergentflow.codegen.executor.execute``'s FUNCTIONAL walk exactly,
    except a single node's runtime failure is recorded as that node's "error"
    status (and downstream nodes as "skipped") instead of aborting the whole
    run. Graph-level guards (validation gate, paradigm, cycle, unbound input)
    still raise so the caller can map them to an HTTP 422.

    *wiring_map*, if given, is reused instead of rebuilt (the ``run_to`` caller
    already built one to resolve ancestors -- building it twice per request
    would double the wiring-map construction cost on the "fast incremental
    re-run" path that ``run_to`` exists for).
    """
    enforce_validation_gate(graph)
    if graph.paradigm is not Paradigm.FUNCTIONAL:
        raise CodegenError(f"expected FUNCTIONAL graph, got {graph.paradigm}")
    for node in graph.nodes.values():
        if node.paradigm is not Paradigm.FUNCTIONAL:
            raise CodegenError(f"node {node.id} is not FUNCTIONAL")
    topo_order_ids = topological_sort(graph)
    if only is not None:
        topo_order_ids = [nid for nid in topo_order_ids if nid in only]
    if wiring_map is None:
        wiring_map = build_wiring_map(graph)
    # Dangling-input guard (raises UnboundInputError -> 422).
    for node_id in topo_order_ids:
        node = graph.nodes[node_id]
        for port in node.ports:
            if port.direction != Direction.IN:
                continue
            if not wiring_map.upstream(node.id, port.id):
                raise UnboundInputError(f"{node.id}.{port.id} has no upstream source")

    results: dict[str, dict[str, Any]] = {}
    statuses: dict[str, dict[str, Any]] = {}
    for node_id in topo_order_ids:
        node = graph.nodes[node_id]
        # If ANY upstream source node is not ok, this node is skipped (no run).
        # Because we iterate in topo order, every upstream node already has a status.
        inputs: dict[str, Any] = {}
        skipped = False
        for port in node.ports:
            if port.direction != Direction.IN:
                continue
            sources = wiring_map.upstream(node.id, port.id)
            if len(sources) > 1:
                raise ValueError(
                    f"IN port {port.name!r} on node {node.id!r} has {len(sources)} "
                    "sources; multi-source fan-in is not yet supported by codegen "
                    "context."
                )
            src = sources[0]
            if statuses[src.node_id]["status"] != _STATUS_OK:
                skipped = True
                break
            src_node = graph.nodes[src.node_id]
            src_port_name = next(p.name for p in src_node.ports if p.id == src.port_id)
            inputs[port.name] = results[src.node_id][src_port_name]
        if skipped:
            statuses[node_id] = {"status": _STATUS_SKIPPED}
            continue
        try:
            definition = get_node_definition(node.type)()
            results[node_id] = definition.execute(node, inputs)
            statuses[node_id] = {"status": _STATUS_OK}
        except Exception as exc:  # noqa: BLE001 - any node-runtime failure -> error status
            statuses[node_id] = {
                "status": _STATUS_ERROR,
                "error": f"{type(exc).__name__}: {exc}",
            }
    return results, statuses


def _results_to_payloads(
    results: dict[str, dict[str, Any]],
) -> dict[str, dict[str, dict[str, Any]]]:
    """Map each OUT-port artifact to its typed result payload (Story 3)."""
    return {
        node_id: {port_name: to_payload(value) for port_name, value in ports.items()}
        for node_id, ports in results.items()
    }


def _split_request(payload: dict[str, Any]) -> tuple[dict[str, Any], Any]:
    """Split an /execute body into (graph_dict, run_to).

    Backward compatible: a bare IR graph (no ``"graph"`` key) yields ``run_to=None``.
    An envelope ``{"graph": ..., "run_to": ...}`` selects the "run to here" subgraph.
    """
    if isinstance(payload.get("graph"), dict):
        return payload["graph"], payload.get("run_to")
    return payload, None


def execute_graph(payload: dict[str, Any]) -> dict[str, Any]:
    """IR graph (as a dict) -> ``{"payload_version", "results", "statuses"}``.

    Runs the whole graph in-process (Epic 4 Story 2). FUNCTIONAL graphs are walked
    node by node so a single node's runtime failure is reported as that node's
    ``error`` status (downstream nodes ``skipped``) at HTTP 200, rather than
    aborting the whole run -- the canvas colours nodes from ``statuses``. Graph-LEVEL
    rejections (validation gate, cycle, unbound input, wrong paradigm) still raise
    and surface as the server's 422. No caching yet (roadmap Epic 7 seam). Each
    OUT port in ``results`` is a typed result payload (Story 3), not a raw
    artifact; ``payload_version`` stamps the contract once at the top level.

    When the body is an envelope with ``run_to`` (a node id or list of ids), only the
    subgraph up to and including those nodes runs ("run to here", Epic 4 Story 6),
    reusing the Epic 2 traversal + wiring; the rest of the graph is left unrun.
    """
    graph_payload, run_to = _split_request(payload)
    graph = _to_graph(graph_payload)
    if graph.paradigm is Paradigm.FUNCTIONAL:
        only: set[str] | None = None
        wiring_map: WiringMap | None = None
        if run_to is not None:
            targets = {run_to} if isinstance(run_to, str) else set(run_to)
            missing = targets - set(graph.nodes)
            if missing:
                raise CodegenError(f"run_to targets not in graph: {sorted(missing)}")
            wiring_map = build_wiring_map(graph)
            only = _ancestors(graph, targets, wiring_map)
        results, statuses = _execute_functional_with_status(graph, only=only, wiring_map=wiring_map)
        return {
            "payload_version": PAYLOAD_CONTRACT_VERSION,
            "results": _results_to_payloads(results),
            "statuses": statuses,
        }
    if run_to is not None:
        raise CodegenError("run_to (run-to-here) is only supported for FUNCTIONAL graphs")
    # DECLARATIVE (and any future paradigm): delegate to the reference executor,
    # which is all-or-nothing. On success the single nn.module node is "ok"; its
    # rejections raise (CodegenError) -> 422.
    results = execute(graph)
    statuses = {node_id: {"status": _STATUS_OK} for node_id in results}
    return {
        "payload_version": PAYLOAD_CONTRACT_VERSION,
        "results": _results_to_payloads(results),
        "statuses": statuses,
    }


def execute_node(payload: dict[str, Any]) -> dict[str, Any]:
    """Execute a single node ("run this node", Epic 4 Story 6).

    Envelope body: ``{"graph": <ir>, "run_node": <node id>, "inputs": {<IN-port name>: value}}``.
    Runs only that node's ``execute()`` with caller-supplied upstream inputs and returns
    the same ``{"payload_version", "results", "statuses"}`` shape as ``execute_graph`` --
    but for the single node. The server is stateless (no cache yet -- roadmap Epic 7), so
    inputs come from the caller; rich inputs (DataFrames) round-trip faithfully only once
    the on-disk cache lands. A node-runtime failure is reported as that node's ``error``
    status at HTTP 200 (mirroring run-all); a bad envelope, unknown node id, or non-FUNCTIONAL
    node RAISES (-> the server's 422). DECLARATIVE nodes (e.g. ``nn.linear``) are rejected
    rather than run standalone: their ``execute()`` returns the bare layer object for the
    whole-graph declarative executor to compose, not a computed result, so running one in
    isolation would silently "succeed" with a meaningless payload instead of erroring.
    """
    graph_payload = payload.get("graph")
    if not isinstance(graph_payload, dict):
        raise CodegenError('execute_node requires an envelope: {"graph": ..., "run_node": ...}')
    node_id = payload.get("run_node")
    if node_id is None:
        raise CodegenError("execute_node requires 'run_node' (a node id)")
    inputs = payload.get("inputs")
    if inputs is None:
        inputs = {}
    if not isinstance(inputs, dict):
        raise CodegenError("execute_node 'inputs' must be an object keyed by IN-port name")
    graph = _to_graph(graph_payload)
    if node_id not in graph.nodes:
        raise CodegenError(f"run_node not in graph: {node_id!r}")
    node = graph.nodes[node_id]
    if node.paradigm is not Paradigm.FUNCTIONAL:
        raise CodegenError(
            f"execute_node only supports FUNCTIONAL nodes, got {node.paradigm} for {node_id!r}"
        )

    results: dict[str, dict[str, Any]] = {}
    try:
        definition = get_node_definition(node.type)()
        results[node_id] = definition.execute(node, inputs)
        status: dict[str, Any] = {"status": _STATUS_OK}
    except Exception as exc:  # noqa: BLE001 - any node-runtime failure -> error status
        status = {"status": _STATUS_ERROR, "error": f"{type(exc).__name__}: {exc}"}
    return {
        "payload_version": PAYLOAD_CONTRACT_VERSION,
        "results": _results_to_payloads(results),
        "statuses": {node_id: status},
    }
