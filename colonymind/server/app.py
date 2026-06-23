"""Thin local HTTP server for the bundled app (ADR 0013 Decision 2, §A6).

Zero-dependency v0: the Python **stdlib** ``http.server`` exposing the in-process
service functions over localhost. No auth, no sandbox, no async -- the JupyterLab
trust model (you run your own code on your own machine). The FastAPI / WebSocket
streaming upgrade is the documented Phase-2 step; this v0 deliberately keeps the
bundled install lean and fully CI-testable.

Routes:
- ``GET  /``          -- a minimal paste-IR demo page (proves the loop end to end)
- ``GET  /healthz``   -- ``{"status": "ok"}``
- ``POST /compile``   -- IR JSON -> ``{"code": ...}``
- ``POST /execute``   -- IR JSON -> ``{"results": ...}``
- ``POST /validate``  -- IR JSON -> ``{"diagnostics": ...}``
"""

from __future__ import annotations

import json
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from colonymind.server.service import compile_graph, execute_graph, validate_graph

_ROUTES: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "/compile": compile_graph,
    "/execute": execute_graph,
    "/validate": validate_graph,
}

# A deliberately tiny single-page client: paste IR JSON, hit a button, see the
# result. It is the throwaway "prove the canvas -> IR -> code -> execute loop"
# stopgap, not the real ui/ canvas (roadmap Epic 3); keep lines <= 100 chars.
_INDEX_HTML = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Colony Mind - local</title></head>
<body style="font-family: system-ui; max-width: 60rem; margin: 2rem auto;">
  <h1>Colony Mind &mdash; local canvas (v0)</h1>
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
    server_version = "colonymind-serve/0"

    def _send_json(self, status: int, body: dict[str, Any]) -> None:
        self._send(status, "application/json", json.dumps(body).encode())

    def _send(self, status: int, content_type: str, data: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            self._send(200, "text/html; charset=utf-8", _INDEX_HTML.encode())
        elif self.path == "/healthz":
            self._send_json(200, {"status": "ok"})
        else:
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
            # Report any cm.* failure as JSON; the local dev server must never
            # crash on a bad graph -- it just hands the error back to the canvas.
            self._send_json(422, {"error": f"{type(exc).__name__}: {exc}"})

    def log_message(self, format: str, *args: Any) -> None:
        # Quiet by default; a v0 local server need not spam stderr per request.
        return


def make_server(host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    """Build (but do not start) the local HTTP server."""
    return ThreadingHTTPServer((host, port), _Handler)


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    """Boot the local canvas server and block until interrupted."""
    httpd = make_server(host, port)
    print(f"Colony Mind - serving the local canvas at http://{host}:{port}  (Ctrl-C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down")
    finally:
        httpd.server_close()
