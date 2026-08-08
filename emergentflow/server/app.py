"""FastAPI local server for the bundled app (ADR 0013 Decision 2, §A6).

Phase-2 "Living Bridge": the stdlib ``http.server`` v0 is replaced by FastAPI +
Uvicorn so a long ``/execute`` no longer blocks ``/healthz`` and so the SSE
streaming endpoint (Epic 7 Story 4) has an async host. The URL paths and JSON
shapes are byte-for-byte the same as the v0 server, so the canvas (a pure HTTP
consumer, ADR 0013 Decision 3) needs no change. ``fastapi``/``uvicorn`` ship in
the optional ``server`` extra; importing this module requires them.

Routes:
- ``GET  /``                 -- ``_static/index.html`` when present, else the demo page
- ``GET  /healthz``          -- ``{"status": "ok"}``
- ``GET  /schema``           -- the IR JSON Schema
- ``GET  /catalog``          -- ``{"catalog_version": <int>, "nodes": [...], "estimators": [...],
  "charts": [...]}`` (ADR 0015)
- ``GET  /mutation-schema``  -- the GraphMutation JSON Schema (Epic 14 Story 4)
- ``GET  /session-event-schema`` -- the session SSE event JSON Schema (Epic 14 Story 4)
- ``GET  /reports/{hash}``   -- a stored HTML report blob (Epic 7 Story 3)
- ``POST /cache/clear``      -- ``{"status": "ok"}``
- ``POST /compile``          -- IR JSON -> ``{"code": ...}``
- ``POST /eval/label``       -- ``{"results", "labels"}`` -> ``{"labeled": [...]}`` (Epic 9 Story 6)
- ``POST /execute``          -- IR JSON -> ``{"payload_version", "results", "statuses"}``
- ``POST /execute/stream``    -- IR JSON -> Server-Sent Events of per-node progress
- ``POST /execute_node``     -- ``{"graph", "run_node", "inputs"}`` -> single-node run
- ``POST /export/eval_set``  -- ``{"rows": [...]}`` -> eval-set JSONL file download (Epic 9 Story 7)
- ``POST /export/finetune``  -- ``{"rows": [...]}`` -> fine-tune JSONL download (Epic 9 Story 7)
- ``POST /validate``         -- IR JSON -> ``{"diagnostics": ...}``
- ``GET  /connections``      -- list local connection profiles (Epic 13 Story 10)
- ``POST /connections/{name}/test`` -- probe one connection profile
- ``GET  /connections/{name}/schema`` -- browse a connection's relations/columns
- ``POST /compile-spec``     -- {"spec": {...}, "dialect": ...} -> {"sql": ...}
- ``GET  /flows``             -- list saved flows
- ``GET  /flows/{slug}``      -- get a saved flow's graph JSON
- ``POST /flows``             -- save a new flow
- ``PUT  /flows/{slug}``      -- update an existing flow
- ``DELETE /flows/{slug}``    -- delete a saved flow
- ``POST /flows/{slug}/rename`` -- rename a flow
- ``GET  /examples``          -- list bundled example graphs
- ``GET  /examples/{path}``   -- get a bundled example graph
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import mimetypes
import os
import pathlib
import queue
import socket
import threading
import time
import webbrowser
from collections.abc import AsyncIterator, Awaitable, Callable, Generator
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse

from emergentflow.collab.agents import list_available_adapter_names
from emergentflow.collab.chat import (
    ChatAlreadyActiveError,
    ChatTurnAlreadyResolvedError,
    UnknownChatTurnError,
)
from emergentflow.collab.chat_runner import (  # noqa: F401
    UnknownBackendError,
    start_chat_turn,
    stop_chat_turn,
)
from emergentflow.collab.gates import (
    Decision,
    Gate,
    GateAlreadyResolvedError,
    UnknownGateError,
)
from emergentflow.collab.knowledge import UnknownKnowledgeEntryError
from emergentflow.collab.review import AnchorError, ReviewComment, ReviewThread
from emergentflow.collab.session import (
    OpenGatesError,
    ProposalAlreadyResolvedError,
    StaleVersionError,
    UnknownProposalError,
    UnknownReviewError,
    UnknownSessionError,
)
from emergentflow.collab.session import get_default_store as get_default_session_store
from emergentflow.ir.graph import Graph
from emergentflow.ir.mutation import GraphMutation
from emergentflow.ir.serialize import deserialize_graph
from emergentflow.llm.gateway import GatewayClient
from emergentflow.server.artifacts import (
    DEFAULT_ARTIFACT_DIRNAME,
    DEFAULT_ARTIFACT_MAX_MB,
    configure_artifacts,
)
from emergentflow.server.cache import DEFAULT_CACHE_DIRNAME, DEFAULT_CACHE_MAX_MB, configure_cache
from emergentflow.server.flows import (
    DEFAULT_FLOW_DIRNAME,
    FlowAlreadyExistsError,
    InvalidSlugError,
    UnknownFlowError,
    configure_flows,
    get_default_flows,
    slugify,
)
from emergentflow.server.reports import get_default_store
from emergentflow.server.runs import (
    DEFAULT_RUNS_DIRNAME,
    DEFAULT_RUNS_KEEP,
    UnknownRunError,
    configure_runs,
    get_default_runs,
)
from emergentflow.server.service import (
    clear_cache,
    column_lineage_for,
    compile_graph,
    compile_query_spec,
    compile_session,
    consult_graph,
    consult_session,
    create_connection,
    delete_connection,
    execute_graph,
    execute_graph_stream,
    execute_node,
    execute_session,
    export_eval_set_bytes,
    export_finetune_bytes,
    get_catalog,
    get_connection_schema,
    get_knowledge_entry,
    get_mutation_schema,
    get_personas,
    get_schema,
    get_session_event_schema,
    get_validity_rules,
    inspect_graph,
    label_eval,
    lineage_for_node,
    list_connections,
    list_knowledge,
    save_knowledge,
    test_connection_route,
    update_connection,
    validate_graph,
)

# The built UI is bundled into emergentflow/_static/ by the package build hook
# (ADR 0013 Decision 1). It is absent in a source checkout / before `vite build`,
# so every read is guarded and the server falls back to the v0 demo page.
# app.py lives at emergentflow/server/app.py; parents[1] is the emergentflow/ package root.
_STATIC_DIR = pathlib.Path(__file__).resolve().parents[1] / "_static"

# parents[2] from emergentflow/server/app.py is the repo root, sibling to examples/ -- this
# only resolves to a real directory in a source checkout (an editable install or `emergentflow
# serve` run from the monorepo). Despite the original intent, neither MANIFEST.in nor
# [tool.setuptools.package-data] in pyproject.toml actually ships examples/ into the sdist or
# wheel (top-level examples/ isn't part of the `emergentflow*` package tree setuptools
# discovers), so for a real `pip install emergentflow[server]` end user this path won't exist
# on disk. `list_examples()` below degrades gracefully (empty list, ExampleGallery renders
# nothing) rather than crashing, but the starter-gallery feature is effectively dev-checkout-
# only until examples/ is packaged as installed data -- see issue #114 follow-up.
_EXAMPLES_DIR = pathlib.Path(__file__).resolve().parents[2] / "examples"


def _static_file(url_path: str) -> pathlib.Path | None:
    """Resolve a GET path to a real file inside ``_STATIC_DIR``, or ``None``.

    Returns ``None`` when ``_static/`` is absent, the resolved path escapes it
    (directory-traversal guard), or the target is not an existing file. ``"/"``
    maps to ``index.html``. The caller falls back to the demo page / a 404.
    """
    if not _STATIC_DIR.is_dir():
        return None
    relative = url_path.lstrip("/") or "index.html"
    candidate = (_STATIC_DIR / relative).resolve()
    if not candidate.is_relative_to(_STATIC_DIR):
        return None
    if candidate.is_file():
        return candidate
    return None


# A deliberately tiny single-page client: paste IR JSON, hit a button, see the
# result. It is the throwaway "prove the canvas -> IR -> code -> execute loop"
# stopgap, not the real ui/ canvas (roadmap Epic 3); keep lines <= 100 chars.
_INDEX_HTML = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Emergent Flow - local</title></head>
<body style="font-family: system-ui; max-width: 60rem; margin: 2rem auto;">
  <h1>Emergent Flow &mdash; local canvas (v0)</h1>
  <p>Paste an IR graph as JSON, then compile / validate / execute it in-process.</p>
  <textarea id="ir" rows="14" style="width:100%;font-family:monospace;"></textarea>
  <p>
    <button onclick="call('/compile')">Compile</button>
    <button onclick="call('/validate')">Validate</button>
    <button onclick="call('/execute')">Execute</button>
  </p>
  <pre id="out" style="background:#f4f4f4;padding:1rem;white-space:pre-wrap;"></pre>
  <script>
    async function call(path) {
      const out = document.getElementById('out');
      let body;
      try { body = JSON.parse(document.getElementById('ir').value); }
      catch (e) { out.textContent = 'Invalid JSON: ' + e; return; }
      const res = await fetch(path, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body),
      });
      out.textContent = JSON.stringify(await res.json(), null, 2);
    }
  </script>
</body>
</html>
"""

