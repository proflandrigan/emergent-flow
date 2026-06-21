"""
tests/test_codegen_inference.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Tests for colonymind.codegen.inference — the whole-graph type-inference pass
(Epic 3, Story 4). Covers a linear chain, diamond fan-out/fan-in, a dangling
IN port, and a node whose OUT type depends on its inputs.
"""

from __future__ import annotations

from typing import Any

from colonymind.api import is_inspectable
from colonymind.codegen.inference import _reduce_inbound_types, infer_graph_types
from colonymind.ir import Cardinality, Direction, Edge, Graph, Node, Port, PortRef
from colonymind.nodes.contract import NodeDefinition
from colonymind.nodes.registry import NodeRegistry
from colonymind.nodes.spec import PortSpec


def _graph(nodes: list[Node], edges: list[Edge]) -> Graph:
    return Graph(nodes={n.id: n for n in nodes}, edges={e.id: e for e in edges})


def test_linear_chain_propagates_declared_out_types() -> None:
    load = Node(
        id="n-load",
        type="data.load_csv",
        label="Load CSV",
        ports=[
            Port(
                id="p-load-frame",
                name="frame",
                direction=Direction.OUT,
                data_type="DataFrame",
            ),
        ],
    )
    report = Node(
        id="n-report",
        type="reports.generate_html_summary",
        label="HTML Summary",
        ports=[
            Port(
                id="p-report-frame",
                name="frame",
                direction=Direction.IN,
                data_type="DataFrame",
            ),
            Port(
                id="p-report-html",
                name="html",
                direction=Direction.OUT,
                data_type="HTML",
            ),
        ],
    )
    edge = Edge(
        id="e1",
        source=PortRef(node_id="n-load", port_id="p-load-frame"),
        target=PortRef(node_id="n-report", port_id="p-report-frame"),
    )
    g = _graph([load, report], [edge])

    result = infer_graph_types(g)

    assert result.type_of("n-load", "p-load-frame") == "DataFrame"
    assert result.type_of("n-report", "p-report-html") == "HTML"
    assert result.unbound == []
    assert is_inspectable(result)


def _src(node_id: str, port_id: str, data_type: str = "DataFrame") -> Node:
    """A source node (one OUT port, no IN ports), type unregistered on purpose."""
    return Node(
        id=node_id,
        type="test.source",
        label=node_id,
        ports=[
            Port(id=port_id, name="out0", direction=Direction.OUT, data_type=data_type),
        ],
    )


def test_diamond_fan_out_and_fan_in_resolves_all_outputs() -> None:
    # a -> b, a -> c (fan-out); b -> d, c -> d (fan-in into a MANY port).
    a = _src("n-a", "p-a-out", "DataFrame")
    b = Node(
        id="n-b",
        type="test.mid",
        label="B",
        ports=[
            Port(id="p-b-in", name="in0", direction=Direction.IN, data_type="DataFrame"),
            Port(id="p-b-out", name="out0", direction=Direction.OUT, data_type="DataFrame"),
        ],
    )
    c = Node(
        id="n-c",
        type="test.mid",
        label="C",
        ports=[
            Port(id="p-c-in", name="in0", direction=Direction.IN, data_type="DataFrame"),
            Port(id="p-c-out", name="out0", direction=Direction.OUT, data_type="DataFrame"),
        ],
    )
    d = Node(
        id="n-d",
        type="test.sink",
        label="D",
        ports=[
            Port(
                id="p-d-in",
                name="in0",
                direction=Direction.IN,
                data_type="DataFrame",
                cardinality=Cardinality.MANY,
            ),
            Port(id="p-d-out", name="out0", direction=Direction.OUT, data_type="DataFrame"),
        ],
    )
    edges = [
        Edge(
            id="e-ab",
            source=PortRef(node_id="n-a", port_id="p-a-out"),
            target=PortRef(node_id="n-b", port_id="p-b-in"),
        ),
        Edge(
            id="e-ac",
            source=PortRef(node_id="n-a", port_id="p-a-out"),
            target=PortRef(node_id="n-c", port_id="p-c-in"),
        ),
        Edge(
            id="e-bd",
            source=PortRef(node_id="n-b", port_id="p-b-out"),
            target=PortRef(node_id="n-d", port_id="p-d-in"),
        ),
        Edge(
            id="e-cd",
            source=PortRef(node_id="n-c", port_id="p-c-out"),
            target=PortRef(node_id="n-d", port_id="p-d-in"),
        ),
    ]
    g = _graph([a, b, c, d], edges)

    result = infer_graph_types(g)

    assert result.type_of("n-a", "p-a-out") == "DataFrame"
    assert result.type_of("n-b", "p-b-out") == "DataFrame"
    assert result.type_of("n-c", "p-c-out") == "DataFrame"
    assert result.type_of("n-d", "p-d-out") == "DataFrame"
    # Every IN port in the diamond is fed, so nothing is unbound.
    assert result.unbound == []


