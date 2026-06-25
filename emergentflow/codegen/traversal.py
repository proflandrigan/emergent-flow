"""
emergentflow.codegen.traversal
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Deterministic graph traversal for the code-generation engine (Epic 2, Story 2).

Both ``compile_to_code`` (Story 5) and ``execute`` (Story 6) need to visit a
functional pipeline's nodes in dependency order: a node is emitted/run only after
every node feeding its IN ports. This module provides that ordering and rejects
cyclic functional graphs (which have no valid order) with a clear, node-naming
error.

The ordering is *deterministic*: ties between independent nodes are broken by
ascending node id, so the same graph always produces an identical order. Stable
output is required by the golden-file tests and the ADR-0002 equivalence invariant.
"""

from __future__ import annotations

import heapq

from emergentflow.api import public_op
from emergentflow.codegen.errors import CycleError
from emergentflow.ir.common import IRId
from emergentflow.ir.graph import Graph
from emergentflow.ir.node import Node


def _describe(node: Node) -> str:
    """Human-readable identifier for a node in error messages."""
    label = (node.label or "").strip()
    if label:
        return f"{label!r} (id={node.id})"
    return f"{node.type!r} (id={node.id})"


@public_op(name="ef.codegen.topological_sort")
def topological_sort(graph: Graph) -> list[IRId]:
    """Return the ids of *graph*'s nodes in deterministic topological order.

    A node always appears after every node that feeds one of its IN ports. Ties
    between independent nodes are broken by ascending node id, so the ordering is
    stable for a given graph regardless of node/edge insertion order.

    Parameters
    ----------
    graph:
        A structurally valid functional-pipeline Graph. Edge endpoints are
        assumed to reference existing nodes/ports (the Graph validator enforces
        this at construction time).

    Returns
    -------
    list[IRId]
        Every node id in the graph, in topological order.

    Raises
    ------
    CycleError
        If the graph contains a cycle (no topological order exists). The message
        names the nodes that remain on the cycle.
    """
    # In-degree and successor adjacency, counted per edge so parallel edges
    # (two edges between the same pair) are handled consistently.
    indegree: dict[IRId, int] = {node_id: 0 for node_id in graph.nodes}
    successors: dict[IRId, list[IRId]] = {node_id: [] for node_id in graph.nodes}

    for edge in graph.edges.values():
        successors[edge.source.node_id].append(edge.target.node_id)
        indegree[edge.target.node_id] += 1

    # Kahn's algorithm with a min-heap on node id for a deterministic tie-break.
    ready: list[IRId] = [nid for nid, deg in indegree.items() if deg == 0]
    heapq.heapify(ready)

    order: list[IRId] = []
    while ready:
        nid = heapq.heappop(ready)
        order.append(nid)
        for succ in successors[nid]:
            indegree[succ] -= 1
            if indegree[succ] == 0:
                heapq.heappush(ready, succ)

    if len(order) != len(graph.nodes):
        # Nodes that never reached in-degree 0 are on (or downstream of) a cycle.
        remaining = [nid for nid in graph.nodes if indegree[nid] > 0]
        names = ", ".join(_describe(graph.nodes[nid]) for nid in sorted(remaining))
        raise CycleError(
            "Functional-pipeline graph contains a cycle; no topological order "
            f"exists. Nodes on or downstream of the cycle: {names}. Functional "
            "pipelines must be acyclic."
        )

    return order