# Service functions keyed by POST path. Each maps a JSON dict to a JSON dict and
# is CPU-bound (it runs node code), so handlers off-load it to a worker thread to
# keep the event loop responsive (the whole point of the FastAPI upgrade).
_POST_ROUTES: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "/cache/clear": clear_cache,
    "/compile": compile_graph,
    "/compile-spec": compile_query_spec,
    "/eval/label": label_eval,
    "/execute": execute_graph,
    "/execute_node": execute_node,
    "/inspect": inspect_graph,
    "/knowledge": save_knowledge,
    "/lineage": lineage_for_node,
    "/lineage/column": column_lineage_for,
    "/validate": validate_graph,
}


def _error_json(status_code: int, message: str) -> JSONResponse:
    """The project's one error-body shape: ``{"error": <message>}``."""
    return JSONResponse(status_code=status_code, content={"error": message})


async def _run_sync(fn: Callable[[], Any]) -> Any:
    """Run a zero-arg synchronous callable off the event loop, in a worker thread.

    Every handler below does some blocking work (file I/O, hashing, schema/catalog
    building); routing it through here keeps the event loop free for concurrent
    requests -- the whole point of the FastAPI upgrade -- instead of stalling
    every in-flight request (including ``/healthz``) for the duration of one
    handler's disk access.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, fn)


async def _safe_json(fn: Callable[[], dict[str, Any]]) -> Response:
    """Run *fn* off the event loop; map any exception to the project's 422 contract."""
    try:
        result = await _run_sync(fn)
    except Exception as exc:  # noqa: BLE001 - any ef.* failure -> 422, never crash the server
        return _error_json(422, f"{type(exc).__name__}: {exc}")
    return JSONResponse(content=result)


async def _session_json(fn: Callable[[], dict[str, Any]]) -> Response:
    """Run *fn* off the event loop; map collab session errors to their HTTP codes.

    ``UnknownSessionError`` / ``UnknownProposalError`` / ``UnknownReviewError`` /
    ``UnknownChatTurnError`` -> 404,
    ``StaleVersionError`` / ``ProposalAlreadyResolvedError`` / ``ChatAlreadyActiveError`` /
    ``ChatTurnAlreadyResolvedError`` -> 409
    (optimistic-concurrency / proposal-lifecycle conflicts -- caller sent a
    stale expected/base version, or tried to re-resolve a decided proposal),
    ``AnchorError`` -> 422 with an ``anchor_error:`` prefix (a review finding's
    node_id/edge_id/port_id didn't resolve against the graph -- same status as
    the generic catch-all below, but a stable, parseable prefix like the 409s
    get, rather than relying on the exception class name), any other
    exception -> 422 (mirrors ``_safe_json``'s catch-all for every other
    service failure).
    """
    try:
        result = await _run_sync(fn)
    except (
        UnknownSessionError,
        UnknownProposalError,
        UnknownReviewError,
        UnknownGateError,
        UnknownChatTurnError,
    ) as exc:
        return _error_json(404, str(exc))
    except StaleVersionError as exc:
        return _error_json(409, f"stale_version: {exc}")
    except ProposalAlreadyResolvedError as exc:
        return _error_json(409, f"proposal_already_resolved: {exc}")
    except OpenGatesError as exc:
        return _error_json(409, f"gates_open: {exc}")
    except GateAlreadyResolvedError as exc:
        return _error_json(409, f"gate_already_resolved: {exc}")
    except ChatAlreadyActiveError as exc:
        return _error_json(409, f"chat_already_active: {exc}")
    except ChatTurnAlreadyResolvedError as exc:
        return _error_json(409, f"chat_turn_already_resolved: {exc}")
    except AnchorError as exc:
        return _error_json(422, f"anchor_error: {exc}")
    except Exception as exc:  # noqa: BLE001 - any other failure -> 422, never crash the server
        return _error_json(422, f"{type(exc).__name__}: {exc}")
    return JSONResponse(content=result)


