"""Tests for the ``reports.result_card`` presentation-only node."""

from __future__ import annotations

import ast

import emergentflow as ef
import emergentflow.nodes.examples  # noqa: F401  (fires node registration)
from emergentflow.ir.common import Direction
from emergentflow.ir.edge import Edge, PortRef
from emergentflow.ir.graph import Graph
from emergentflow.nodes.examples import LoadSample, ResultCard
from emergentflow.nodes.registry import registry


def test_registered() -> None:
    defn = registry.get("reports.result_card")
    assert defn is ResultCard
    assert defn.family == "reports"


def test_codegen_is_empty_and_execute_returns_empty() -> None:
    defn = ResultCard()
    node = defn.instantiate()
    assert defn.preview(node).body == ""
    assert defn.execute(node, {"results": []}) == {}


def test_compile_and_execute_graph_with_card() -> None:
    load = LoadSample().instantiate(name="iris")
    card = ResultCard().instantiate()
    out = next(p for p in load.ports if p.direction == Direction.OUT and p.name == "frame")
    inp = next(p for p in card.ports if p.direction == Direction.IN and p.name == "results")
    edge = Edge(
        source=PortRef(node_id=load.id, port_id=out.id),
        target=PortRef(node_id=card.id, port_id=inp.id),
    )
    graph = Graph(nodes={load.id: load, card.id: card}, edges={edge.id: edge})

    ast.parse(ef.compile_to_code(graph))
    ef.execute(graph)
