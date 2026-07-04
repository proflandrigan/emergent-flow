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
- ``GET  /catalog``          -- ``{"catalog_version": <int>, "nodes": [...], "estimators": [...]}``
  (ADR 0015)
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
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import mimetypes
import pathlib
import queue
import socket
import threading
import time
import webbrowser
from collections.abc import AsyncIterator, Awaitable, Callable, Generator
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse

from emergentflow.server.cache import DEFAULT_CACHE_DIRNAME, DEFAULT_CACHE_MAX_MB, configure_cache
from emergentflow.server.reports import get_default_store
from emergentflow.server.service import (
    clear_cache,
    compile_graph,
    execute_graph,
    execute_graph_stream,
    execute_node,
    export_eval_set_bytes,
    export_finetune_bytes,
    get_catalog,
    get_schema,
    label_eval,
    validate_graph,
)

# The built UI is bundled into emergentflow/_static/ by the package build hook
# (ADR 0013 Decision 1). It is absent in a source checkout / before `vite build`,
# so every read is guarded and the server falls back to the v0 demo page.
# app.py lives at emergentflow/server/app.py; parents[1] is the emergentflow/ package root.
_STATIC_DIR = pathlib.Path(__file__).resolve().parents[1] / "_static"


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
    "/eval/label": label_eval,
    "/execute": execute_graph,
    "/execute_node": execute_node,
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

    @application.get("/healthz")
    async def healthz() -> JSONResponse:
        return JSONResponse(content={"status": "ok"})

    @application.get("/schema")
    async def schema() -> Response:
        return await _safe_json(get_schema)

    @application.get("/catalog")
    async def catalog() -> Response:
        return await _safe_json(get_catalog)

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

    # Catch-all GET: static asset -> demo page (for "/" and "/index.html") -> 404.
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
    """
    import uvicorn

    cache_root = (
        pathlib.Path(cache_dir)
        if cache_dir is not None
        else pathlib.Path.cwd() / DEFAULT_CACHE_DIRNAME
    )
    resolved_max_mb = cache_max_mb if cache_max_mb is not None else DEFAULT_CACHE_MAX_MB
    configure_cache(cache_root, max_mb=resolved_max_mb)

    browse_host = "127.0.0.1" if host == "0.0.0.0" else host  # noqa: S104
    url = f"http://{browse_host}:{port}"
    print(f"Emergent Flow - serving the local canvas at {url}  (Ctrl-C to stop)")
    if open_browser:
        threading.Thread(
            target=_open_browser_when_ready, args=(browse_host, port, url), daemon=True
        ).start()
    uvicorn.run(app, host=host, port=port, log_level="warning")