def _graph_from_session_payload(payload: dict[str, Any]) -> Graph:
    """Parse an embedded IR graph dict the same way the payload-only routes do.

    Routes it through ``deserialize_graph`` (not ``Graph.model_validate``) so
    session routes apply the same schema-version checks/migrations as every
    other graph-accepting route in this file.
    """
    return deserialize_graph(json.dumps(payload))


# Bearer-token gate for /sessions* routes (ADR 0019 trust boundary). Open by
# default (today's trusted-localhost model); serve() flips this on when the
# server binds to a non-loopback host. A plain module-level pair of globals is
# enough here -- unlike configure_cache's lazily-created singleton, there is
# nothing to guard against re-configuring, since every route handler just
# re-reads these two values on every request.
_session_auth_required = False
_session_auth_token: str | None = None


def configure_session_auth(*, required: bool, token: str | None = None) -> None:
    """Set whether ``/sessions*`` routes require a bearer token, and what it is.

    When *required* is True, *token* MUST be a non-empty string -- binding the
    server to a non-loopback host and leaving the session surface open is
    exactly the misconfiguration this gate exists to prevent, so it is a hard
    error, not a silent no-op. When *required* is False (the localhost
    default), *token* is ignored and every ``/sessions*`` request passes
    through unauthenticated, unchanged from today's trusted local-app model.
    """
    global _session_auth_required, _session_auth_token
    if required and not token:
        raise ValueError(
            "configure_session_auth(required=True) needs a non-empty token -- "
            "binding the server to a non-loopback host requires a real bearer "
            "token, never an implicit open session surface."
        )
    _session_auth_required = required
    _session_auth_token = token


async def _require_session_auth(request: Request) -> None:
    """FastAPI dependency: raise 401 if *request* fails the bearer-token check.

    Wired via ``dependencies=[Depends(_require_session_auth)]`` on every
    ``/sessions*`` route instead of each handler repeating a guard-clause line.
    A no-op whenever auth is not required (the localhost default) -- every
    non-session route in this file is intentionally untouched by this check.
    The raised HTTPException is reshaped to the project's ``{"error": ...}``
    body by ``_http_exception_handler`` below.
    """
    if not _session_auth_required:
        return
    if request.headers.get("authorization") != f"Bearer {_session_auth_token}":
        raise HTTPException(status_code=401, detail="missing or invalid bearer token")


