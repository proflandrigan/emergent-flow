"""
emergentflow.validity.traversal
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Pure graph-topology helpers for validity rules (Epic 17).

Rules reason about reachability: "is a fitting transform upstream of a split?",
"does a windowing transform cross a split boundary?". These helpers compute
that reachability deterministically over the whole graph tree (top-level edges
plus every nested ``Node.subgraph``), so a rule never has to hand-roll
traversal and results stay golden-testable.
"""

from __future__ import annotations

from emergentflow.ir import Edge, Graph

IRId = str


def all_edges(graph: Graph) -> list[Edge]:
    """Every edge in the graph tree, top-level first then nested subgraphs.

    Subgraphs are walked depth-first in ``graph.nodes`` dict order. The result
    is deterministic for a given graph. Used so rules see composite containers'
    internal wiring without special-casing nesting.
    """
    edges: list[Edge] = list(graph.edges.values())
    for node in graph.nodes.values():
        if node.subgraph is not None:
            edges.extend(all_edges(node.subgraph))
    return edges


def _adjacency(
    edges: list[Edge],
) -> tuple[dict[IRId, set[IRId]], dict[IRId, set[IRId]]]:
    """Build forward and reverse adjacency maps over *edges*.

    ``fwd[n]`` = the set of node ids with an edge FROM n; ``rev[n]`` = the set
    of node ids with an edge INTO n. Edges reference endpoints as
    ``(source.node_id, source.port_id) -> (target.node_id, target.port_id)``;
    only the node ids matter for reachability.
    """
    fwd: dict[IRId, set[IRId]] = {}
    rev: dict[IRId, set[IRId]] = {}
    for edge in edges:
        src = edge.source.node_id
        dst = edge.target.node_id
        fwd.setdefault(src, set()).add(dst)
        rev.setdefault(dst, set()).add(src)
    return fwd, rev


def upstream(graph: Graph, node_id: IRId) -> set[IRId]:
    """All nodes that can reach *node_id* through a directed path, exclusive.

    Transitive closure over reversed edges. ``node_id`` itself is excluded.
    Deterministic: computed via a worklist; the returned set's *contents* are
    deterministic (set order is irrelevant to callers, which test membership).
    """
    _, rev = _adjacency(all_edges(graph))
    seen: set[IRId] = set()
    stack = list(rev.get(node_id, set()))
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        stack.extend(rev.get(current, set()))
    return seen


def downstream(graph: Graph, node_id: IRId) -> set[IRId]:
    """All nodes reachable from *node_id* through a directed path, exclusive.

    Transitive closure over forward edges. ``node_id`` itself is excluded.
    """
    fwd, _ = _adjacency(all_edges(graph))
    seen: set[IRId] = set()
    stack = list(fwd.get(node_id, set()))
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        stack.extend(fwd.get(current, set()))
    return seen


def reaches(graph: Graph, source: IRId, target: IRId) -> bool:
    """``True`` when a directed path exists from *source* to *target*."""
    return target in downstream(graph, source)
