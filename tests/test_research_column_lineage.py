"""Tests for emergentflow.research.lineage column lineage (Epic 18, Stories 1, 3, 6).

Exercises trace_column_lineage and trace_column_impact over a cleaning/feature
flow: a source load node, a derive_column producing a new feature, and a
select_columns gate. Also verifies the inspectable contract and the honest
"unknown" boundary for undeclared transformers.
"""

from __future__ import annotations

import json

import pytest

from emergentflow.api import is_inspectable
from emergentflow.ir import Paradigm
from emergentflow.ir.edge import Edge, PortRef
from emergentflow.ir.graph import Graph
from emergentflow.nodes.registry import get
from emergentflow.research.errors import UnknownNodeError
from emergentflow.research.lineage import (
    ColumnRole,
    trace_column_impact,
    trace_column_lineage,
)


def _port(node, name: str, direction: str):
    return next(p for p in node.ports if p.name == name and p.direction.value == direction)


def _link(acc, source, target) -> Edge:
    n = len(acc["_edges"])
    edge_id = f"{source.id}-{target.id}-e{n}"
    acc["_edges"].append(edge_id)
    return Edge(
        id=edge_id,
        source=PortRef(node_id=source.id, port_id=_port(source, "frame", "out").id),
        target=PortRef(node_id=target.id, port_id=_port(target, "frame", "in").id),
    )


def _link_out_to_in(acc, source, target, out_name="frame", in_name="frame") -> Edge:
    n = len(acc["_edges"])
    edge_id = f"{source.id}-{target.id}-e{n}"
    acc["_edges"].append(edge_id)
    return Edge(
        id=edge_id,
        source=PortRef(node_id=source.id, port_id=_port(source, out_name, "out").id),
        target=PortRef(node_id=target.id, port_id=_port(target, in_name, "in").id),
    )


def _flow(acc, *order):
    edges = {}
    for i in range(len(order) - 1):
        e = _link(acc, order[i], order[i + 1])
        edges[e.id] = e
    return edges


def _load_derive_select_flow():
    """load_csv -> derive_column(revenue_log=log1p(revenue)) -> select_columns(keep)."""
    acc: dict = {"_edges": []}
    load = get("data.load_csv")().instantiate(label="load")
    derive = get("clean.derive_column")().instantiate(
        label="derive", columns=[{"name": "revenue_log", "expr": "log1p(revenue)"}]
    )
    select = get("clean.select_columns")().instantiate(
        label="select", columns=["revenue_log", "user_id"]
    )
    edges = _flow(acc, load, derive, select)
    graph = Graph(
        paradigm=Paradigm.FUNCTIONAL,
        name="cleaning-flow",
        nodes={n.id: n for n in (load, derive, select)},
        edges=edges,
    )
    return graph, load, derive, select


# ---------------------------------------------------------------------------
# trace_column_lineage
# ---------------------------------------------------------------------------


def test_trace_column_lineage_derivation_chain() -> None:
    graph, _load, derive, select = _load_derive_select_flow()
    lineage = trace_column_lineage(graph, select.id, "revenue_log")

    assert lineage.target_node_id == select.id
    assert lineage.target_column == "revenue_log"
    # sources first, target last (deterministic topological order)
    by_id = {n.node_type: n for n in lineage.nodes}
    assert lineage.nodes[0].node_type == "data.load_csv"
    assert lineage.nodes[-1].node_type == "clean.select_columns"

    derived = by_id["clean.derive_column"]
    assert derived.role == ColumnRole.DERIVED
    assert derived.source_column == "revenue"
    assert derived.detail and "revenue" in derived.detail

    source = by_id["data.load_csv"]
    assert source.column == "revenue"
    assert source.role == ColumnRole.SOURCE

    sel = by_id["clean.select_columns"]
    assert sel.role == ColumnRole.PASSTHROUGH


def test_trace_column_lineage_edges_walk_chain() -> None:
    graph, load, derive, select = _load_derive_select_flow()
    lineage = trace_column_lineage(graph, select.id, "revenue_log")
    edge_pairs = {(e.source_node_id, e.source_column, e.target_node_id) for e in lineage.edges}
    assert edge_pairs == {
        (derive.id, "revenue_log", select.id),
        (load.id, "revenue", derive.id),
    }


def test_trace_column_lineage_unknown_boundary_for_undeclared_node() -> None:
    """A transformer with no declaration terminates as an explicit unknown."""
    load = get("data.load_csv")().instantiate(label="load")
    custom = get("script.custom_code")().instantiate(label="custom")
    acc: dict = {"_edges": []}
    e = _link_out_to_in(acc, load, custom, in_name="value")
    graph = Graph(
        paradigm=Paradigm.FUNCTIONAL,
        name="custom-flow",
        nodes={n.id: n for n in (load, custom)},
        edges={e.id: e},
    )
    lineage = trace_column_lineage(graph, custom.id, "anything")
    # custom_code is undeclared -> unknown boundary, chain does not continue to load.
    assert any(n.role == ColumnRole.UNKNOWN for n in lineage.nodes)
    assert not any(
        n.role == ColumnRole.SOURCE and n.node_type == "data.load_csv" for n in lineage.nodes
    )


def test_trace_column_lineage_result_is_inspectable_and_jsonable() -> None:
    graph, _load, _derive, select = _load_derive_select_flow()
    lineage = trace_column_lineage(graph, select.id, "revenue_log")
    assert is_inspectable(lineage) is True
    json.loads(json.dumps(lineage, default=lambda o: o.__dict__))


def test_trace_column_lineage_unknown_node_raises() -> None:
    graph, _load, _derive, _select = _load_derive_select_flow()
    with pytest.raises(UnknownNodeError):
        trace_column_lineage(graph, "does-not-exist", "col")


def test_trace_column_lineage_cycle_safe() -> None:
    """A degenerate self-cycle must not loop forever."""
    n = get("clean.impute_missing")().instantiate(label="n")
    # self-edge on the out->in frame ports of the single node
    e = Edge(
        id="self",
        source=PortRef(node_id=n.id, port_id=_port(n, "frame", "out").id),
        target=PortRef(node_id=n.id, port_id=_port(n, "frame", "in").id),
    )
    graph = Graph(
        paradigm=Paradigm.FUNCTIONAL,
        name="loop",
        nodes={n.id: n},
        edges={e.id: e},
    )
    lineage = trace_column_lineage(graph, n.id, "x")
    assert len(lineage.nodes) >= 1


# ---------------------------------------------------------------------------
# trace_column_impact
# ---------------------------------------------------------------------------


def test_trace_column_impact_reaches_downstream() -> None:
    graph, load, derive, select = _load_derive_select_flow()
    impact = trace_column_impact(graph, load.id, "revenue")

    assert impact.target_node_id == load.id
    assert impact.target_column == "revenue"
    assert impact.nodes[0].node_type == "data.load_csv"
    assert len(impact.nodes) >= 2  # source + at least one consumer
    assert any(n.column == "revenue_log" and n.role == ColumnRole.DERIVED for n in impact.nodes)
