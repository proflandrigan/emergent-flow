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
    _derive_source_cols,
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


def test_trace_column_lineage_case_when_derives_from_condition() -> None:
    """A case-when derived column's lineage walks the columns in its ``when``
    conditions, not just a bare ``expr`` (Epic 18 Story 3)."""
    load = get("data.load_csv")().instantiate(label="load")
    derive = get("clean.derive_column")().instantiate(
        label="derive",
        columns=[
            {
                "name": "bucket",
                "when": [{"if": "revenue > 100", "then": "high"}],
                "else": "low",
            }
        ],
    )
    acc: dict = {"_edges": []}
    edges = _flow(acc, load, derive)
    graph = Graph(
        paradigm=Paradigm.FUNCTIONAL,
        name="case-when-flow",
        nodes={n.id: n for n in (load, derive)},
        edges=edges,
    )
    lineage = trace_column_lineage(graph, derive.id, "bucket")
    derived = next(n for n in lineage.nodes if n.node_type == "clean.derive_column")
    assert derived.role == ColumnRole.DERIVED
    assert derived.source_column == "revenue"
    assert derived.detail and "revenue" in derived.detail
    assert any(n.node_type == "data.load_csv" and n.column == "revenue" for n in lineage.nodes)


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


def test_trace_column_lineage_custom_code_observed_is_unknown() -> None:
    """Even when a last-run `observed` schema refines a custom_code node's output
    column, custom_code must still break the chain as UNKNOWN -- never be asserted as
    a data SOURCE (the docstring/comment contract)."""
    load = get("data.load_csv")().instantiate(label="load")
    custom = get("script.custom_code")().instantiate(label="custom")
    acc: dict = {"_edges": []}
    e = _link_out_to_in(acc, load, custom, in_name="value")
    graph = Graph(
        paradigm=Paradigm.FUNCTIONAL,
        name="custom-observed-flow",
        nodes={n.id: n for n in (load, custom)},
        edges={e.id: e},
    )
    observed = {custom.id: ["anything"], load.id: ["anything", "col_a"]}
    lineage = trace_column_lineage(graph, custom.id, "anything", observed=observed)
    # custom_code breaks the chain: UNKNOWN boundary, never a SOURCE claim.
    assert any(n.role == ColumnRole.UNKNOWN for n in lineage.nodes)
    assert not any(
        n.role == ColumnRole.SOURCE and n.node_type == "script.custom_code" for n in lineage.nodes
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


def test_trace_column_impact_tolerates_cycle() -> None:
    """A cyclic graph must not crash trace_column_impact (it falls back to insertion
    order, mirroring trace_column_lineage), rather than raising a bare CycleError."""
    n = get("clean.impute_missing")().instantiate(label="n")
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
    impact = trace_column_impact(graph, n.id, "x")
    assert len(impact.nodes) >= 1


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


def test_trace_column_impact_stops_at_select_drop() -> None:
    """Impact analysis must not propagate a seed column past a select that drops it.

    load -> select(drop revenue) -> derive2(double2 = revenue*2): revenue is
    removed by the select, so derive2's ``double2`` cannot be derived from it.
    The blast radius terminates at the select; the downstream derive is not
    reported as impacted (Epic 18, Story 6).
    """
    load = get("data.load_csv")().instantiate(label="load")
    select = get("clean.select_columns")().instantiate(
        label="select", columns=["revenue"], drop=True
    )
    derive2 = get("clean.derive_column")().instantiate(
        label="derive2", columns=[{"name": "double2", "expr": "revenue * 2"}]
    )
    acc: dict = {"_edges": []}
    edges = _flow(acc, load, select, derive2)
    graph = Graph(
        paradigm=Paradigm.FUNCTIONAL,
        name="impact-drop",
        nodes={n.id: n for n in (load, select, derive2)},
        edges=edges,
    )
    impact = trace_column_impact(graph, load.id, "revenue")
    # The seed column reaches the select's input but not its output; nothing
    # downstream of the select is seeded by `revenue`.
    assert not any(
        n.node_type == "clean.derive_column" and n.column == "double2" for n in impact.nodes
    )
    assert not any(
        n.node_type == "clean.derive_column" and n.column == "revenue" for n in impact.nodes
    )
    # No edge may claim `revenue` flows into the select (it does not survive it).
    assert not any(
        e.target_node_id == select.id and e.source_column == "revenue" for e in impact.edges
    )


def test_trace_column_impact_edges_require_surviving_column() -> None:
    """Impact edges must only be emitted for a column that survives into the
    target's output. `revenue` reaches derive (it is the source of revenue_log)
    but is dropped by the select -- so no edge carries `revenue` into the
    select. The derived `revenue_log` is kept by the select, so it legitimately
    passes through it (a derived column preserved by the node survives)."""
    load = get("data.load_csv")().instantiate(label="load")
    derive = get("clean.derive_column")().instantiate(
        label="derive", columns=[{"name": "revenue_log", "expr": "log1p(revenue)"}]
    )
    select = get("clean.select_columns")().instantiate(
        label="select", columns=["revenue_log", "user_id"]
    )
    acc: dict = {"_edges": []}
    edges = _flow(acc, load, derive, select)
    graph = Graph(
        paradigm=Paradigm.FUNCTIONAL,
        name="impact-keep",
        nodes={n.id: n for n in (load, derive, select)},
        edges=edges,
    )
    impact = trace_column_impact(graph, load.id, "revenue")
    # The seed `revenue` is dropped by the select: no edge carries it into the
    # select. The derived `revenue_log` survives the select, so it does flow
    # through it.
    assert not any(
        e.target_node_id == select.id and e.source_column == "revenue" for e in impact.edges
    )
    assert {e.source_column for e in impact.edges if e.target_node_id == derive.id} == {"revenue"}
    assert {e.source_column for e in impact.edges if e.target_node_id == select.id} == {
        "revenue_log"
    }


# ---------------------------------------------------------------------------
# Regression tests
# ---------------------------------------------------------------------------


def test_derive_source_cols_excludes_module_base_of_qualified_call() -> None:
    """A qualified call's module base (``np`` in ``np.sqrt``) is an operator,
    not a column reference (bug 2)."""
    assert _derive_source_cols("np.sqrt(c) + a") == ("a", "c")
    # ``np`` is the base of a bare function call, not an operand column.
    assert "np" not in _derive_source_cols("np.sqrt(c) + a")
    assert _derive_source_cols("np.log1p(x)") == ("x",)
    assert "np" not in _derive_source_cols("np.log1p(x)")
    # A bare function call name is likewise excluded, not a column.
    assert _derive_source_cols("log1p(x)") == ("x",)


def test_trace_column_impact_flows_through_derived_column() -> None:
    """Impact seeded at `x` must flow through a derived column `y` so a
    transitive consumer `z = y + 1` is reported as impacted (bug 1)."""
    load = get("data.load_csv")().instantiate(label="load")
    der = get("clean.derive_column")().instantiate(
        label="der", columns=[{"name": "y", "expr": "x * 2"}]
    )
    down = get("clean.derive_column")().instantiate(
        label="down", columns=[{"name": "z", "expr": "y + 1"}]
    )
    acc: dict = {"_edges": []}
    edges = _flow(acc, load, der, down)
    graph = Graph(
        paradigm=Paradigm.FUNCTIONAL,
        name="impact-multihop",
        nodes={n.id: n for n in (load, der, down)},
        edges=edges,
    )
    impact = trace_column_impact(graph, load.id, "x")
    # `down.z` is derived from `y`, which is itself derived from `x` -- so it
    # must be reported as impacted with a DERIVED role.
    assert any(
        n.node_type == "clean.derive_column" and n.column == "z" and n.role == ColumnRole.DERIVED
        for n in impact.nodes
    )
    # The intermediate derived column `y` is reported as impacted too.
    assert any(
        n.node_type == "clean.derive_column" and n.column == "y" and n.role == ColumnRole.DERIVED
        for n in impact.nodes
    )