async def _safe_download(fn: Callable[[], bytes], filename: str) -> Response:
    """Run *fn* off the event loop; map any exception to the project's 422 contract,
    else return its bytes as a ``Content-Disposition: attachment`` file download.

    Mirrors ``_safe_json`` but for a binary payload instead of a JSON dict -- used by the
    dataset-export routes, which stream a JSONL file rather than a JSON response body.
    """
    try:
        content = await _run_sync(fn)
    except Exception as exc:  # noqa: BLE001 - any ef.* failure -> 422, never crash the server
        return _error_json(422, f"{type(exc).__name__}: {exc}")
    return Response(
        content=content,
        media_type="application/x-ndjson",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _sse_frame(event: dict[str, Any]) -> bytes:
    """One ``data: <json>\n\n`` SSE frame for *event* (the project's one event shape)."""
    return f"data: {json.dumps(event)}\n\n".encode()


def _bridge_to_queue(
    events: Generator[dict[str, Any], None, None],
    q: queue.SimpleQueue[bytes | None],
    cancel: threading.Event,
) -> None:
    """Drain a sync event generator into *q* (a thread-safe queue), sentinel ``None`` last.

    Runs on a background thread (started by the route handler below) so the
    blocking, CPU-bound node-by-node walk never runs on the asyncio event
    loop -- the same reason every other handler in this module offloads
    blocking work via ``_run_sync``/``run_in_executor``. Unlike those
    one-shot handlers, this one must hand back partial results as they
    become available rather than waiting for the whole walk to finish, hence
    the producer-thread + queue bridge instead of a single
    ``run_in_executor`` call.

    Checks *cancel* between node events and closes *events* (stopping the
    graph walk before its next node) once it's set -- the route handler below
    sets it when the client disconnects, so an abandoned request doesn't run
    the rest of a possibly-large graph for nobody. Any exception escaping the
    walk (including one raised by ``_sse_frame`` itself, e.g. a non-JSON-safe
    value) becomes a terminal ``run_error`` frame instead of silently ending
    the stream -- a generator failure that gets swallowed here is otherwise
    indistinguishable, on the wire, from a normal successful close.
    """
    try:
        for event in events:
            if cancel.is_set():
                events.close()
                break
            q.put(_sse_frame(event))
    except Exception as exc:  # noqa: BLE001 - any failure draining/framing -> a terminal event
        q.put(_sse_frame({"type": "run_error", "error": f"{type(exc).__name__}: {exc}"}))
    finally:
        q.put(None)


async def _execute_stream_response(payload: dict[str, Any]) -> Response:
    """Build the ``/execute/stream`` response: a real 4xx for upfront failures, else SSE.

    Forces the first step of ``execute_graph_stream`` (graph parsing, the
    validation gate, paradigm/cycle/unbound-input checks, unknown ``run_to``
    targets) to run -- and raise, if it's going to -- BEFORE any bytes are
    sent, so those failures still map to the project's normal 422 contract
    exactly like ``/execute`` does. Only once that first event is in hand do
    we commit to a ``text/event-stream`` response and start draining the rest
    on a background thread.
    """
    events = execute_graph_stream(payload)
    try:
        first_event = await _run_sync(lambda: next(events, None))
    except Exception as exc:  # noqa: BLE001 - any ef.* failure -> 422, never crash the server
        return _error_json(422, f"{type(exc).__name__}: {exc}")

    q: queue.SimpleQueue[bytes | None] = queue.SimpleQueue()
    if first_event is not None:
        q.put(_sse_frame(first_event))
    cancel = threading.Event()
    threading.Thread(target=_bridge_to_queue, args=(events, q, cancel), daemon=True).start()

    async def body() -> AsyncIterator[bytes]:
        loop = asyncio.get_running_loop()
        try:
            while True:
                chunk = await loop.run_in_executor(None, q.get)
                if chunk is None:
                    break
                yield chunk
        finally:
            # Runs on a client disconnect too (Starlette closes this async
            # generator), not just on a clean finish -- signals the producer
            # thread to stop rather than walking the rest of the graph.
            cancel.set()

    return StreamingResponse(body(), media_type="text/event-stream")


async def _read_json_body(request: Request) -> dict[str, Any]:
    """Parse the request body as a JSON dict; an empty body is ``{}``.

    Raises ``json.JSONDecodeError``/``ValueError`` on malformed JSON so the caller
    can map it to HTTP 400 -- matching the v0 stdlib server's contract exactly.
    """
    raw = await request.body()
    if not raw:
        return {}
    return json.loads(raw)


async def _dispatch(
    service_fn: Callable[[dict[str, Any]], dict[str, Any]], request: Request
) -> Response:
    """Run *service_fn* on the parsed body in a worker thread; map errors to JSON.

    400 = bad JSON body, 422 = any service-level failure (bad graph, etc.),
    200 = the function's JSON dict. Mirrors the v0 server's status codes.
    """
    try:
        body = await _read_json_body(request)
    except (ValueError, json.JSONDecodeError) as exc:
        return _error_json(400, f"invalid JSON body: {exc}")
    return await _safe_json(lambda: service_fn(body))


def _make_post_handler(
    service_fn: Callable[[dict[str, Any]], dict[str, Any]],
) -> Callable[[Request], Awaitable[Response]]:
    async def handler(request: Request) -> Response:
        return await _dispatch(service_fn, request)

    return handler


def create_app() -> FastAPI:
    """Build the FastAPI application (one instance per process; see ``app`` below)."""
    application = FastAPI(title="Emergent Flow - local", docs_url=None, redoc_url=None)

    @application.exception_handler(HTTPException)
    async def _http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
        """Reshape FastAPI's default `{"detail": ...}` into this project's one
        error-body shape, `{"error": ...}` (see `_error_json`) -- the only
        HTTPException raised anywhere in this module is `_require_session_auth`'s
        401, but this keeps that response consistent with every other error path."""
        return _error_json(exc.status_code, str(exc.detail))

    @application.get("/healthz")
    async def healthz() -> JSONResponse:
        return JSONResponse(content={"status": "ok"})

    @application.get("/schema")
    async def schema() -> Response:
        return await _safe_json(get_schema)

    @application.get("/catalog")
    async def catalog() -> Response:
        return await _safe_json(get_catalog)

    @application.get("/validity-rules")
    async def validity_rules() -> Response:
        return await _safe_json(get_validity_rules)

    @application.get("/mutation-schema")
    async def mutation_schema() -> Response:
        return await _safe_json(get_mutation_schema)

    @application.get("/session-event-schema")
    async def session_event_schema() -> Response:
        return await _safe_json(get_session_event_schema)

    @application.get("/personas")
    async def personas() -> Response:
        return await _safe_json(get_personas)

    @application.get("/knowledge")
    async def knowledge_list(request: Request) -> Response:
        in_type = request.query_params.get("in")
        out_type = request.query_params.get("out")
        tag = request.query_params.get("tag")
        return await _safe_json(lambda: list_knowledge(in_type=in_type, out_type=out_type, tag=tag))

    @application.get("/knowledge/{slug}")
    async def knowledge_get(slug: str) -> Response:
        try:
            result = await _run_sync(lambda: get_knowledge_entry(slug))
        except UnknownKnowledgeEntryError as exc:
            return _error_json(404, str(exc))
        except Exception as exc:  # noqa: BLE001 - never crash the server on a store failure
            return _error_json(422, f"{type(exc).__name__}: {exc}")
        return JSONResponse(content=result)

    @application.get("/reports/{report_hash}")
    async def report(report_hash: str) -> Response:
        try:
            html = await _run_sync(lambda: get_default_store().get(report_hash))
        except Exception as exc:  # noqa: BLE001 - never crash the server on a store failure
            return _error_json(422, f"{type(exc).__name__}: {exc}")
        if html is None:
            return _error_json(404, f"report not found: {report_hash}")
        return HTMLResponse(content=html)

    @application.post("/execute/stream")
    async def execute_stream(request: Request) -> Response:
        try:
            body_dict = await _read_json_body(request)
        except (ValueError, json.JSONDecodeError) as exc:
            return _error_json(400, f"invalid JSON body: {exc}")
        return await _execute_stream_response(body_dict)

    @application.post("/export/eval_set")
    async def export_eval_set_route(request: Request) -> Response:
        try:
            body_dict = await _read_json_body(request)
        except (ValueError, json.JSONDecodeError) as exc:
            return _error_json(400, f"invalid JSON body: {exc}")
        return await _safe_download(lambda: export_eval_set_bytes(body_dict), "eval_set.jsonl")

    @application.post("/export/finetune")
    async def export_finetune_route(request: Request) -> Response:
        try:
            body_dict = await _read_json_body(request)
        except (ValueError, json.JSONDecodeError) as exc:
            return _error_json(400, f"invalid JSON body: {exc}")
        return await _safe_download(lambda: export_finetune_bytes(body_dict), "finetune.jsonl")

    for path, fn in _POST_ROUTES.items():
        application.add_api_route(path, _make_post_handler(fn), methods=["POST"])

    @application.get("/connections")
    async def connections() -> Response:
        return await _safe_json(list_connections)

    @application.post("/connections/{name}/test")
    async def connection_test(name: str) -> Response:
        return await _safe_json(lambda: test_connection_route(name))

    @application.post("/connections")
    async def connection_create(request: Request) -> Response:
        try:
            body = await _read_json_body(request)
        except (ValueError, json.JSONDecodeError) as exc:
            return _error_json(400, f"invalid JSON body: {exc}")
        return await _safe_json(lambda: create_connection(body))

    @application.put("/connections/{name}")
    async def connection_update(name: str, request: Request) -> Response:
        try:
            body = await _read_json_body(request)
        except (ValueError, json.JSONDecodeError) as exc:
            return _error_json(400, f"invalid JSON body: {exc}")
        return await _safe_json(lambda: update_connection(name, body))

    @application.delete("/connections/{name}")
    async def connection_delete(name: str) -> Response:
        return await _safe_json(lambda: delete_connection(name))

    @application.get("/connections/{name}/schema")
    async def connection_schema(name: str, request: Request) -> Response:
        database = request.query_params.get("database")
        schema_param = request.query_params.get("schema")
        relation = request.query_params.get("relation")
        return await _safe_json(
            lambda: get_connection_schema(
                name, database=database, schema=schema_param, relation=relation
            )
        )

    @application.post("/sessions", dependencies=[Depends(_require_session_auth)])
    async def create_session(request: Request) -> Response:
        try:
            body = await _read_json_body(request)
        except (ValueError, json.JSONDecodeError) as exc:
            return _error_json(400, f"invalid JSON body: {exc}")

        def _create() -> dict[str, Any]:
            graph_payload = body.get("graph")
            graph = (
                _graph_from_session_payload(graph_payload) if graph_payload is not None else None
            )
            session = get_default_session_store().create(graph)
            return session.model_dump(mode="json")

        return await _session_json(_create)

    @application.get("/sessions", dependencies=[Depends(_require_session_auth)])
    async def list_sessions() -> Response:
        def _list() -> dict[str, Any]:
            sessions = get_default_session_store().list()
            return {"sessions": [s.model_dump(mode="json") for s in sessions]}

        return await _session_json(_list)

    @application.get("/sessions/{session_id}", dependencies=[Depends(_require_session_auth)])
    async def get_session(session_id: str) -> Response:
        def _get() -> dict[str, Any]:
            return get_default_session_store().get(session_id).model_dump(mode="json")

        return await _session_json(_get)

    @application.delete("/sessions/{session_id}", dependencies=[Depends(_require_session_auth)])
    async def delete_session(session_id: str) -> Response:
        def _delete() -> dict[str, Any]:
            get_default_session_store().delete(session_id)
            return {"status": "ok"}

        return await _session_json(_delete)

    @application.put("/sessions/{session_id}/graph", dependencies=[Depends(_require_session_auth)])
    async def replace_session_graph(session_id: str, request: Request) -> Response:
        try:
            body = await _read_json_body(request)
        except (ValueError, json.JSONDecodeError) as exc:
            return _error_json(400, f"invalid JSON body: {exc}")

        def _replace() -> dict[str, Any]:
            graph_payload = body.get("graph")
            if not isinstance(graph_payload, dict):
                raise ValueError("PUT /sessions/{id}/graph requires a 'graph' object in the body")
            expected_version = body.get("expected_version")
            if not isinstance(expected_version, int):
                raise ValueError(
                    "PUT /sessions/{id}/graph requires an integer 'expected_version' in the body"
                )
            graph = _graph_from_session_payload(graph_payload)
            session = get_default_session_store().replace_graph(
                session_id, graph, expected_version=expected_version
            )
            return session.model_dump(mode="json")

        return await _session_json(_replace)

    @application.post(
        "/sessions/{session_id}/proposals", dependencies=[Depends(_require_session_auth)]
    )
    async def create_proposal(session_id: str, request: Request) -> Response:
        try:
            body = await _read_json_body(request)
        except (ValueError, json.JSONDecodeError) as exc:
            return _error_json(400, f"invalid JSON body: {exc}")

        def _propose() -> dict[str, Any]:
            mutation = GraphMutation.model_validate(body)
            proposal = get_default_session_store().add_proposal(session_id, mutation)
            return proposal.model_dump(mode="json")

        return await _session_json(_propose)

    @application.post(
        "/sessions/{session_id}/proposals/{proposal_id}/accept",
        dependencies=[Depends(_require_session_auth)],
    )
    async def accept_proposal_route(session_id: str, proposal_id: str) -> Response:
        def _accept() -> dict[str, Any]:
            session = get_default_session_store().accept_proposal(session_id, proposal_id)
            return session.model_dump(mode="json")

        return await _session_json(_accept)

    @application.post(
        "/sessions/{session_id}/proposals/{proposal_id}/reject",
        dependencies=[Depends(_require_session_auth)],
    )
    async def reject_proposal_route(session_id: str, proposal_id: str) -> Response:
        def _reject() -> dict[str, Any]:
            session = get_default_session_store().reject_proposal(session_id, proposal_id)
            return session.model_dump(mode="json")

        return await _session_json(_reject)

    @application.get("/sessions/{session_id}/events", dependencies=[Depends(_require_session_auth)])
    async def session_events(session_id: str, request: Request) -> Response:
        try:
            q = await _run_sync(lambda: get_default_session_store().subscribe(session_id))
        except UnknownSessionError as exc:
            return _error_json(404, str(exc))

        async def body() -> AsyncIterator[bytes]:
            loop = asyncio.get_running_loop()
            try:
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        event = await loop.run_in_executor(None, lambda: q.get(timeout=1.0))
                    except queue.Empty:
                        continue
                    yield _sse_frame(event)
            finally:
                get_default_session_store().unsubscribe(session_id, q)

        return StreamingResponse(body(), media_type="text/event-stream")

    @application.post(
        "/sessions/{session_id}/reviews", dependencies=[Depends(_require_session_auth)]
    )
    async def create_review(session_id: str, request: Request) -> Response:
        try:
            body = await _read_json_body(request)
        except (ValueError, json.JSONDecodeError) as exc:
            return _error_json(400, f"invalid JSON body: {exc}")

        def _create() -> dict[str, Any]:
            thread = ReviewThread.model_validate(body)
            result = get_default_session_store().add_review(session_id, thread)
            return result.model_dump(mode="json")

        return await _session_json(_create)

    @application.get(
        "/sessions/{session_id}/reviews", dependencies=[Depends(_require_session_auth)]
    )
    async def list_reviews(session_id: str) -> Response:
        def _list() -> dict[str, Any]:
            session = get_default_session_store().get(session_id)
            threads = sorted(session.collab.reviews.values(), key=lambda t: t.id)
            return {"reviews": [t.model_dump(mode="json") for t in threads]}

        return await _session_json(_list)

    @application.post(
        "/sessions/{session_id}/reviews/{review_id}/comments",
        dependencies=[Depends(_require_session_auth)],
    )
    async def add_review_comment_route(
        session_id: str, review_id: str, request: Request
    ) -> Response:
        try:
            body = await _read_json_body(request)
        except (ValueError, json.JSONDecodeError) as exc:
            return _error_json(400, f"invalid JSON body: {exc}")

        def _comment() -> dict[str, Any]:
            comment = ReviewComment.model_validate(body)
            result = get_default_session_store().add_review_comment(session_id, review_id, comment)
            return result.model_dump(mode="json")

        return await _session_json(_comment)

    @application.post("/sessions/{session_id}/gates", dependencies=[Depends(_require_session_auth)])
    async def create_gate(session_id: str, request: Request) -> Response:
        try:
            body = await _read_json_body(request)
        except (ValueError, json.JSONDecodeError) as exc:
            return _error_json(400, f"invalid JSON body: {exc}")

        def _create() -> dict[str, Any]:
            gate = Gate.model_validate(body)
            result = get_default_session_store().open_gate(session_id, gate)
            return result.model_dump(mode="json")

        return await _session_json(_create)

    @application.get("/sessions/{session_id}/gates", dependencies=[Depends(_require_session_auth)])
    async def list_gates(session_id: str) -> Response:
        def _list() -> dict[str, Any]:
            session = get_default_session_store().get(session_id)
            gates = sorted(session.collab.gates.values(), key=lambda g: g.id)
            return {"gates": [g.model_dump(mode="json") for g in gates]}

        return await _session_json(_list)

    @application.post(
        "/sessions/{session_id}/gates/{gate_id}/close",
        dependencies=[Depends(_require_session_auth)],
    )
    async def close_gate_route(session_id: str, gate_id: str) -> Response:
        def _close() -> dict[str, Any]:
            result = get_default_session_store().close_gate(session_id, gate_id)
            return result.model_dump(mode="json")

        return await _session_json(_close)

    @application.post(
        "/sessions/{session_id}/gates/{gate_id}/skip",
        dependencies=[Depends(_require_session_auth)],
    )
    async def skip_gate_route(session_id: str, gate_id: str) -> Response:
        def _skip() -> dict[str, Any]:
            result = get_default_session_store().skip_gate(session_id, gate_id)
            return result.model_dump(mode="json")

        return await _session_json(_skip)

    @application.post(
        "/sessions/{session_id}/gates/{gate_id}/decisions",
        dependencies=[Depends(_require_session_auth)],
    )
    async def add_gate_decision_route(session_id: str, gate_id: str, request: Request) -> Response:
        try:
            body = await _read_json_body(request)
        except (ValueError, json.JSONDecodeError) as exc:
            return _error_json(400, f"invalid JSON body: {exc}")

        def _decision() -> dict[str, Any]:
            decision = Decision.model_validate(body)
            result = get_default_session_store().add_decision(session_id, gate_id, decision)
            return result.model_dump(mode="json")

        return await _session_json(_decision)

    @application.post(
        "/sessions/{session_id}/compile", dependencies=[Depends(_require_session_auth)]
    )
    async def compile_session_route(session_id: str) -> Response:
        def _compile() -> dict[str, Any]:
            return compile_session(session_id)

        return await _session_json(_compile)

    @application.post(
        "/sessions/{session_id}/execute", dependencies=[Depends(_require_session_auth)]
    )
    async def execute_session_route(session_id: str, request: Request) -> Response:
        try:
            body = await _read_json_body(request)
        except (ValueError, json.JSONDecodeError) as exc:
            return _error_json(400, f"invalid JSON body: {exc}")

        def _execute() -> dict[str, Any]:
            return execute_session(session_id, body)

        return await _session_json(_execute)

    @application.post("/consult")
    async def consult(request: Request) -> Response:
        try:
            body = await _read_json_body(request)
        except (ValueError, json.JSONDecodeError) as exc:
            return _error_json(400, f"invalid JSON body: {exc}")

        def _consult() -> dict[str, Any]:
            client = GatewayClient()
            return consult_graph(body, client=client)

        return await _safe_json(_consult)

    @application.post(
        "/sessions/{session_id}/consult", dependencies=[Depends(_require_session_auth)]
    )
    async def consult_session_route(session_id: str, request: Request) -> Response:
        try:
            body = await _read_json_body(request)
        except (ValueError, json.JSONDecodeError) as exc:
            return _error_json(400, f"invalid JSON body: {exc}")

        def _consult() -> dict[str, Any]:
            client = GatewayClient()
            return consult_session(session_id, body, client=client)

        return await _session_json(_consult)

    @application.get("/agents")
    async def list_agents() -> Response:
        return await _safe_json(lambda: {"agents": list_available_adapter_names()})

    @application.post("/sessions/{session_id}/chat", dependencies=[Depends(_require_session_auth)])
    async def start_chat(session_id: str, request: Request) -> Response:
        try:
            body = await _read_json_body(request)
        except (ValueError, json.JSONDecodeError) as exc:
            return _error_json(400, f"invalid JSON body: {exc}")

        backend = body.get("backend")
        if not isinstance(backend, str) or not backend:
            return _error_json(
                400, "POST /sessions/{id}/chat requires a non-empty 'backend' string"
            )
        message = body.get("message")
        if not isinstance(message, str) or not message:
            return _error_json(
                400, "POST /sessions/{id}/chat requires a non-empty 'message' string"
            )

        base_url = str(request.base_url)
        auth_token = _session_auth_token if _session_auth_required else None

        def _start() -> dict[str, Any]:
            turn = start_chat_turn(
                session_id, backend, message, base_url=base_url, auth_token=auth_token
            )
            return turn.model_dump(mode="json")

        return await _session_json(_start)

    @application.post(
        "/sessions/{session_id}/chat/{turn_id}/stop",
        dependencies=[Depends(_require_session_auth)],
    )
    async def stop_chat(session_id: str, turn_id: str) -> Response:
        def _stop() -> dict[str, Any]:
            stop_chat_turn(session_id, turn_id)
            session = get_default_session_store().get(session_id)
            turn = next(t for t in session.collab.chat.turns if t.id == turn_id)
            return turn.model_dump(mode="json")

        return await _session_json(_stop)

    @application.post(
        "/sessions/{session_id}/chat/end", dependencies=[Depends(_require_session_auth)]
    )
    async def end_chat_route(session_id: str) -> Response:
        def _end() -> dict[str, Any]:
            session = get_default_session_store().end_chat(session_id)
            return session.model_dump(mode="json")

        return await _session_json(_end)

    # -- Flow store routes (issue #114) ------------------------------------------

    @application.get("/flows")
    async def list_flows() -> Response:
        return await _safe_json(lambda: {"flows": get_default_flows().list()})

    @application.get("/flows/{slug}")
    async def get_flow(slug: str) -> Response:
        try:
            graph = await _run_sync(lambda: get_default_flows().get(slug))
        except UnknownFlowError as exc:
            return _error_json(404, str(exc))
        except InvalidSlugError as exc:
            return _error_json(400, str(exc))
        except Exception as exc:  # noqa: BLE001 - never crash the server on a store failure
            return _error_json(422, f"{type(exc).__name__}: {exc}")
        return JSONResponse(content=graph)

    @application.post("/flows")
    async def create_flow(request: Request) -> Response:
        try:
            body = await _read_json_body(request)
        except (ValueError, json.JSONDecodeError) as exc:
            return _error_json(400, f"invalid JSON body: {exc}")
        graph = body.get("graph")
        if not isinstance(graph, dict):
            return _error_json(400, "POST /flows requires a 'graph' object in the body")
        # `graph["name"]` is client-controlled and untyped JSON -- slugify() assumes a str
        # (calls .strip()/.lower() on it) and raises AttributeError on anything else (e.g. a
        # number, list, or bool), which would otherwise propagate out of this route as an
        # unhandled 500 instead of a clean error response. Guard the type here, not just
        # emptiness.
        raw_name = graph.get("name")
        name = raw_name if isinstance(raw_name, str) and raw_name.strip() else "Untitled"
        # `slug`, if given, is a raw request-body string, not something we ran through
        # `slugify()` ourselves -- FlowStore.save()/`_path()` is what actually rejects a
        # malformed or path-escaping value (InvalidSlugError below), so this route must never
        # assume a client-supplied slug is already safe.
        slug = body.get("slug") or slugify(name)
        try:
            result = await _run_sync(lambda: get_default_flows().save(slug, graph))
        except InvalidSlugError as exc:
            return _error_json(400, str(exc))
        except Exception as exc:  # noqa: BLE001 - never crash the server on a store failure
            return _error_json(422, f"{type(exc).__name__}: {exc}")
        return JSONResponse(content=result)

    @application.put("/flows/{slug}")
    async def update_flow(slug: str, request: Request) -> Response:
        try:
            body = await _read_json_body(request)
        except (ValueError, json.JSONDecodeError) as exc:
            return _error_json(400, f"invalid JSON body: {exc}")
        graph = body.get("graph")
        if not isinstance(graph, dict):
            return _error_json(400, "PUT /flows/{slug} requires a 'graph' object in the body")
        try:
            result = await _run_sync(lambda: get_default_flows().save(slug, graph))
        except InvalidSlugError as exc:
            return _error_json(400, str(exc))
        except Exception as exc:  # noqa: BLE001 - never crash the server on a store failure
            return _error_json(422, f"{type(exc).__name__}: {exc}")
        return JSONResponse(content=result)

    @application.delete("/flows/{slug}")
    async def delete_flow(slug: str) -> Response:
        try:
            await _run_sync(lambda: get_default_flows().delete(slug))
        except UnknownFlowError as exc:
            return _error_json(404, str(exc))
        except InvalidSlugError as exc:
            return _error_json(400, str(exc))
        except Exception as exc:  # noqa: BLE001 - never crash the server on a store failure
            return _error_json(422, f"{type(exc).__name__}: {exc}")
        return JSONResponse(content={"status": "ok"})

    @application.post("/flows/{slug}/rename")
    async def rename_flow(slug: str, request: Request) -> Response:
        try:
            body = await _read_json_body(request)
        except (ValueError, json.JSONDecodeError) as exc:
            return _error_json(400, f"invalid JSON body: {exc}")
        new_slug = body.get("new_slug")
        if not isinstance(new_slug, str) or not new_slug:
            return _error_json(
                400, "POST /flows/{slug}/rename requires a non-empty 'new_slug' string"
            )
        # `new_slug` is an unvalidated request-body string (the client slugifies before
        # sending, but the server must not trust that) -- FlowStore.rename() -> `_path()`
        # rejects anything that isn't a plain `slugify()`-shaped slug, closing off a path-
        # traversal write (e.g. `new_slug: "../../../../tmp/evil"` moving a flow file outside
        # the flow store's root via the underlying `os.replace()`).
        try:
            result = await _run_sync(lambda: get_default_flows().rename(slug, new_slug))
        except UnknownFlowError as exc:
            return _error_json(404, str(exc))
        except FlowAlreadyExistsError as exc:
            return _error_json(409, str(exc))
        except InvalidSlugError as exc:
            return _error_json(400, str(exc))
        except Exception as exc:  # noqa: BLE001 - never crash the server on a store failure
            return _error_json(422, f"{type(exc).__name__}: {exc}")
        return JSONResponse(content=result)

    # -- Run store routes (issue #120) -------------------------------------------

    @application.get("/runs")
    async def list_runs() -> Response:
        return await _safe_json(lambda: {"runs": get_default_runs().list()})

    @application.get("/runs/{run_id}")
    async def get_run(run_id: str) -> Response:
        try:
            result = await _run_sync(lambda: get_default_runs().get(run_id))
        except UnknownRunError as exc:
            return _error_json(404, str(exc))
        except Exception as exc:
            return _error_json(422, f"{type(exc).__name__}: {exc}")
        return JSONResponse(content=result)

    @application.get("/runs/{run_id}/graph")
    async def get_run_graph(run_id: str) -> Response:
        try:
            result = await _run_sync(lambda: get_default_runs().get_graph(run_id))
        except UnknownRunError as exc:
            return _error_json(404, str(exc))
        except Exception as exc:
            return _error_json(422, f"{type(exc).__name__}: {exc}")
        return JSONResponse(content=result)

    @application.delete("/runs/{run_id}")
    async def delete_run(run_id: str) -> Response:
        try:
            await _run_sync(lambda: get_default_runs().delete(run_id))
        except UnknownRunError as exc:
            return _error_json(404, str(exc))
        except Exception as exc:
            return _error_json(422, f"{type(exc).__name__}: {exc}")
        return JSONResponse(content={"status": "ok"})

    # -- Examples endpoint (issue #114) ------------------------------------------

    @application.get("/examples")
    async def list_examples() -> Response:
        def _list() -> dict[str, Any]:
            examples: list[dict[str, str]] = []
            if not _EXAMPLES_DIR.is_dir():
                return {"examples": examples}
            for json_path in sorted(_EXAMPLES_DIR.rglob("*.json")):
                try:
                    data = json.loads(json_path.read_text(encoding="utf-8"))
                except Exception:  # noqa: BLE001 - skip a malformed example, never crash the list
                    continue
                if not isinstance(data, dict) or "nodes" not in data:
                    continue
                name = data.get("name") or json_path.stem
                rel = str(json_path.relative_to(_EXAMPLES_DIR))
                examples.append({"name": name, "path": rel, "slug": slugify(name)})
            return {"examples": examples}

        return await _safe_json(_list)

    @application.get("/examples/{path:path}")
    async def get_example(path: str) -> Response:
        def _get() -> dict[str, Any]:
            target = (_EXAMPLES_DIR / path).resolve()
            if not target.is_relative_to(_EXAMPLES_DIR) or not target.is_file():
                raise FileNotFoundError(f"example not found: {path}")
            return json.loads(target.read_text(encoding="utf-8"))

        try:
            result = await _run_sync(_get)
        except FileNotFoundError as exc:
            return _error_json(404, str(exc))
        except Exception as exc:  # noqa: BLE001 - never crash the server on a store failure
            return _error_json(422, f"{type(exc).__name__}: {exc}")
        return JSONResponse(content=result)

    # Catch-all GET: serves static asset -> demo page (for "/" and "/index.html") -> 404.
    # Declared last so the explicit GET routes above take precedence.
    @application.get("/{full_path:path}")
    async def static_or_demo(full_path: str, request: Request) -> Response:
        url_path = request.url.path
        asset = await _run_sync(lambda: _static_file(url_path))
        if asset is not None:
            content_type = mimetypes.guess_type(asset.name)[0] or "application/octet-stream"
            content = await _run_sync(asset.read_bytes)
            return Response(content=content, media_type=content_type)
        if url_path in ("/", "/index.html"):
            return HTMLResponse(content=_INDEX_HTML)
        return _error_json(404, f"not found: {url_path}")

    # Catch-all POST: an unknown POST path is a 404 with the {"error": ...} shape
    # (rather than FastAPI's default {"detail": ...}); keeps the v0 contract.
    @application.post("/{full_path:path}")
    async def post_not_found(full_path: str, request: Request) -> Response:
        return _error_json(404, f"not found: {request.url.path}")

    return application


# One application instance for Uvicorn to serve (cheap to build at import time).
app = create_app()


def _open_browser(url: str) -> None:
    """Best-effort: open *url* in a browser tab; never fail the server if it can't.

    A headless host (CI, a server box) has no browser; ``webbrowser.open`` may return
    ``False`` or raise depending on the platform. Swallow everything -- opening a tab is
    a convenience, not a requirement for ``emergentflow serve`` to run.
    """
    with contextlib.suppress(Exception):
        webbrowser.open(url)


def _open_browser_when_ready(probe_host: str, port: int, url: str, timeout: float = 10.0) -> None:
    """Poll *probe_host*:*port* until it accepts connections, then open *url*.

    Uvicorn binds the listening socket only after ``uvicorn.run`` starts (unlike
    the old stdlib server, which bound synchronously in its constructor before
    ``serve()`` ever opened a browser tab) -- opening the browser unconditionally
    races a slow Uvicorn startup and can show "connection refused" instead of the
    canvas. Runs on a background thread so it never blocks ``uvicorn.run``.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with (
            contextlib.suppress(OSError),
            socket.create_connection((probe_host, port), timeout=0.25),
        ):
            break
        time.sleep(0.05)
    _open_browser(url)


def serve(
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
    cache_dir: str | None = None,
    cache_max_mb: float | None = None,
    session_token: str | None = None,
    runs_keep: int | None = None,
) -> None:
    """Boot the local canvas server on Uvicorn and block until interrupted.

    When *open_browser* is true (the default), a browser tab is opened at the served
    URL once the socket is actually accepting connections. ``0.0.0.0`` is shown/opened
    as ``127.0.0.1`` since a wildcard bind is not a browsable address.

    *cache_dir* and *cache_max_mb* configure the on-disk execution cache
    (Epic 7 Story 6) via ``configure_cache`` -- this MUST run before
    ``uvicorn.run`` starts accepting requests, since a first request would
    otherwise create the default cache singleton before it's configured, and
    ``configure_cache`` raises if called after that singleton already
    exists. ``None`` for either parameter means "use the built-in default"
    (``DEFAULT_CACHE_DIRNAME`` resolved under the current working directory,
    ``DEFAULT_CACHE_MAX_MB``).

    *session_token* configures the ``/sessions*`` bearer-token gate (ADR 0019):
    when *host* is ``"127.0.0.1"`` (the default), the session surface stays
    open, matching every other route's trusted-local-app model. For any other
    *host*, a token is REQUIRED -- from *session_token* if given, else from the
    ``EMERGENTFLOW_SESSION_TOKEN`` environment variable; if neither is set,
    ``serve`` raises rather than silently exposing the session surface on a
    non-loopback bind.
    """
    import uvicorn

    cache_root = (
        pathlib.Path(cache_dir)
        if cache_dir is not None
        else pathlib.Path.cwd() / DEFAULT_CACHE_DIRNAME
    )
    resolved_max_mb = cache_max_mb if cache_max_mb is not None else DEFAULT_CACHE_MAX_MB
    configure_cache(cache_root, max_mb=resolved_max_mb)

    # Configure the artifact store (partial runs, issue #105) alongside the
    # cache, in a sibling directory under the same parent. Same "must run before
    # the first request" contract as configure_cache.
    artifact_root = cache_root.parent / DEFAULT_ARTIFACT_DIRNAME
    configure_artifacts(artifact_root, max_mb=DEFAULT_ARTIFACT_MAX_MB)

    # Configure the flow store (saved user graphs, issue #114) alongside the cache
    # and artifacts, in a sibling directory under the same parent. Same "must run
    # before the first request" contract as configure_cache/configure_artifacts.
    flow_root = cache_root.parent / DEFAULT_FLOW_DIRNAME
    configure_flows(flow_root)

    # Configure the runs store (execution run history, Task 02) alongside the
    # cache, artifacts, and flows, in a sibling directory under the same parent.
    # Same "must run before the first request" contract as configure_cache.
    runs_root = cache_root.parent / DEFAULT_RUNS_DIRNAME
    resolved_runs_keep = runs_keep if runs_keep is not None else DEFAULT_RUNS_KEEP
    configure_runs(runs_root, keep=resolved_runs_keep)

    if host == "127.0.0.1":
        configure_session_auth(required=False)
    else:
        resolved_token = session_token or os.environ.get("EMERGENTFLOW_SESSION_TOKEN")
        if not resolved_token:
            raise ValueError(
                f"serve(host={host!r}) binds to a non-loopback host, which requires a "
                "session bearer token: pass session_token=... or set the "
                "EMERGENTFLOW_SESSION_TOKEN environment variable."
            )
        configure_session_auth(required=True, token=resolved_token)

    from emergentflow.collab.persona_defs import register_builtin_personas

    register_builtin_personas()

    browse_host = "127.0.0.1" if host == "0.0.0.0" else host  # noqa: S104
    url = f"http://{browse_host}:{port}"
    print(f"Emergent Flow - serving the local canvas at {url}  (Ctrl-C to stop)")
    if open_browser:
        threading.Thread(
            target=_open_browser_when_ready, args=(browse_host, port, url), daemon=True
        ).start()
    uvicorn.run(app, host=host, port=port, log_level="warning")
