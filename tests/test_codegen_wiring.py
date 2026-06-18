"""Tests for colonymind.codegen.wiring — input-wiring map, fan-in/out, cardinality
enforcement, and the dangling-port policy (Epic 2, Story 2)."""

from __future__ import annotations

import pytest

from colonymind.api import is_inspectable
from colonymind.codegen import CardinalityError
from colonymind.codegen.wiring import WiringMap, build_wiring_map
from colonymind.ir import Cardinality, Direction, Edge, Graph, Node, Port, PortRef

# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _node(
    label: str,
    *,
    ins: list[tuple[str, Cardinality]] | None = None,
    n_out: int = 1,
) -> Node:
    ports = [
        Port(name=name, direction=Direction.IN, cardinality=card) for name, card in (ins or [])
    ]
    ports += [Port(name=f"out{i}", direction=Direction.OUT) for i in range(n_out)]
    return Node(type="test.node", label=label, ports=ports)


def _out(node: Node, idx: int = 0) -> Port:
    return [p for p in node.ports if p.direction == Direction.OUT][idx]


def _in(node: Node, idx: int = 0) -> Port:
    return [p for p in node.ports if p.direction == Direction.IN][idx]


def _edge(src: Node, tgt: Node, *, src_out: int = 0, tgt_in: int = 0) -> Edge:
    return Edge(
        source=PortRef(node_id=src.id, port_id=_out(src, src_out).id),
        target=PortRef(node_id=tgt.id, port_id=_in(tgt, tgt_in).id),
    )


def _graph(nodes: list[Node], edges: list[Edge]) -> Graph:
    return Graph(nodes={n.id: n for n in nodes}, edges={e.id: e for e in edges})


def _src_keys(refs: list[PortRef]) -> set[tuple[str, str]]:
    return {(r.node_id, r.port_id) for r in refs}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_linear_binding_resolves_upstream() -> None:
    a = _node("A", n_out=1)
    b = _node("B", ins=[("in0", Cardinality.ONE)], n_out=0)
    g = _graph([a, b], [_edge(a, b)])
    wm = build_wiring_map(g)

    up = wm.upstream(b.id, _in(b).id)
    assert _src_keys(up) == {(a.id, _out(a).id)}
    assert wm.is_bound(b.id, _in(b).id) is True


def test_dangling_in_port_is_unbound_not_error() -> None:
    a = _node("A", ins=[("in0", Cardinality.ONE)], n_out=0)
    g = _graph([a], [])
    wm = build_wiring_map(g)

    assert wm.upstream(a.id, _in(a).id) == []
    assert wm.is_bound(a.id, _in(a).id) is False


def test_fan_in_many_collects_all_sources() -> None:
    a = _node("A", n_out=1)
    c = _node("C", n_out=1)
    b = _node("B", ins=[("in0", Cardinality.MANY)], n_out=0)
    g = _graph([a, c, b], [_edge(a, b), _edge(c, b)])
    wm = build_wiring_map(g)

    up = wm.upstream(b.id, _in(b).id)
    assert _src_keys(up) == {(a.id, _out(a).id), (c.id, _out(c).id)}


def test_fan_in_into_cardinality_one_raises() -> None:
    a = _node("A", n_out=1)
    c = _node("C", n_out=1)
    b = _node("B", ins=[("in0", Cardinality.ONE)], n_out=0)
    g = _graph([a, c, b], [_edge(a, b), _edge(c, b)])
    with pytest.raises(CardinalityError) as exc:
        build_wiring_map(g)
    assert "ONE" in str(exc.value)


def test_fan_out_consumers() -> None:
    a = _node("A", n_out=1)
    b = _node("B", ins=[("in0", Cardinality.ONE)], n_out=0)
    c = _node("C", ins=[("in0", Cardinality.ONE)], n_out=0)
    g = _graph([a, b, c], [_edge(a, b), _edge(a, c)])
    wm = build_wiring_map(g)

    cons = wm.consumers(a.id, _out(a).id)
    assert _src_keys(cons) == {(b.id, _in(b).id), (c.id, _in(c).id)}


def test_consumers_empty_when_out_port_unused() -> None:
    a = _node("A", n_out=1)
    g = _graph([a], [])
    wm = build_wiring_map(g)
    assert wm.consumers(a.id, _out(a).id) == []


def test_every_in_port_has_a_binding() -> None:
    a = _node("A", n_out=1)
    b = _node("B", ins=[("x", Cardinality.ONE), ("y", Cardinality.ONE)], n_out=0)
    g = _graph([a, b], [_edge(a, b, tgt_in=0)])
    wm = build_wiring_map(g)

    targets = {(bd.target.node_id, bd.target.port_id) for bd in wm.bindings}
    assert targets == {(b.id, _in(b, 0).id), (b.id, _in(b, 1).id)}


def test_upstream_unknown_port_raises_keyerror() -> None:
    a = _node("A", n_out=1)
    wm = build_wiring_map(_graph([a], []))
    with pytest.raises(KeyError):
        wm.upstream(a.id, "no-such-port")


def test_upstream_returns_a_copy_not_internal_state() -> None:
    # Mutating the list returned by upstream() must not corrupt the map's state.
    a = _node("A", n_out=1)
    b = _node("B", ins=[("in0", Cardinality.ONE)], n_out=0)
    wm = build_wiring_map(_graph([a, b], [_edge(a, b)]))

    up = wm.upstream(b.id, _in(b).id)
    up.append(PortRef(node_id="HACK", port_id="HACK"))

    assert _src_keys(wm.upstream(b.id, _in(b).id)) == {(a.id, _out(a).id)}


def test_map_is_inspectable_and_round_trips() -> None:
    a = _node("A", n_out=1)
    b = _node("B", ins=[("in0", Cardinality.MANY)], n_out=0)
    g = _graph([a, b], [_edge(a, b)])
    wm = build_wiring_map(g)

    assert is_inspectable(wm) is True

    restored = WiringMap.model_validate_json(wm.model_dump_json())
    # Indexes are rebuilt on deserialization, so lookups still work.
    assert _src_keys(restored.upstream(b.id, _in(b).id)) == {(a.id, _out(a).id)}
    assert restored == wm


def test_map_is_deterministic_across_insertion_order() -> None:
    a = _node("A", n_out=1)
    b = _node("B", ins=[("in0", Cardinality.ONE)], n_out=0)
    edges = [_edge(a, b)]
    g1 = Graph(nodes={a.id: a, b.id: b}, edges={e.id: e for e in edges})
    g2 = Graph(nodes={b.id: b, a.id: a}, edges={e.id: e for e in edges})
    assert build_wiring_map(g1) == build_wiring_map(g2)
