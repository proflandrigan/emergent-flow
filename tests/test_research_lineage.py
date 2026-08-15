"""Tests for emergentflow.research.lineage (Epic 16, Story 17).

Exercises trace_lineage over branching and merging DAGs, plus the inspectable
contract and the error path for unknown nodes.
"""

from __future__ import annotations

import pytest

from emergentflow.api import is_inspectable
from emergentflow.ir import Direction, Graph, Node, Paradigm, Port, Position
from emergentflow.ir.edge import Edge, PortRef
from emergentflow.research.errors import UnknownNodeError
from emergentflow.research.lineage import Lineage, LineageEdge, LineageNode, trace_lineage

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _node(
    id_: str,
    type_: str = "data.load_csv",
    label: str | None = None,
    in_ports: list[str] | None = None,
    out_ports: list[str] | None = None,
) -> Node:
    return Node(
        id=id_,
        type=type_,
        label=label,
        paradigm=Paradigm.FUNCTIONAL,
        ports=[
            Port(id=f"p-{id_}-{name}", name=name, direction=Direction.IN, data_type="DataFrame")
            for name in (in_ports or [])
        ]
        + [
            Port(id=f"p-{id_}-{name}", name=name, direction=Direction.OUT, data_type="DataFrame")
            for name in (out_ports or [])
        ],
        position=Position(x=0.0, y=0.0),
    )


def _edge(id_: str, src: str, src_port: str, tgt: str, tgt_port: str) -> Edge:
    return Edge(
        id=id_,
        source=PortRef(node_id=src, port_id=f"p-{src}-{src_port}"),
        target=PortRef(node_id=tgt, port_id=f"p-{tgt}-{tgt_port}"),
    )


def _diamond_graph() -> Graph:
    """A diamond: A -> {B, C} -> D.

    Four edges: A->B, A->C, B->D, C->D.
    """
    a = _node("a", label="A", out_ports=["out"])
    b = _node("b", type_="clean.impute_missing", label="B", in_ports=["in"], out_ports=["out"])
    c = _node("c", type_="clean.impute_missing", label="C", in_ports=["in"], out_ports=["out"])
    d = _node("d", label="D", in_ports=["in_b", "in_c"])
    edges = {
        "e-ab": _edge("e-ab", "a", "out", "b", "in"),
        "e-ac": _edge("e-ac", "a", "out", "c", "in"),
        "e-bd": _edge("e-bd", "b", "out", "d", "in_b"),
        "e-cd": _edge("e-cd", "c", "out", "d", "in_c"),
    }
    return Graph(
        paradigm=Paradigm.FUNCTIONAL,
        name="diamond",
        nodes={n.id: n for n in (a, b, c, d)},
        edges=edges,
    )


# ---------------------------------------------------------------------------
# trace_lineage
# ---------------------------------------------------------------------------


def test_trace_lineage_linear_chain() -> None:
    a = _node("a", label="A", out_ports=["out"])
    b = _node("b", type_="clean.impute_missing", label="B", in_ports=["in"], out_ports=["out"])
    c = _node("c", label="C", in_ports=["in"])
    edges = {
        "e-ab": _edge("e-ab", "a", "out", "b", "in"),
        "e-bc": _edge("e-bc", "b", "out", "c", "in"),
    }
    graph = Graph(
        paradigm=Paradigm.FUNCTIONAL,
        name="linear",
        nodes={n.id: n for n in (a, b, c)},
        edges=edges,
    )

    lineage = trace_lineage(graph, "c")

    assert [n.node_id for n in lineage.nodes] == ["a", "b", "c"]
    assert len(lineage.edges) == 2
    assert (
        LineageEdge(
            source_node_id="a", source_port="p-a-out", target_node_id="b", target_port="p-b-in"
        )
        in lineage.edges
    )
    assert (
        LineageEdge(
            source_node_id="b", source_port="p-b-out", target_node_id="c", target_port="p-c-in"
        )
        in lineage.edges
    )


def test_trace_lineage_no_upstream() -> None:
    a = _node("a", type_="data.load_csv", label="A", out_ports=["out"])
    graph = Graph(
        paradigm=Paradigm.FUNCTIONAL,
        name="single",
        nodes={"a": a},
        edges={},
    )

    lineage = trace_lineage(graph, "a")

    assert lineage == Lineage(
        target_node_id="a",
        nodes=[LineageNode(node_id="a", node_type="data.load_csv", label="A")],
        edges=[],
    )


