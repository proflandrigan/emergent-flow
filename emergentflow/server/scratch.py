"""Scratch "explore this output" runs (issue #178, task 2).

``POST /scratch/run`` runs an ad-hoc ``def transform(value):`` against one *stored* node
output (``ArtifactStore``) so an EDA user can ask a one-off question -- a grouped
calculation, a fix for an error -- without touching the graph. The code runs through the
same ``emergentflow.script`` seam a ``script.custom_code`` node uses, so promoting a
scratch to a node (the UI's "Save as code node") gives the same result by construction.

This executes arbitrary code in the server process (the same unsandboxed trust level as
``custom_code``); the route is therefore gated in ``app.py`` to loopback clients or a
presented token. See ``docs/runbook.md``.

Binding: the request names ``(node_id, port, revision)``. If the stored output was replaced
or evicted the run is refused (``revision_mismatch`` / ``expired``) -- never silently
rebound to newer data, so what the user explored is what they promote.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any

from emergentflow.script import CaptureResult, TransformError, run_transform_capture
from emergentflow.server.artifacts import get_default_artifacts
from emergentflow.server.service import _payload_for

# Soft wall-clock limit. Python cannot kill a running thread, so on timeout the worker is
# abandoned (daemon thread) and keeps running until it finishes; only the response is cut off.
SCRATCH_TIMEOUT_S = 30.0
MAX_RESULT_BYTES = 4 * 1024 * 1024  # cap on the serialised result payload
MAX_OUTPUT_CHARS = 65536  # cap on captured stdout / stderr each
MAX_REPR_CHARS = 2000


def _copy_for_transform(value: Any) -> Any:
    """A DataFrame/Series copy so ``transform`` cannot mutate the loaded artifact."""
    import pandas as pd

    if isinstance(value, (pd.DataFrame, pd.Series)):
        return value.copy()
    return value


def _run_with_timeout(code: str, value: Any, timeout_s: float) -> CaptureResult:
    box: list[CaptureResult] = []
    worker = threading.Thread(
        target=lambda: box.append(run_transform_capture(code, value)), daemon=True
    )
    worker.start()
    worker.join(timeout_s)
    if not box:
        msg = f"transform did not finish within {timeout_s:g}s (the thread cannot be killed)"
        return CaptureResult(None, "", "", TransformError("TimeoutError", msg, msg, None))
    return box[0]


def _result_payload(value: Any) -> dict[str, Any]:
    """Node-output payload for *value*, degrading to a repr for anything unconvertible/huge."""
    try:
        payload = _payload_for(value)
        if len(json.dumps(payload)) <= MAX_RESULT_BYTES:
            return payload
        reason = "result exceeds the size cap"
    except Exception as exc:  # noqa: BLE001 - a bad return value must not fail the run
        reason = f"{type(exc).__name__}: {exc}"
    try:
        text = repr(value)
    except Exception:  # noqa: BLE001
        text = f"<{type(value).__name__}: repr failed>"
    return {
        "kind": "unsupported",
        "type": type(value).__name__,
        "repr": f"{text[:MAX_REPR_CHARS]}  ({reason})",
    }


def run_scratch(payload: dict[str, Any]) -> dict[str, Any]:
    """``POST /scratch/run``: {node_id, port, revision, code} -> a status envelope.

    ``status`` is ``ok`` | ``error`` (user code failed; ``error`` has type/message/
    traceback/line) | ``expired`` (no stored output) | ``revision_mismatch`` (stored output
    replaced; ``current_revision`` says which). All four are HTTP 200; only a malformed
    request raises (-> 422).
    """
    node_id, port, code = payload.get("node_id"), payload.get("port"), payload.get("code")
    if not isinstance(node_id, str) or not isinstance(port, str) or not isinstance(code, str):
        raise ValueError("scratch run requires string 'node_id', 'port' and 'code'")
    revision = payload.get("revision")
    started = time.perf_counter()

    def envelope(status: str, **extra: Any) -> dict[str, Any]:
        return {
            "status": status,
            "revision": revision,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
            **extra,
        }

    hit = get_default_artifacts().get_with_revision(node_id)
    if hit is None:
        return envelope("expired")
    outputs, current = hit
    if current != revision:
        return envelope("revision_mismatch", current_revision=current)
    if port not in outputs:
        return envelope(
            "error",
            error={
                "type": "KeyError",
                "message": f"stored output has no port {port!r}",
                "traceback": "",
                "line": None,
            },
        )

    outcome = _run_with_timeout(code, _copy_for_transform(outputs[port]), SCRATCH_TIMEOUT_S)
    streams = {
        "stdout": outcome.stdout[:MAX_OUTPUT_CHARS],
        "stderr": outcome.stderr[:MAX_OUTPUT_CHARS],
    }
    if outcome.error is not None:
        err = outcome.error
        error = {"type": err.type, "message": err.message, "traceback": err.traceback}
        return envelope("error", **streams, error={**error, "line": err.line})
    return envelope("ok", **streams, result=_result_payload(outcome.value))
