"""
emergentflow.research.lineage
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Data lineage / provenance (Epic 16, Story 17).

``trace_lineage`` is a pure function computed on demand from the existing graph IR — lineage is
never stored as a Graph/Node/Edge schema field (mirrors ADR 0019's "state lives beside the
graph, never on it" discipline: adding a field would force a schema-version bump and break
older deployments, and two structurally-identical graphs shouldn't serialize differently based
on non-structural metadata).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from emergentflow.api import public_op
from emergentflow.ir.common import IRId
from emergentflow.ir.graph import Graph
from emergentflow.research.errors import UnknownNodeError

__all__ = ["LineageNode", "LineageEdge", "Lineage", "trace_lineage"]


@dataclass
class LineageNode:
    """One node in a traced lineage chain."""

    node_id: str
    node_type: str
    label: str | None


@dataclass
class LineageEdge:
    """One edge in a traced lineage chain, between two nodes both present in
    :attr:`Lineage.nodes`."""

    source_node_id: str
    source_port: str
    target_node_id: str
    target_port: str


@dataclass
class Lineage:
    """The upstream source -> transform -> artifact chain behind a target node.

    Attributes
    ----------
    target_node_id: the node id lineage was traced for.
    nodes: the target node plus every ancestor reachable by walking edges backward
        (source <- target), deduplicated, in deterministic topological order (the same order
        ``ef.codegen.topological_sort`` would assign the whole graph, filtered to this subset).
        The target node is always last.
    edges: every edge in *graph* whose source and target are both in ``nodes`` — i.e. the
        induced subgraph's edges — in deterministic order (following ``nodes``' topological
        order by source then target, with the edge id as the tie-break for parallel edges),
        so a graph traces identically regardless of the order its edges were added in.
    """

    target_node_id: str
    nodes: list[LineageNode] = field(default_factory=list)
    edges: list[LineageEdge] = field(default_factory=list)


@public_op(name="ef.research.trace_lineage")
def trace_lineage(graph: Graph, node_id: IRId) -> Lineage:
    """Trace the upstream lineage of *node_id* within *graph*.

    Walks edges backward from *node_id* (an edge's ``target.node_id`` -> its
    ``source.node_id``) to collect every ancestor node, handling branching (a node with
    multiple upstream sources) and merging (two paths converging on a shared ancestor)
    correctly via a visited-set BFS/DFS -- each ancestor is visited at most once regardless of
    how many downstream paths reach it.

    Parameters
    ----------
    graph:
        A structurally valid Graph (edge endpoints are assumed to reference existing
        nodes/ports -- the Graph validator enforces this at construction time).
    node_id:
        The id of the node to trace lineage for.

    Returns
    -------
    Lineage
        ``target_node_id=node_id``, ``nodes`` containing *node_id* and every ancestor in
        deterministic topological order (target last), and ``edges`` containing every edge of
        *graph* connecting two nodes both present in ``nodes``, itself in a deterministic
        order that does not depend on the order the edges were added to *graph*.

    Raises
    ------
    UnknownNodeError
        If *node_id* does not exist in *graph*.
    """
    # Deferred import: emergentflow.codegen's package __init__ eagerly imports
    # emergentflow.nodes (for the declarative compiler), which imports every reference node
    # including the research.build_report node -- which imports back from emergentflow.research.
    # A module-level import here would make that a real circular import whenever
    # emergentflow.research is the first of the two packages touched (e.g. iterating
    # emergentflow.__all__, where "research" precedes "codegen"). Deferring to call time avoids
    # it: by the time trace_lineage is actually invoked, both packages are already initialized.
    from emergentflow.codegen.traversal import topological_sort

    if node_id not in graph.nodes:
        raise UnknownNodeError(
            f"node {node_id!r} does not exist in this graph; known node ids: "
            f"{sorted(graph.nodes)!r}."
        )

    # Backward adjacency: node_id -> the node ids feeding one of its IN ports.
    predecessors: dict[str, list[str]] = {nid: [] for nid in graph.nodes}
    for edge in graph.edges.values():
        predecessors[edge.target.node_id].append(edge.source.node_id)

    visited: set[str] = {node_id}
    frontier = [node_id]
    while frontier:
        current = frontier.pop()
        for pred in predecessors[current]:
            if pred not in visited:
                visited.add(pred)
                frontier.append(pred)

    order = [nid for nid in topological_sort(graph) if nid in visited]

    nodes = [
        LineageNode(node_id=nid, node_type=graph.nodes[nid].type, label=graph.nodes[nid].label)
        for nid in order
    ]
    # Deterministic edge order, mirroring the discipline every other pass keeps
    # (`topological_sort`'s node-id tie-break, `build_wiring_map`'s sorted fan-in sources,
    # `validate`'s `sorted(graph.edges.items())`): iterating `graph.edges.values()` directly
    # would follow dict INSERTION order, so two structurally identical graphs whose edges
    # were added in a different order -- ordinary canvas editing -- would trace to different
    # `edges` orderings. Keyed to follow `order` (so hops read along the chain `nodes`
    # already presents) with the edge id as a final tie-break for parallel edges.
    position = {nid: i for i, nid in enumerate(order)}
    in_subgraph = [
        (edge_id, edge)
        for edge_id, edge in graph.edges.items()
        if edge.source.node_id in visited and edge.target.node_id in visited
    ]
    in_subgraph.sort(
        key=lambda item: (
            position[item[1].source.node_id],
            position[item[1].target.node_id],
            item[0],
        )
    )
    edges = [
        LineageEdge(
            source_node_id=edge.source.node_id,
            source_port=edge.source.port_id,
            target_node_id=edge.target.node_id,
            target_port=edge.target.port_id,
        )
        for _edge_id, edge in in_subgraph
    ]

    return Lineage(target_node_id=node_id, nodes=nodes, edges=edges)
