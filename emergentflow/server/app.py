"""Thin local HTTP server for the bundled app (ADR 0013 Decision 2, §A6).

Zero-dependency v0: the Python **stdlib** ``http.server`` exposing the in-process
service functions over localhost. No auth, no sandbox, no async -- the JupyterLab
trust model (you run your own code on your own machine). The FastAPI / WebSocket
streaming upgrade is the documented Phase-2 step; this v0 deliberately keeps the
bundled install lean and fully CI-testable.

Routes:
- ``GET  /``          -- serves ``_static/index.html`` when present, else the demo page
- ``GET  /healthz``   -- ``{"status": "ok"}``
- ``GET  /schema``    -- the IR JSON Schema
- ``GET  /catalog``   -- ``{"catalog_version": <int>, "nodes": [<NodeSpec>, ...]}`` (ADR 0015)
- ``POST /compile``   -- IR JSON -> ``{"code": ...}``
- ``POST /execute``   -- IR JSON -> ``{"results": ..., "statuses": ...}``
- ``POST /execute_node`` -- ``{"graph", "run_node", "inputs"}`` -> single-node run
- ``POST /validate``  -- IR JSON -> ``{"diagnostics": ...}``
"""

from __future__ import annotations

import contextlib
import json
import mimetypes
import pathlib
import webbrowser
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from emergentflow.server.service import (
    compile_graph,
    execute_graph,
    execute_node,
    get_catalog,
    get_schema,
    validate_graph,
)

_ROUTES: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "/compile": compile_graph,
    "/execute": execute_graph,
    "/execute_node": execute_node,
    "/validate": validate_graph,
}

_GET_ROUTES: dict[str, Callable[[], dict[str, Any]]] = {
    "/schema": get_schema,
    "/catalog": get_catalog,
}

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


class _Handler(BaseHTTPRequestHandler):
    server_version = "emergentflow-serve/0"

    def _send_json(self, status: int, body: dict[str, Any]) -> None:
        self._send(status, "application/json", json.dumps(body).encode())

    def _send(self, status: int, content_type: str, data: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path == "/healthz":
            self._send_json(200, {"status": "ok"})
            return
        url_path = self.path.split("?", 1)[0]  # ignore any query string
        get_handler = _GET_ROUTES.get(url_path)
        if get_handler is not None:
            try:
                self._send_json(200, get_handler())
            except Exception as exc:
                self._send_json(422, {"error": f"{type(exc).__name__}: {exc}"})
            return
        asset = _static_file(url_path)
        if asset is not None:
            content_type = mimetypes.guess_type(asset.name)[0] or "application/octet-stream"
            self._send(200, content_type, asset.read_bytes())
            return
        if url_path in ("/", "/index.html"):
            # No bundled UI present -- fall back to the throwaway v0 demo page.
            self._send(200, "text/html; charset=utf-8", _INDEX_HTML.encode())
            return
        self._send_json(404, {"error": f"not found: {self.path}"})

    def do_POST(self) -> None:
        handler = _ROUTES.get(self.path)
        if handler is None:
            self._send_json(404, {"error": f"not found: {self.path}"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError) as exc:
            self._send_json(400, {"error": f"invalid JSON body: {exc}"})
            return
        try:
            self._send_json(200, handler(payload))
        except Exception as exc:
            # Report any ef.* failure as JSON; the local dev server must never
            # crash on a bad graph -- it just hands the error back to the canvas.
            self._send_json(422, {"error": f"{type(exc).__name__}: {exc}"})

    def log_message(self, format: str, *args: Any) -> None:
        # Quiet by default; a v0 local server need not spam stderr per request.
        return


def _open_browser(url: str) -> None:
    """Best-effort: open *url* in a browser tab; never fail the server if it can't.

    A headless host (CI, a server box) has no browser; ``webbrowser.open`` may return
    ``False`` or raise depending on the platform. Swallow everything -- opening a tab is
    a convenience, not a requirement for ``emergentflow serve`` to run.
    """
    with contextlib.suppress(Exception):
        webbrowser.open(url)


def make_server(host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    """Build (but do not start) the local HTTP server."""
    return ThreadingHTTPServer((host, port), _Handler)


def serve(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    """Boot the local canvas server and block until interrupted.

    When *open_browser* is true (the default), a browser tab is opened at the served
    URL once the socket is listening. ``0.0.0.0`` is shown/opened as ``127.0.0.1`` since
    a wildcard bind is not a browsable address.
    """
    httpd = make_server(host, port)
    browse_host = "127.0.0.1" if host == "0.0.0.0" else host  # noqa: S104
    url = f"http://{browse_host}:{port}"
    print(f"Emergent Flow - serving the local canvas at {url}  (Ctrl-C to stop)")
    if open_browser:
        _open_browser(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down")
    finally:
        httpd.server_close()
