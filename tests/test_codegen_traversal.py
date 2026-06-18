"""Tests for colonymind.codegen.traversal — deterministic topological sort and
cycle detection (Epic 2, Story 2)."""

from __future__ import annotations

import pytest

from colonymind.codegen import CycleError
from colonymind.codegen.traversal import topological_sort
from colonymind.ir import Direction, Edge, Graph, Node, Port, PortRef

# ---------------------------------------------------------------------------
# Builders — small helpers for crafting graphs with valid ports/edges
# ---------------------------------------------------------------------------


def _node(label: str, *, n_in: int = 1, n_out: int = 1) -> Node:
    ports = [Port(name=f"in{i}", direction=Direction.IN) for i in range(n_in)]
    ports += [Port(name=f"out{i}", direction=Direction.OUT) for i in range(n_out)]
    return Node(type="test.node", label=label, ports=ports)


def _out_port(node: Node, idx: int = 0) -> Port:
    return [p for p in node.ports if p.direction == Direction.OUT][idx]


def _in_port(node: Node, idx: int = 0) -> Port:
    return [p for p in node.ports if p.direction == Direction.IN][idx]


def _edge(src: Node, tgt: Node, *, src_out: int = 0, tgt_in: int = 0) -> Edge:
    return Edge(
        source=PortRef(node_id=src.id, port_id=_out_port(src, src_out).id),
        target=PortRef(node_id=tgt.id, port_id=_in_port(tgt, tgt_in).id),
    )


def _graph(nodes: list[Node], edges: list[Edge]) -> Graph:
    return Graph(nodes={n.id: n for n in nodes}, edges={e.id: e for e in edges})


def _assert_valid_topo(graph: Graph, order: list[str]) -> None:
    assert set(order) == set(graph.nodes), "order must contain every node exactly once"
    assert len(order) == len(graph.nodes)
    pos = {nid: i for i, nid in enumerate(order)}
    for edge in graph.edges.values():
        assert pos[edge.source.node_id] < pos[edge.target.node_id], (
            "source must precede target in topological order"
        )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_empty_graph_returns_empty_order() -> None:
    assert topological_sort(Graph()) == []


def test_single_node() -> None:
    a = _node("A", n_in=0, n_out=0)
    assert topological_sort(_graph([a], [])) == [a.id]


def test_linear_chain_has_unique_order() -> None:
    a = _node("A", n_in=0)
    b = _node("B")
    c = _node("C", n_out=0)
    g = _graph([a, b, c], [_edge(a, b), _edge(b, c)])
    order = topological_sort(g)
    assert order == [a.id, b.id, c.id]
    _assert_valid_topo(g, order)


def test_diamond_fan_out_fan_in() -> None:
    a = _node("A", n_in=0, n_out=2)
    b = _node("B")
    c = _node("C")
    d = _node("D", n_in=2, n_out=0)
    g = _graph(
        [a, b, c, d],
        [
            _edge(a, b, src_out=0),
            _edge(a, c, src_out=1),
            _edge(b, d, tgt_in=0),
            _edge(c, d, tgt_in=1),
        ],
    )
    order = topological_sort(g)
    _assert_valid_topo(g, order)
    assert order[0] == a.id
    assert order[-1] == d.id


def test_fan_out_single_out_port_many_targets() -> None:
    a = _node("A", n_in=0, n_out=1)
    b = _node("B", n_out=0)
    c = _node("C", n_out=0)
    g = _graph([a, b, c], [_edge(a, b), _edge(a, c)])
    order = topological_sort(g)
    _assert_valid_topo(g, order)
    assert order[0] == a.id


def test_disconnected_nodes_all_present() -> None:
    a = _node("A", n_in=0, n_out=0)
    b = _node("B", n_in=0, n_out=0)
    order = topological_sort(_graph([a, b], []))
    assert set(order) == {a.id, b.id}


def test_cycle_raises_cycle_error_naming_nodes() -> None:
    a = _node("A")
    b = _node("B")
    g = _graph([a, b], [_edge(a, b), _edge(b, a)])
    with pytest.raises(CycleError) as exc:
        topological_sort(g)
    assert a.id in str(exc.value)
    assert b.id in str(exc.value)


def test_self_loop_raises_cycle_error() -> None:
    a = _node("A")
    with pytest.raises(CycleError):
        topological_sort(_graph([a], [_edge(a, a)]))


def test_tie_break_is_ascending_node_id() -> None:
    a = _node("A", n_in=0, n_out=0)
    b = _node("B", n_in=0, n_out=0)
    order = topological_sort(_graph([a, b], []))
    assert order == sorted([a.id, b.id])


def test_order_is_stable_across_insertion_order() -> None:
    a = _node("A", n_in=0, n_out=2)
    b = _node("B", n_out=0)
    c = _node("C", n_out=0)
    edges = [_edge(a, b), _edge(a, c, src_out=1)]
    g1 = Graph(nodes={a.id: a, b.id: b, c.id: c}, edges={e.id: e for e in edges})
    g2 = Graph(
        nodes={c.id: c, b.id: b, a.id: a},
        edges={e.id: e for e in reversed(edges)},
    )
    assert topological_sort(g1) == topological_sort(g2)
