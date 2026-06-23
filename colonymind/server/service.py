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
from colonymind.ir import Graph
from colonymind.ir.serialize import deserialize_graph


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


def execute_graph(payload: dict[str, Any]) -> dict[str, Any]:
    """IR graph (as a dict) -> ``{"results": <per-node outputs, JSON-safe>}``."""
    return {"results": _jsonable(execute(_to_graph(payload)))}
