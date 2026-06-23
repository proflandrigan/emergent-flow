"""In-process service functions backing the local server (ADR 0013, §A6).

Pure-ish wrappers over the public ``cm.*`` entry points: each takes a parsed IR
graph (a JSON-native ``dict``) and returns a JSON-native ``dict``. There is no
HTTP here and no I/O of their own beyond what ``cm.execute`` performs, so they
are unit-testable without a running server and would be reused unchanged if the
transport is later upgraded from the stdlib server to FastAPI.

The happy path (§A6): the bundled app runs these *in-process* on localhost --
no Celery, no sandbox. Equivalence (ADR 0002) is unaffected; these only wrap the
already-tested pure functions and JSON-encode their results.
"""

from __future__ import annotations

import json
from typing import Any

from colonymind import compile_to_code, execute, validate
from colonymind.codegen.errors import CodegenError, UnboundInputError
from colonymind.codegen.traversal import topological_sort
from colonymind.codegen.validation import enforce_validation_gate
from colonymind.codegen.wiring import build_wiring_map
from colonymind.ir import Direction, Graph, Paradigm
from colonymind.ir.serialize import deserialize_graph
from colonymind.nodes import get as get_node_definition

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


def _fallback(obj: Any) -> Any:
    """Render an execute() artifact that is not JSON-native as safe summary data.

    ``cm.execute`` returns *inspectable* objects (ADR 0002), but inspectable is a
    superset of JSON-native: a DataFrame is inspectable yet not directly
    serializable. Prefer a structured ``to_dict()`` when the object offers one,
    else fall back to ``repr`` so a response never fails to encode.
    """
    to_dict = getattr(obj, "to_dict", None)
    if callable(to_dict):
        try:
            return to_dict()
        except Exception:
            return repr(obj)
    return repr(obj)


def _jsonable(value: Any) -> Any:
    """Best-effort coercion of an execute() result into JSON-native data."""
    return json.loads(json.dumps(value, default=_fallback))


def compile_graph(payload: dict[str, Any]) -> dict[str, Any]:
    """IR graph (as a dict) -> ``{"code": <generated Python>}``."""
    return {"code": compile_to_code(_to_graph(payload))}


def validate_graph(payload: dict[str, Any]) -> dict[str, Any]:
    """IR graph (as a dict) -> ``{"diagnostics": <Diagnostics, JSON-native>}``."""
    return {"diagnostics": validate(_to_graph(payload)).model_dump(mode="json")}


def _execute_functional_with_status(
    graph: Graph,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Walk a FUNCTIONAL graph node by node, capturing a per-node run status.

    Mirrors ``colonymind.codegen.executor.execute``'s FUNCTIONAL walk exactly,
    except a single node's runtime failure is recorded as that node's "error"
    status (and downstream nodes as "skipped") instead of aborting the whole
    run. Graph-level guards (validation gate, paradigm, cycle, unbound input)
    still raise so the caller can map them to an HTTP 422.
    """
    enforce_validation_gate(graph)
    if graph.paradigm is not Paradigm.FUNCTIONAL:
        raise CodegenError(f"expected FUNCTIONAL graph, got {graph.paradigm}")
    for node in graph.nodes.values():
        if node.paradigm is not Paradigm.FUNCTIONAL:
            raise CodegenError(f"node {node.id} is not FUNCTIONAL")
    topo_order_ids = topological_sort(graph)
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
            src = wiring_map.upstream(node.id, port.id)[0]
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


def execute_graph(payload: dict[str, Any]) -> dict[str, Any]:
    """IR graph (as a dict) -> ``{"results": ..., "statuses": ...}``.

    Runs the whole graph in-process (Epic 4 Story 2). FUNCTIONAL graphs are walked
    node by node so a single node's runtime failure is reported as that node's
    ``error`` status (downstream nodes ``skipped``) at HTTP 200, rather than
    aborting the whole run -- the canvas colours nodes from ``statuses``. Graph-LEVEL
    rejections (validation gate, cycle, unbound input, wrong paradigm) still raise
    and surface as the server's 422. No caching yet (roadmap Epic 7 seam).
    """
    graph = _to_graph(payload)
    if graph.paradigm is Paradigm.FUNCTIONAL:
        results, statuses = _execute_functional_with_status(graph)
        return {"results": _jsonable(results), "statuses": statuses}
    # DECLARATIVE (and any future paradigm): delegate to the reference executor,
    # which is all-or-nothing. On success the single nn.module node is "ok"; its
    # rejections raise (CodegenError) -> 422.
    results = execute(graph)
    statuses = {node_id: {"status": _STATUS_OK} for node_id in results}
    return {"results": _jsonable(results), "statuses": statuses}
