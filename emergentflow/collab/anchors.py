"""
emergentflow.collab.anchors
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Shared graph-ID resolution used by review findings (``emergentflow.collab.review``) and guided
tours (``emergentflow.collab.tours``). Both anchor collaboration objects to real graph elements
and must reject anchors that point at nothing.

Pure helpers only. This module is never imported by emergentflow/__init__.py or
emergentflow/ir/*.
"""

from __future__ import annotations

from collections.abc import Iterable

from emergentflow.ir.graph import Graph


class AnchorError(Exception):
    """Raised when a review finding's or tour step's anchor (node_id/edge_id/port_id) doesn't
    resolve against the session's graph -- the server rejects unanchored objects rather than
    storing one that points at nothing (or, worse, at some OTHER graph's element)."""


def missing_node_ids(graph: Graph, ids: Iterable[str]) -> list[str]:
    """Return the ids from *ids* that are not top-level nodes of *graph*, in first-seen order,
    de-duplicated. Pure."""
    missing: list[str] = []
    seen: set[str] = set()
    for node_id in ids:
        if node_id in seen:
            continue
        seen.add(node_id)
        if node_id not in graph.nodes:
            missing.append(node_id)
    return missing