def test_trace_lineage_diamond_branch_and_merge() -> None:
    graph = _diamond_graph()

    # -- Trace D (merge point) --
    lineage = trace_lineage(graph, "d")
    assert {n.node_id for n in lineage.nodes} == {"a", "b", "c", "d"}
    assert lineage.nodes[-1].node_id == "d"
    a_pos = next(i for i, n in enumerate(lineage.nodes) if n.node_id == "a")
    b_pos = next(i for i, n in enumerate(lineage.nodes) if n.node_id == "b")
    c_pos = next(i for i, n in enumerate(lineage.nodes) if n.node_id == "c")
    assert a_pos < b_pos
    assert a_pos < c_pos
    edge_pairs = {(e.source_node_id, e.target_node_id) for e in lineage.edges}
    assert edge_pairs == {("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")}

    # -- Trace B (branch point, not the merge) --
    lineage = trace_lineage(graph, "b")
    assert {n.node_id for n in lineage.nodes} == {"a", "b"}
    assert len(lineage.edges) == 1
    assert lineage.edges[0].source_node_id == "a"
    assert lineage.edges[0].target_node_id == "b"

    # -- Trace A (root) --
    lineage = trace_lineage(graph, "a")
    assert [n.node_id for n in lineage.nodes] == ["a"]
    assert lineage.edges == []


def test_trace_lineage_unrelated_branch_is_excluded() -> None:
    graph = _diamond_graph()
    e = _node("e", label="E", out_ports=["out"])
    graph.nodes["e"] = e

    lineage = trace_lineage(graph, "b")
    assert "e" not in {n.node_id for n in lineage.nodes}


def test_trace_lineage_unknown_node_raises() -> None:
    a = _node("a", out_ports=["out"])
    graph = Graph(
        paradigm=Paradigm.FUNCTIONAL,
        name="tiny",
        nodes={"a": a},
        edges={},
    )
    with pytest.raises(UnknownNodeError) as exc_info:
        trace_lineage(graph, "does-not-exist")
    assert issubclass(UnknownNodeError, ValueError)
    assert "does-not-exist" in str(exc_info.value)


def test_trace_lineage_result_is_inspectable() -> None:
    a = _node("a", label="A", out_ports=["out"])
    b = _node("b", type_="clean.impute_missing", label="B", in_ports=["in"], out_ports=["out"])
    c = _node("c", label="C", in_ports=["in"])
    edges = {
        "e-ab": _edge("e-ab", "a", "out", "b", "in"),
        "e-bc": _edge("e-bc", "b", "out", "c", "in"),
    }
    graph = Graph(
        paradigm=Paradigm.FUNCTIONAL,
        name="linear",
        nodes={n.id: n for n in (a, b, c)},
        edges=edges,
    )
    result = trace_lineage(graph, "c")
    assert is_inspectable(result) is True


def test_trace_lineage_edge_order_is_insertion_order_independent() -> None:
    """Two structurally identical graphs must trace to an identical Lineage.

    ``edges`` was built by iterating ``graph.edges.values()``, i.e. dict INSERTION order, so
    adding the same edges in a different order -- ordinary canvas editing -- produced a
    different ``edges`` ordering for the same graph, while ``nodes`` (via
    ``topological_sort``) was correctly stable. Every other pass in the codebase pins this
    down explicitly, so lineage must too.
    """
    all_edges = {
        "e-ab": _edge("e-ab", "a", "out", "b", "in"),
        "e-ac": _edge("e-ac", "a", "out", "c", "in"),
        "e-bd": _edge("e-bd", "b", "out", "d", "in_b"),
        "e-cd": _edge("e-cd", "c", "out", "d", "in_c"),
    }

    def _build(edge_ids: list[str]) -> Graph:
        a = _node("a", label="A", out_ports=["out"])
        b = _node("b", type_="clean.impute_missing", label="B", in_ports=["in"], out_ports=["out"])
        c = _node("c", type_="clean.impute_missing", label="C", in_ports=["in"], out_ports=["out"])
        d = _node("d", label="D", in_ports=["in_b", "in_c"])
        return Graph(
            paradigm=Paradigm.FUNCTIONAL,
            name="diamond",
            nodes={n.id: n for n in (a, b, c, d)},
            edges={eid: all_edges[eid] for eid in edge_ids},
        )

    forward = trace_lineage(_build(["e-ab", "e-ac", "e-bd", "e-cd"]), "d")
    reversed_ = trace_lineage(_build(["e-cd", "e-bd", "e-ac", "e-ab"]), "d")

    assert forward.nodes == reversed_.nodes
    assert forward.edges == reversed_.edges
    # And the order follows `nodes`' topological order by source, then target.
    assert [(e.source_node_id, e.target_node_id) for e in forward.edges] == [
        ("a", "b"),
        ("a", "c"),
        ("b", "d"),
        ("c", "d"),
    ]


def test_trace_lineage_tolerates_cycle() -> None:
    """A degenerate cyclic graph (which the structural validator permits) must not
    crash trace_lineage -- it falls back to insertion order, like trace_column_lineage."""
    a = _node("a", type_="clean.impute_missing", in_ports=["in"], out_ports=["out"])
    b = _node("b", type_="clean.impute_missing", in_ports=["in"], out_ports=["out"])
    graph = Graph(
        paradigm=Paradigm.FUNCTIONAL,
        name="cyclic",
        nodes={n.id: n for n in (a, b)},
        edges={
            "e-ab": _edge("e-ab", "a", "out", "b", "in"),
            "e-ba": _edge("e-ba", "b", "out", "a", "in"),
        },
    )
    result = trace_lineage(graph, a.id)
    assert {n.node_id for n in result.nodes} == {a.id, b.id}