def test_dangling_in_port_recorded_as_unbound() -> None:
    sink = Node(
        id="n-sink",
        type="test.sink",
        label="Sink",
        ports=[
            Port(id="p-sink-in", name="in0", direction=Direction.IN, data_type="DataFrame"),
            Port(id="p-sink-out", name="out0", direction=Direction.OUT, data_type="DataFrame"),
        ],
    )
    g = _graph([sink], [])

    result = infer_graph_types(g)

    assert len(result.unbound) == 1
    entry = result.unbound[0]
    assert entry.node_id == "n-sink"
    assert entry.port_id == "p-sink-in"
    assert entry.port_name == "in0"
    # The OUT port still resolves from its declared type.
    assert result.type_of("n-sink", "p-sink-out") == "DataFrame"


def test_reduce_inbound_types_uniform_and_conflict() -> None:
    assert _reduce_inbound_types(["DataFrame"]) == "DataFrame"
    assert _reduce_inbound_types(["DataFrame", "DataFrame"]) == "DataFrame"
    assert _reduce_inbound_types(["DataFrame", "HTML"]) == "any"


class _EchoType(NodeDefinition):
    """Test fixture: a node whose OUT type echoes its IN type (input-dependent)."""

    type = "test.echo"
    family = "test"
    label = "Echo Type"

    ports = [
        PortSpec(name="in0", direction=Direction.IN, data_type="any"),
        PortSpec(name="out0", direction=Direction.OUT, data_type="any"),
    ]

    def codegen(self, node: Node, ctx: Any) -> Any:  # pragma: no cover - unused by inference
        raise NotImplementedError

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:  # pragma: no cover
        raise NotImplementedError

    def infer_types(self, node: Node, input_types: dict[str, str]) -> dict[str, str]:
        return {"out0": input_types.get("in0", "any")}


def _echo_registry() -> NodeRegistry:
    reg = NodeRegistry()
    reg.register(_EchoType)
    return reg


def test_input_dependent_out_type_propagates() -> None:
    src = _src("n-src", "p-src-out", "DataFrame")
    echo = Node(
        id="n-echo",
        type="test.echo",
        label="Echo",
        ports=[
            Port(id="p-echo-in", name="in0", direction=Direction.IN, data_type="any"),
            Port(id="p-echo-out", name="out0", direction=Direction.OUT, data_type="any"),
        ],
    )
    edges = [
        Edge(
            id="e-ae",
            source=PortRef(node_id="n-src", port_id="p-src-out"),
            target=PortRef(node_id="n-echo", port_id="p-echo-in"),
        ),
    ]
    g = _graph([src, echo], edges)

    result = infer_graph_types(g, node_registry=_echo_registry())

    assert result.type_of("n-echo", "p-echo-out") == "DataFrame"


def test_conflicting_inbound_types_reduce_to_any() -> None:
    a = _src("n-a", "p-a-out", "DataFrame")
    b = _src("n-b", "p-b-out", "HTML")
    echo = Node(
        id="n-echo",
        type="test.echo",
        label="Echo",
        ports=[
            Port(
                id="p-echo-in",
                name="in0",
                direction=Direction.IN,
                data_type="any",
                cardinality=Cardinality.MANY,
            ),
            Port(id="p-echo-out", name="out0", direction=Direction.OUT, data_type="any"),
        ],
    )
    edges = [
        Edge(
            id="e-ae",
            source=PortRef(node_id="n-a", port_id="p-a-out"),
            target=PortRef(node_id="n-echo", port_id="p-echo-in"),
        ),
        Edge(
            id="e-be",
            source=PortRef(node_id="n-b", port_id="p-b-out"),
            target=PortRef(node_id="n-echo", port_id="p-echo-in"),
        ),
    ]
    g = _graph([a, b, echo], edges)

    result = infer_graph_types(g, node_registry=_echo_registry())

    assert result.type_of("n-echo", "p-echo-out") == "any"
