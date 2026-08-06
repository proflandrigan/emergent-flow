"""
emergentflow.collab.metrics
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Metric extraction from run payloads (Epic 17 Story 3).

Extracts named scalars from execution results for comparison across runs.
Pure functions over RunStore data — no I/O, no global state.
"""

from __future__ import annotations

from typing import Any


def extract_metric(
    payloads: dict[str, dict[str, dict[str, Any]]],
    node_id: str,
    metric_name: str,
) -> float | int | None:
    """Extract a named scalar metric from run payloads.

    Searches all ports of the given node for a scalar or record field matching
    metric_name. Returns the value if found, else None.
    """
    if node_id not in payloads:
        return None

    for port_name, payload in payloads[node_id].items():
        kind = payload.get("kind")

        if kind == "scalar":
            if metric_name == port_name:
                value = payload.get("value")
                if isinstance(value, (int, float)):
                    return value

        elif kind == "record":
            fields = payload.get("fields", {})
            if metric_name in fields:
                field_payload = fields[metric_name]
                if field_payload.get("kind") == "scalar":
                    value = field_payload.get("value")
                    if isinstance(value, (int, float)):
                        return value

    return None


def compare_metrics(
    value_a: float | int | None,
    value_b: float | int | None,
) -> dict[str, Any]:
    """Compute delta between two metric values.

    Returns {"before", "after", "delta", "delta_pct", "error"}. If either value is
    None the metric was missing and ``delta``/``delta_pct`` are None and ``error``
    names which side(s) were missing, so a caller can distinguish "metric absent"
    from "metric null".
    """
    missing = [side for side, v in (("before", value_a), ("after", value_b)) if v is None]
    if value_a is None or value_b is None:
        return {
            "before": value_a,
            "after": value_b,
            "delta": None,
            "delta_pct": None,
            "error": f"metric missing on: {', '.join(missing)}",
        }

    delta = value_b - value_a
    delta_pct = (delta / value_a * 100) if value_a != 0 else None

    return {
        "before": value_a,
        "after": value_b,
        "delta": delta,
        "delta_pct": delta_pct,
    }
