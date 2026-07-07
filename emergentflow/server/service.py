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

import contextlib
import hashlib
import json
import time
from collections.abc import Generator, Iterator
from dataclasses import dataclass
from typing import Any, cast

import pandas as pd

from emergentflow import __version__, compile_to_code, execute, export_catalog, validate
from emergentflow.codegen.errors import CodegenError, UnboundInputError
from emergentflow.codegen.traversal import topological_sort
from emergentflow.codegen.validation import enforce_validation_gate
from emergentflow.codegen.wiring import WiringMap, build_wiring_map
from emergentflow.eval import label as eval_label
from emergentflow.eval.export import build_eval_set_rows, build_finetune_rows, rows_to_jsonl_bytes
from emergentflow.ir import Direction, Graph, Node, Paradigm
from emergentflow.ir.schema import ir_json_schema
from emergentflow.ir.serialize import deserialize_graph
from emergentflow.llm.gateway import GatewayClient
from emergentflow.llm.secrets import validate_api_keys_present
from emergentflow.nodes import get as get_node_definition
from emergentflow.server.cache import get_default_cache
from emergentflow.server.payload import PAYLOAD_CONTRACT_VERSION, to_payload
from emergentflow.server.reports import get_default_store


# Server-run nodes that declare `requires_client = True` (Epic 9, ADR 0017) get a
# real `GatewayClient` so "run this graph"/"run this node" over the local server
# actually reaches the provider, mirroring `emergentflow.codegen.executor.execute`'s
# `client` threading. `GatewayClient` itself only imports `litellm` lazily inside
# `complete()`, so importing the class here adds no hard dependency on the `llm` extra.
def _execute_node(definition: Any, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
    if type(definition).requires_client:
        return cast(Any, definition.execute)(node, inputs, client=GatewayClient())
    return cast(dict[str, Any], definition.execute(node, inputs))


# Per-node execution status reported to the canvas (Epic 4 Story 2). A node is
# "ok" if it ran, "error" if its execute() raised, "skipped" if an upstream node
# did not produce its inputs (error or skipped), "cached" if its outputs were
# served from the on-disk execution cache instead of being re-executed (Epic 7
# Story 6). Consumed by repo Epic 5 Story 8.
_STATUS_OK = "ok"
_STATUS_ERROR = "error"
_STATUS_SKIPPED = "skipped"
_STATUS_CACHED = "cached"


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


def label_eval(payload: dict[str, Any]) -> dict[str, Any]:
    """``POST /eval/label``: ``{"results": [...], "labels": [...]}`` -> ``{"labeled": [...]}``.

    Builds a DataFrame from each of ``payload["results"]``/``payload["labels"]`` (lists of
    row dicts, e.g. what the Prompt Lab compare grid already holds client-side after an
    ``ef.eval.run`` run and a batch of label clicks), merges them via
    ``emergentflow.eval.label.label`` (Epic 9 Story 6), and returns the merged rows as a
    JSON-native list of dicts (``DataFrame.to_dict(orient="records")``).
    """
    results_df = pd.DataFrame(payload.get("results", []))
    labels_df = pd.DataFrame(payload.get("labels", []))
    labeled_df = eval_label(results_df, labels_df)
    return {"labeled": labeled_df.to_dict(orient="records")}


def export_eval_set_bytes(payload: dict[str, Any]) -> bytes:
    """``POST /export/eval_set``: ``{"rows": [...]}`` -> raw eval-set JSONL bytes.

    ``build_eval_set_rows``/``rows_to_jsonl_bytes`` (``emergentflow.eval.export``) build the
    JSONL payload entirely in memory -- no filesystem access needed to answer an HTTP request,
    unlike ``export_eval_set``, which additionally writes those same bytes to a path for the
    SDK/CLI-facing use case.
    """
    df = pd.DataFrame(payload.get("rows", []))
    return rows_to_jsonl_bytes(build_eval_set_rows(df))


def export_finetune_bytes(payload: dict[str, Any]) -> bytes:
    """``POST /export/finetune``: ``{"rows": [...]}`` -> raw fine-tune JSONL bytes."""
    df = pd.DataFrame(payload.get("rows", []))
    return rows_to_jsonl_bytes(build_finetune_rows(df))


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
    two-tier palette. Shape: ``{"catalog_version": <int>, "nodes": [<NodeSpec as JSON>, ...],
    "estimators": [<estimator catalog entry, Epic 8>, ...],
    "charts": [<chart catalog entry, Epic 12>, ...]}``, all three lists sorted by their
    ``type``/``key``. The palette (Epic 5 Story 3) and the schema-driven config panels
    (Story 4) render entirely from this -- no Python in the client.
    """
    return export_catalog()


def clear_cache(payload: dict[str, Any]) -> dict[str, Any]:
    """Remove every entry from the on-disk execution cache (POST /cache/clear).

    ``payload`` is unused -- this endpoint takes no request body -- but the
    parameter is required to match the ``(payload) -> dict`` shape every
    function in ``app.py``'s ``_POST_ROUTES`` dict must have, so it can be
    dispatched through the same uniform routing/error-handling machinery as
    ``/compile``, ``/execute``, etc. instead of needing bespoke route code.
    """
    get_default_cache().clear()
    return {"status": "ok"}


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


def _node_hash(node: Node, upstream_hashes: list[str]) -> str:
    """This node's cache key: sha256(node type + canonical params + upstream hashes + sdk version).

    Recursive by construction: *upstream_hashes* are themselves node hashes
    (each already folding in ITS OWN upstream hashes via a prior call to this
    function), so folding them into this node's hash transitively covers the
    entire upstream chain -- any ancestor's param change changes every
    descendant's hash. The caller (``_execute_functional_stream``) is
    responsible for only calling this when every upstream hash is known
    (non-``None``) and this node is itself ``cacheable`` -- see that
    function's docstring for why a node with a non-cacheable ancestor never
    gets a defined hash.

    ``node.type`` is included so two different node types with coincidentally
    identical params/upstream hashes never collide on the same key, and
    *upstream_hashes* is folded in caller-supplied order (one hash per IN
    port, in port-declaration order) rather than sorted, so a node whose
    upstream wiring is swapped across two non-commutative ports produces a
    different key even though the *set* of upstream hashes is unchanged.
    """
    params_json_safe = {p.name: p.model_dump(mode="json")["value"] for p in node.params}
    canonical_params = json.dumps(params_json_safe, sort_keys=True, separators=(",", ":"))
    payload = node.type + canonical_params + "".join(upstream_hashes) + __version__
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class _NodeEvent:
    """One step in a FUNCTIONAL graph's node-by-node walk (Epic 7 Story 4 seam).

    ``phase`` is one of "start" (about to run a non-skipped node), "ok" (ran
    successfully), "error" (raised), or "skip" (an upstream dependency was not
    "ok", so this node never ran). A later SSE layer maps every phase to a wire
    event 1:1 (including "skip" -> ``node_skip``) so the canvas never has to
    infer a node's status from the absence of an event.
    ``_execute_functional_with_status`` below consumes every phase, including
    "skip", to keep its existing ``statuses`` contract.
    """

    phase: str  # "start" | "ok" | "error" | "skip"
    node_id: str
    label: str
    current: int | None = None  # 1-indexed position in this run's topo order ("start" only)
    total: int | None = None  # size of this run's topo order ("start" only)
    elapsed_ms: int | None = None  # "ok" / "error" only
    results: dict[str, Any] | None = None  # raw OUT-port artifacts, "ok" only
    cached: bool = False  # "ok" only; True when served from the execution cache
    error: str | None = None  # "error" only


def _execute_functional_stream(
    graph: Graph,
    only: set[str] | None = None,
    wiring_map: WiringMap | None = None,
) -> Iterator[_NodeEvent]:
    """Walk a FUNCTIONAL graph node by node, yielding one lifecycle event per node.

    The generator core behind both the synchronous whole-graph execute path
    (``_execute_functional_with_status``, which drains it into the existing
    ``(results, statuses)`` shape) and the SSE streaming path (Epic 7 Story 4),
    so the two stay equivalent by construction instead of by parallel
    maintenance. Graph-level guards (validation gate, paradigm, cycle, unbound
    input) still raise immediately -- the caller must map those to an HTTP 4xx
    *before* consuming this generator, since a streaming HTTP response cannot
    change its status code after the first byte is sent.

    Caching (Epic 7 Story 6): when a node is ``cacheable`` and every upstream
    node has a defined (non-``None``) hash, the node's hash is computed via
    ``_node_hash`` and used to check the on-disk ``ExecutionCache`` before
    executing. A cache hit skips ``definition.execute(...)`` and yields the
    cached outputs instead; the event's ``cached`` field is ``True``. A node
    with a non-cacheable ancestor never gets a defined hash (``None``) and is
    never looked up or written to the cache -- see ``_node_hash``'s docstring
    for the hash/propagation rule.
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
    # Dangling-input guard (raises UnboundInputError -> 422), same as before.
    for node_id in topo_order_ids:
        node = graph.nodes[node_id]
        for port in node.ports:
            if port.direction != Direction.IN:
                continue
            if not wiring_map.upstream(node.id, port.id):
                raise UnboundInputError(f"{node.id}.{port.id} has no upstream source")

    total = len(topo_order_ids)
    node_status: dict[str, str] = {}
    node_results: dict[str, dict[str, Any]] = {}
    node_hashes: dict[str, str | None] = {}
    cache = get_default_cache()
    for index, node_id in enumerate(topo_order_ids, start=1):
        node = graph.nodes[node_id]
        inputs: dict[str, Any] = {}
        upstream_hashes: list[str | None] = []
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
            if node_status[src.node_id] not in (_STATUS_OK, _STATUS_CACHED):
                skipped = True
                break
            src_node = graph.nodes[src.node_id]
            src_port_name = next(p.name for p in src_node.ports if p.id == src.port_id)
            inputs[port.name] = node_results[src.node_id][src_port_name]
            upstream_hashes.append(node_hashes[src.node_id])
        if skipped:
            node_status[node_id] = _STATUS_SKIPPED
            yield _NodeEvent(phase="skip", node_id=node_id, label=node.label or "")
            continue
        yield _NodeEvent(
            phase="start", node_id=node_id, label=node.label or "", current=index, total=total
        )
        start = time.monotonic()
        try:
            definition = get_node_definition(node.type)()
            cache_hash: str | None = None
            if definition.cacheable and all(h is not None for h in upstream_hashes):
                cache_hash = _node_hash(node, [h for h in upstream_hashes if h is not None])
            cached_outputs = cache.get(cache_hash) if cache_hash is not None else None
            is_cache_hit = cached_outputs is not None
            if is_cache_hit:
                assert cached_outputs is not None  # mypy: narrowed by is_cache_hit above
                outputs = cached_outputs
            else:
                outputs = _execute_node(definition, node, inputs)
                if cache_hash is not None:
                    # A cache-write failure (e.g. an unpicklable output, a full
                    # disk) must not turn a successful execute() into a
                    # reported node "error" -- caching is an optimization, not
                    # part of the node's correctness contract.
                    with contextlib.suppress(Exception):
                        cache.put(cache_hash, outputs, node_id=node.id, label=node.label or "")
            elapsed_ms = int((time.monotonic() - start) * 1000)
            node_results[node_id] = outputs
            node_status[node_id] = _STATUS_CACHED if is_cache_hit else _STATUS_OK
            node_hashes[node_id] = cache_hash
            yield _NodeEvent(
                phase="ok",
                node_id=node_id,
                label=node.label or "",
                elapsed_ms=elapsed_ms,
                results=outputs,
                cached=is_cache_hit,
            )
        except Exception as exc:  # noqa: BLE001 - any node-runtime failure -> error event
            elapsed_ms = int((time.monotonic() - start) * 1000)
            node_status[node_id] = _STATUS_ERROR
            node_hashes[node_id] = None
            yield _NodeEvent(
                phase="error",
                node_id=node_id,
                label=node.label or "",
                elapsed_ms=elapsed_ms,
                error=f"{type(exc).__name__}: {exc}",
            )


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

    *wiring_map*, if given, is reused instead of rebuilt (the ``run_to``
    caller already built one to resolve ancestors -- building it twice per
    request would double the wiring-map construction cost on the "fast
    incremental re-run" path that ``run_to`` exists for).

    Drains ``_execute_functional_stream`` (Epic 7 Story 4 seam) rather than
    walking the graph itself, so this function and the SSE streaming path
    stay equivalent by construction.
    """
    results: dict[str, dict[str, Any]] = {}
    statuses: dict[str, dict[str, Any]] = {}
    for event in _execute_functional_stream(graph, only=only, wiring_map=wiring_map):
        if event.phase == "skip":
            statuses[event.node_id] = {"status": _STATUS_SKIPPED}
        elif event.phase == "ok":
            results[event.node_id] = event.results or {}
            statuses[event.node_id] = {"status": _STATUS_CACHED if event.cached else _STATUS_OK}
        elif event.phase == "error":
            statuses[event.node_id] = {"status": _STATUS_ERROR, "error": event.error}
        # "start" carries no status change; ignore it here.
    return results, statuses


def _payload_for(value: Any) -> dict[str, Any]:
    """``to_payload`` for *value*, registering any HTML report for ``/reports``.

    ``to_payload`` stays pure (no I/O); the side effect of persisting the report
    blob lives here in the execute path. An ``"html"`` payload gains a
    ``"report_hash"`` (additive -- existing fields are untouched) so the canvas
    can load large reports via ``GET /reports/{hash}`` instead of a multi-MB
    ``srcdoc``. Non-HTML payloads pass through unchanged.
    """
    payload = to_payload(value)
    if payload.get("kind") == "html":
        payload["report_hash"] = get_default_store().put(payload["value"])
    return payload


def _results_to_payloads(
    results: dict[str, dict[str, Any]],
) -> dict[str, dict[str, dict[str, Any]]]:
    """Map each OUT-port artifact to its typed result payload (Story 3)."""
    return {
        node_id: {port_name: _payload_for(value) for port_name, value in ports.items()}
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


def _resolve_run_to(graph: Graph, run_to: Any) -> tuple[set[str] | None, WiringMap | None]:
    """Resolve a request's ``run_to`` value into ``(only, wiring_map)`` for a FUNCTIONAL walk.

    Shared by ``execute_graph`` and ``execute_graph_stream`` so the "run to here"
    target-resolution logic (Epic 4 Story 6 / Epic 7 Story 5) exists in exactly
    one place. ``run_to is None`` means "run everything" -- returns ``(None,
    None)``, and the caller builds its own wiring map lazily only if it needs
    one. An unknown target id raises ``CodegenError`` (-> 422).
    """
    if run_to is None:
        return None, None
    targets = {run_to} if isinstance(run_to, str) else set(run_to)
    missing = targets - set(graph.nodes)
    if missing:
        raise CodegenError(f"run_to targets not in graph: {sorted(missing)}")
    wiring_map = build_wiring_map(graph)
    only = _ancestors(graph, targets, wiring_map)
    return only, wiring_map


def execute_graph(payload: dict[str, Any]) -> dict[str, Any]:
    """IR graph (as a dict) -> ``{"payload_version", "results", "statuses"}``.

    Runs the whole graph in-process (Epic 4 Story 2). FUNCTIONAL graphs are walked
    node by node so a single node's runtime failure is reported as that node's
    ``error`` status (downstream nodes ``skipped``) at HTTP 200, rather than
    aborting the whole run -- the canvas colours nodes from ``statuses``. Graph-LEVEL
    rejections (validation gate, cycle, unbound input, wrong paradigm) still raise
    and surface as the server's 422. FUNCTIONAL graphs are cached per-node via
    ``ExecutionCache`` (see ``_execute_functional_stream``'s docstring for the
    hash/propagation rule). Each
    OUT port in ``results`` is a typed result payload (Story 3), not a raw
    artifact; ``payload_version`` stamps the contract once at the top level.

    When the body is an envelope with ``run_to`` (a node id or list of ids), only the
    subgraph up to and including those nodes runs ("run to here", Epic 4 Story 6),
    reusing the Epic 2 traversal + wiring; the rest of the graph is left unrun.
    """
    graph_payload, run_to = _split_request(payload)
    graph = _to_graph(graph_payload)
    validate_api_keys_present(graph)
    if graph.paradigm is Paradigm.FUNCTIONAL:
        only, wiring_map = _resolve_run_to(graph, run_to)
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


def execute_graph_stream(payload: dict[str, Any]) -> Generator[dict[str, Any], None, None]:
    """IR graph (as a dict) -> a stream of SSE-ready event dicts (Story 4).

    Mirrors ``execute_graph``'s validation and dispatch (same ``_split_request``
    envelope, same ``run_to`` ancestor resolution, same DECLARATIVE fallback)
    but yields one JSON-safe event dict per step instead of collecting a final
    ``{"results", "statuses"}`` response -- the HTTP layer (``app.py``) formats
    each as a ``text/event-stream`` frame. Every event dict has a ``"type"``
    key: ``"node_start"``, ``"node_ok"``, ``"node_error"``, ``"node_skip"``,
    ``"run_complete"``, or ``"run_error"``, plus a ``"payload_version"`` key
    (``PAYLOAD_CONTRACT_VERSION``) so the client can detect a stale bundle
    talking to an incompatible server on the very first event, the same
    contract ``execute_graph`` stamps once at the top level. All graph-level
    validation (``enforce_validation_gate``, paradigm/cycle/unbound-input
    checks, unknown ``run_to`` targets) happens eagerly on the FIRST iteration
    step, before any event is yielded, so the caller can still raise straight
    through and map it to a real HTTP 4xx if it chooses to peek the first item
    before committing to a streaming response. A node-runtime failure
    (FUNCTIONAL) becomes a ``"node_error"`` event and the walk continues
    (downstream nodes reported via ``"node_skip"``, mirroring
    ``execute_graph``'s "skipped" status); a DECLARATIVE-graph failure has no
    per-node granularity to report, so it becomes a terminal ``"run_error"``
    event instead.
    """
    graph_payload, run_to = _split_request(payload)
    graph = _to_graph(graph_payload)
    validate_api_keys_present(graph)
    start_time = time.monotonic()
    try:
        if graph.paradigm is Paradigm.FUNCTIONAL:
            only, wiring_map = _resolve_run_to(graph, run_to)
            for event in _execute_functional_stream(graph, only=only, wiring_map=wiring_map):
                if event.phase == "start":
                    yield {
                        "type": "node_start",
                        "node_id": event.node_id,
                        "label": event.label,
                        "current": event.current,
                        "total": event.total,
                        "payload_version": PAYLOAD_CONTRACT_VERSION,
                    }
                elif event.phase == "ok":
                    yield {
                        "type": "node_ok",
                        "node_id": event.node_id,
                        "elapsed_ms": event.elapsed_ms,
                        "results": {
                            port_name: _payload_for(value)
                            for port_name, value in (event.results or {}).items()
                        },
                        "cached": event.cached,
                        "payload_version": PAYLOAD_CONTRACT_VERSION,
                    }
                elif event.phase == "error":
                    yield {
                        "type": "node_error",
                        "node_id": event.node_id,
                        "elapsed_ms": event.elapsed_ms,
                        "error": event.error,
                        "payload_version": PAYLOAD_CONTRACT_VERSION,
                    }
                elif event.phase == "skip":
                    yield {
                        "type": "node_skip",
                        "node_id": event.node_id,
                        "payload_version": PAYLOAD_CONTRACT_VERSION,
                    }
        elif run_to is not None:
            raise CodegenError("run_to (run-to-here) is only supported for FUNCTIONAL graphs")
        else:
            # DECLARATIVE (and any future paradigm): the reference executor is
            # all-or-nothing and has no per-node granularity to stream, so emit
            # one node_start/node_ok pair per produced node (mirrors
            # execute_graph's all-"ok" statuses on success).
            results = execute(graph)
            for node_id, ports in results.items():
                yield {
                    "type": "node_start",
                    "node_id": node_id,
                    "label": node_id,
                    "payload_version": PAYLOAD_CONTRACT_VERSION,
                }
                yield {
                    "type": "node_ok",
                    "node_id": node_id,
                    "elapsed_ms": int((time.monotonic() - start_time) * 1000),
                    "results": {
                        port_name: _payload_for(value) for port_name, value in ports.items()
                    },
                    # DECLARATIVE graphs are never cached (Epic 7 Story 6 only
                    # caches the FUNCTIONAL per-node walk); always False rather
                    # than omitted so every node_ok frame satisfies the same
                    # StreamEvent shape (ui/src/exec/sse.ts).
                    "cached": False,
                    "payload_version": PAYLOAD_CONTRACT_VERSION,
                }
    except CodegenError:
        raise
    except Exception as exc:  # noqa: BLE001 - any failure mid-stream -> a terminal event, not a crash
        yield {
            "type": "run_error",
            "error": f"{type(exc).__name__}: {exc}",
            "payload_version": PAYLOAD_CONTRACT_VERSION,
        }
        return
    yield {
        "type": "run_complete",
        "total_ms": int((time.monotonic() - start_time) * 1000),
        "payload_version": PAYLOAD_CONTRACT_VERSION,
    }


def _coerce_json_inputs(node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
    """Coerce JSON-transported ``inputs`` values to the native type each IN port expects.

    ``execute_node``'s ``inputs`` arrive over HTTP as plain JSON, but a node's ``execute()``
    expects native Python objects for non-JSON-native port types (e.g. a ``DataFrame`` IN port
    -- ``eval.run``'s ``dataset``, ``eval.label``'s ``results``/``labels``) exactly like it
    would receive from an upstream node in a full graph run. A JSON body can only carry a
    ``list[dict]`` for a table, so this converts that shape to a real `pd.DataFrame` for any
    port declared ``data_type == "DataFrame"``, leaving every other port's value untouched.
    """
    coerced = dict(inputs)
    for port in node.ports:
        if (
            port.direction == Direction.IN
            and port.data_type == "DataFrame"
            and port.name in coerced
            and isinstance(coerced[port.name], list)
        ):
            coerced[port.name] = pd.DataFrame(coerced[port.name])
    return coerced


def execute_node(payload: dict[str, Any]) -> dict[str, Any]:
    """Execute a single node ("run this node", Epic 4 Story 6).

    Envelope body: ``{"graph": <ir>, "run_node": <node id>, "inputs": {<IN-port name>: value}}``.
    Runs only that node's ``execute()`` with caller-supplied upstream inputs and returns
    the same ``{"payload_version", "results", "statuses"}`` shape as ``execute_graph`` --
    but for the single node. This path bypasses ``ExecutionCache`` entirely (it has no
    upstream chain to hash and the caller already supplies fresh inputs directly), so a
    node-runtime failure is reported as that node's ``error``
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
    validate_api_keys_present(graph, node_ids=[node_id])
    if node.paradigm is not Paradigm.FUNCTIONAL:
        raise CodegenError(
            f"execute_node only supports FUNCTIONAL nodes, got {node.paradigm} for {node_id!r}"
        )
    inputs = _coerce_json_inputs(node, inputs)

    results: dict[str, dict[str, Any]] = {}
    try:
        definition = get_node_definition(node.type)()
        results[node_id] = _execute_node(definition, node, inputs)
        status: dict[str, Any] = {"status": _STATUS_OK}
    except Exception as exc:  # noqa: BLE001 - any node-runtime failure -> error status
        status = {"status": _STATUS_ERROR, "error": f"{type(exc).__name__}: {exc}"}
    return {
        "payload_version": PAYLOAD_CONTRACT_VERSION,
        "results": _results_to_payloads(results),
        "statuses": {node_id: status},
    }
