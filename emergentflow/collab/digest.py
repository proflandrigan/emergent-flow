"""
emergentflow.collab.digest
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Payload digest layer for agent consumption (Epic 17 Story 2).

Reduces execution result payloads to bounded summaries suitable for LLM context
windows. Scalars/records pass through verbatim; tables become shape+dtypes+head;
images/figures become presence markers with handles for on-demand fetch.

Never imported by ``emergentflow/__init__.py`` or ``emergentflow/ir/*`` —
collaboration state lives beside the graph (ADR 0019).
"""

from __future__ import annotations

import json
from typing import Any

MAX_DIGEST_BYTES = 50 * 1024  # 50KB hard cap on total digest size
MAX_TABLE_HEAD_ROWS = 5  # Rows to keep in table digests
MAX_JSON_CHARS = 1024  # JSON payloads larger than this get truncated


def digest_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Reduce a single payload to a bounded digest for agent consumption.

    Returns a new dict with the same ``kind`` discriminator but reduced content.
    Images become summaries with handles; tables keep only shape+head; scalars
    pass through verbatim.
    """
    kind = payload.get("kind")

    if kind == "scalar":
        return payload

    if kind == "text":
        return payload

    if kind == "table":
        head = payload.get("head", [])
        if len(head) > MAX_TABLE_HEAD_ROWS:
            head = head[:MAX_TABLE_HEAD_ROWS]
        return {
            "kind": "table",
            "columns": payload.get("columns", []),
            "dtypes": payload.get("dtypes", []),
            "shape": payload.get("shape", [0, 0]),
            "head": head,
            "truncated": True,  # Always mark as truncated in digest
        }

    if kind == "record":
        fields = payload.get("fields", {})
        digested_fields = {name: digest_payload(field) for name, field in fields.items()}
        return {
            "kind": "record",
            "type": payload.get("type", "unknown"),
            "fields": digested_fields,
        }

    if kind == "json":
        value = payload.get("value")
        serialized = json.dumps(value, separators=(",", ":"))
        if len(serialized) <= MAX_JSON_CHARS:
            return payload
        return {
            "kind": "json",
            "value": serialized[:MAX_JSON_CHARS],
            "truncated": True,
            "original_bytes": len(serialized),
        }

    if kind == "image":
        # Replace with summary, no base64 data
        data = payload.get("data", "")
        return {
            "kind": "image_summary",
            "mime": payload.get("mime", "image/png"),
            "width": payload.get("width", 0),
            "height": payload.get("height", 0),
            "bytes": len(data) * 3 // 4,  # Approximate original bytes from base64
            "handle": f"image:{payload.get('width', 0)}x{payload.get('height', 0)}",
        }

    if kind == "html":
        value = payload.get("value", "")
        return {
            "kind": "html_summary",
            "bytes": len(value),
            "handle": f"html:{len(value)}bytes",
        }

    if kind == "unsupported":
        return payload

    # Unknown kind: pass through
    return payload


def digest_results(
    results: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, dict[str, dict[str, Any]]]:
    """Digest a full result payload (node_id -> port_name -> payload).

    Returns a new dict with the same structure but digested payloads.
    Applies a hard cap on total digest size (50KB). If exceeded, truncates
    from the end with explicit markers.
    """
    digested: dict[str, dict[str, dict[str, Any]]] = {}
    total_bytes = 0

    for node_id, ports in results.items():
        digested_ports: dict[str, dict[str, Any]] = {}
        for port_name, payload in ports.items():
            if total_bytes >= MAX_DIGEST_BYTES:
                # Hard cap exceeded: add truncation marker
                digested_ports[port_name] = {
                    "kind": "truncated",
                    "reason": "digest size limit exceeded",
                }
                continue

            digested_payload = digest_payload(payload)
            digested_ports[port_name] = digested_payload

            # Estimate size
            serialized = json.dumps(digested_payload, separators=(",", ":"))
            total_bytes += len(serialized)

        digested[node_id] = digested_ports

    return digested
