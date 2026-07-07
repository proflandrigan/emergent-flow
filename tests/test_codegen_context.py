"""Tests for emergentflow.codegen.context — the per-node CodegenContext binding
context and `build_codegen_context` (Epic 2, Story 4)."""

from __future__ import annotations

import pytest

from emergentflow.codegen.context import CodegenContext, build_codegen_context
from emergentflow.codegen.naming import build_name_map
from emergentflow.codegen.wiring import build_wiring_map
from emergentflow.ir import Cardinality, Direction, Edge, Graph, Node, Port, PortRef
from emergentflow.nodes.examples import Anova, ImputeMissing, LoadCsv

# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _out_port(node: Node, name: str) -> Port:
    return next(p for p in node.ports if p.direction == Direction.OUT and p.name == name)


def _in_port(node: Node, name: str) -> Port:
    return next(p for p in node.ports if p.direction == Direction.IN and p.name == name)


def _graph(nodes: list[Node], edges: list[Edge] | None = None) -> Graph:
    edges = edges or []
    return Graph(nodes={n.id: n for n in nodes}, edges={e.id: e for e in edges})


# ---------------------------------------------------------------------------
# 1. preview identity
# ---------------------------------------------------------------------------


def test_preview_identity_for_anova() -> None:
    node = Anova().instantiate(group_col="g", value_col="v")
    ctx = CodegenContext.preview(node)

    assert ctx.in_var("frame") == "frame"
    assert ctx.out_var("result") == "result"


# ---------------------------------------------------------------------------
# 2. preview separates IN/OUT same-name
# ---------------------------------------------------------------------------


def test_preview_separates_in_and_out_with_same_name() -> None:
    node = ImputeMissing().instantiate()
    ctx = CodegenContext.preview(node)

    assert ctx.in_var("frame") == "frame"
    assert ctx.out_var("frame") == "frame"


# ---------------------------------------------------------------------------
# 3. in_var/out_var KeyError on unknown port name
# ---------------------------------------------------------------------------


def test_in_var_unknown_port_raises_key_error() -> None:
    ctx = CodegenContext(in_vars={}, out_vars={})
    with pytest.raises(KeyError):
        ctx.in_var("nope")


def test_out_var_unknown_port_raises_key_error() -> None:
    ctx = CodegenContext(in_vars={}, out_vars={})
    with pytest.raises(KeyError):
        ctx.out_var("nope")


# ---------------------------------------------------------------------------
# 4. graph-backed wiring
# ---------------------------------------------------------------------------


def test_build_codegen_context_resolves_upstream_and_own_out_vars() -> None:
    load_csv_node = LoadCsv().instantiate(path="x.csv")
    anova_node = Anova().instantiate(group_col="g", value_col="v")
    edge = Edge(
        source=PortRef(node_id=load_csv_node.id, port_id=_out_port(load_csv_node, "frame").id),
        target=PortRef(node_id=anova_node.id, port_id=_in_port(anova_node, "frame").id),
    )
    graph = _graph([load_csv_node, anova_node], [edge])
    name_map = build_name_map(graph)
    wiring_map = build_wiring_map(graph)

    ctx = build_codegen_context(anova_node, name_map, wiring_map)

    expected_in = name_map.var_for(load_csv_node.id, _out_port(load_csv_node, "frame").id)
    expected_out = name_map.var_for(anova_node.id, _out_port(anova_node, "result").id)

    assert ctx.in_var("frame") == expected_in
    assert ctx.out_var("result") == expected_out


# ---------------------------------------------------------------------------
# 5. dangling fallback
# ---------------------------------------------------------------------------


def test_build_codegen_context_dangling_in_port_binds_to_none_literal() -> None:
    """An unconnected IN port binds to the `None` literal (compiler.py's dangling-input
    guard already rejects this for *required* ports, so build_codegen_context only ever
    sees this case for a genuinely optional, unconnected port)."""
    anova_node = Anova().instantiate(group_col="g", value_col="v")
    graph = _graph([anova_node], [])
    name_map = build_name_map(graph)
    wiring_map = build_wiring_map(graph)

    ctx = build_codegen_context(anova_node, name_map, wiring_map)

    assert ctx.in_var("frame") == "None"


# ---------------------------------------------------------------------------
# 6. fan-in raises
# ---------------------------------------------------------------------------


def test_build_codegen_context_fan_in_raises_value_error() -> None:
    source_a = Node(
        type="test.source", label="A", ports=[Port(name="out", direction=Direction.OUT)]
    )
    source_b = Node(
        type="test.source", label="B", ports=[Port(name="out", direction=Direction.OUT)]
    )
    sink = Node(
        type="test.sink",
        label="Sink",
        ports=[Port(name="in0", direction=Direction.IN, cardinality=Cardinality.MANY)],
    )
    edges = [
        Edge(
            source=PortRef(node_id=source_a.id, port_id=_out_port(source_a, "out").id),
            target=PortRef(node_id=sink.id, port_id=_in_port(sink, "in0").id),
        ),
        Edge(
            source=PortRef(node_id=source_b.id, port_id=_out_port(source_b, "out").id),
            target=PortRef(node_id=sink.id, port_id=_in_port(sink, "in0").id),
        ),
    ]
    graph = _graph([source_a, source_b, sink], edges)
    name_map = build_name_map(graph)
    wiring_map = build_wiring_map(graph)

    with pytest.raises(ValueError, match="in0"):
        build_codegen_context(sink, name_map, wiring_map)
