"""
Epic 3 Story 8 fixture corpus for graph-validation tests.

This module defines a set of validation scenarios used by golden snapshot tests
and unit tests. Each case carries the node and type registries it validates
against: cases needing a custom catalog (``subtype_acceptance``,
``dangling_required_in``) build their own, while the rest reuse the package
default singletons. The default-singleton cases are deterministic only because no
other test mutates those singletons; give a case its own fresh registries if that
ever changes.
"""

from __future__ import annotations

from dataclasses import dataclass

from emergentflow.ir import Cardinality, Direction, Edge, Graph, Node, Port, PortRef
from emergentflow.nodes import registry as default_node_registry
from emergentflow.nodes.contract import NodeDefinition
from emergentflow.nodes.registry import NodeRegistry
from emergentflow.nodes.spec import PortSpec
from emergentflow.types.registry import TypeDef, TypeRegistry
from emergentflow.types.registry import registry as default_type_registry


@dataclass(frozen=True)
class ValidationCase:
    """One named graph-validation scenario for the Story 8 corpus."""

    name: str
    graph: Graph
    node_registry: NodeRegistry
    type_registry: TypeRegistry
    expected_severity: str | None  # "error", "warning", or None when clean


class _RequiredSink(NodeDefinition):
    type = "test.required_sink"
    family = "test"
    label = "Required Sink"
    ports = [
        PortSpec(name="in0", direction=Direction.IN, data_type="DataFrame", required=True),
        PortSpec(name="out0", direction=Direction.OUT, data_type="DataFrame"),
    ]

    def codegen(self, node, ctx):  # pragma: no cover
        raise NotImplementedError

    def execute(self, node, inputs):  # pragma: no cover
        raise NotImplementedError


def build_compatible_chain() -> ValidationCase:
    src = Node(
        id="n-src",
        type="test.source",
        ports=[Port(id="p-out", name="out0", direction=Direction.OUT, data_type="DataFrame")],
    )
    sink = Node(
        id="n-sink",
        type="test.sink",
        ports=[
            Port(
                id="p-in",
                name="in0",
                direction=Direction.IN,
                data_type="DataFrame",
                cardinality=Cardinality.ONE,
            )
        ],
    )
    edge = Edge(
        id="e1",
        source=PortRef(node_id="n-src", port_id="p-out"),
        target=PortRef(node_id="n-sink", port_id="p-in"),
    )
    graph = Graph(nodes={n.id: n for n in [src, sink]}, edges={e.id: e for e in [edge]})
    return ValidationCase(
        name="compatible_chain",
        graph=graph,
        node_registry=default_node_registry,
        type_registry=default_type_registry,
        expected_severity=None,
    )


def build_incompatible_edge() -> ValidationCase:
    src = Node(
        id="n-src",
        type="test.source",
        ports=[Port(id="p-out", name="out0", direction=Direction.OUT, data_type="HTML")],
    )
    sink = Node(
        id="n-sink",
        type="test.sink",
        ports=[
            Port(
                id="p-in",
                name="in0",
                direction=Direction.IN,
                data_type="DataFrame",
                cardinality=Cardinality.ONE,
            )
        ],
    )
    edge = Edge(
        id="e1",
        source=PortRef(node_id="n-src", port_id="p-out"),
        target=PortRef(node_id="n-sink", port_id="p-in"),
    )
    graph = Graph(nodes={n.id: n for n in [src, sink]}, edges={e.id: e for e in [edge]})
    return ValidationCase(
        name="incompatible_edge",
        graph=graph,
        node_registry=default_node_registry,
        type_registry=default_type_registry,
        expected_severity="error",
    )


def build_any_wildcard() -> ValidationCase:
    src = Node(
        id="n-src",
        type="test.source",
        ports=[Port(id="p-out", name="out0", direction=Direction.OUT, data_type="HTML")],
    )
    sink = Node(
        id="n-sink",
        type="test.sink",
        ports=[
            Port(
                id="p-in",
                name="in0",
                direction=Direction.IN,
                data_type="any",
                cardinality=Cardinality.ONE,
            )
        ],
    )
    edge = Edge(
        id="e1",
        source=PortRef(node_id="n-src", port_id="p-out"),
        target=PortRef(node_id="n-sink", port_id="p-in"),
    )
    graph = Graph(nodes={n.id: n for n in [src, sink]}, edges={e.id: e for e in [edge]})
    return ValidationCase(
        name="any_wildcard",
        graph=graph,
        node_registry=default_node_registry,
        type_registry=default_type_registry,
        expected_severity=None,
    )


def build_subtype_acceptance() -> ValidationCase:
    tr = TypeRegistry()
    tr.register(TypeDef(token="DataFrame"))
    tr.register(TypeDef(token="TimeSeries", supertypes=("DataFrame",)))
    src = Node(
        id="n-src",
        type="test.source",
        ports=[Port(id="p-out", name="out0", direction=Direction.OUT, data_type="TimeSeries")],
    )
    sink = Node(
        id="n-sink",
        type="test.sink",
        ports=[
            Port(
                id="p-in",
                name="in0",
                direction=Direction.IN,
                data_type="DataFrame",
                cardinality=Cardinality.ONE,
            )
        ],
    )
    edge = Edge(
        id="e1",
        source=PortRef(node_id="n-src", port_id="p-out"),
        target=PortRef(node_id="n-sink", port_id="p-in"),
    )
    graph = Graph(nodes={n.id: n for n in [src, sink]}, edges={e.id: e for e in [edge]})
    return ValidationCase(
        name="subtype_acceptance",
        graph=graph,
        node_registry=default_node_registry,
        type_registry=tr,
        expected_severity=None,
    )


def build_unregistered_token() -> ValidationCase:
    src = Node(
        id="n-src",
        type="test.source",
        ports=[Port(id="p-out", name="out0", direction=Direction.OUT, data_type="Mystery")],
    )
    sink = Node(
        id="n-sink",
        type="test.sink",
        ports=[
            Port(
                id="p-in",
                name="in0",
                direction=Direction.IN,
                data_type="DataFrame",
                cardinality=Cardinality.ONE,
            )
        ],
    )
    edge = Edge(
        id="e1",
        source=PortRef(node_id="n-src", port_id="p-out"),
        target=PortRef(node_id="n-sink", port_id="p-in"),
    )
    graph = Graph(nodes={n.id: n for n in [src, sink]}, edges={e.id: e for e in [edge]})
    return ValidationCase(
        name="unregistered_token",
        graph=graph,
        node_registry=default_node_registry,
        type_registry=default_type_registry,
        expected_severity="warning",
    )


def build_dangling_required_in() -> ValidationCase:
    nr = NodeRegistry()
    nr.register(_RequiredSink)
    sink = Node(
        id="n-sink",
        type="test.required_sink",
        ports=[
            Port(
                id="p-in",
                name="in0",
                direction=Direction.IN,
                data_type="DataFrame",
                cardinality=Cardinality.ONE,
            )
        ],
    )
    graph = Graph(nodes={n.id: n for n in [sink]}, edges={})
    return ValidationCase(
        name="dangling_required_in",
        graph=graph,
        node_registry=nr,
        type_registry=default_type_registry,
        expected_severity="error",
    )


def build_cardinality_violation() -> ValidationCase:
    src_a = Node(
        id="n-a",
        type="test.source",
        ports=[Port(id="p-a", name="out0", direction=Direction.OUT, data_type="DataFrame")],
    )
    src_b = Node(
        id="n-b",
        type="test.source",
        ports=[Port(id="p-b", name="out0", direction=Direction.OUT, data_type="DataFrame")],
    )
    sink = Node(
        id="n-sink",
        type="test.sink",
        ports=[
            Port(
                id="p-in",
                name="in0",
                direction=Direction.IN,
                data_type="DataFrame",
                cardinality=Cardinality.ONE,
            )
        ],
    )
    edge1 = Edge(
        id="e1",
        source=PortRef(node_id="n-a", port_id="p-a"),
        target=PortRef(node_id="n-sink", port_id="p-in"),
    )
    edge2 = Edge(
        id="e2",
        source=PortRef(node_id="n-b", port_id="p-b"),
        target=PortRef(node_id="n-sink", port_id="p-in"),
    )
    graph = Graph(
        nodes={n.id: n for n in [src_a, src_b, sink]},
        edges={e.id: e for e in [edge1, edge2]},
    )
    return ValidationCase(
        name="cardinality_violation",
        graph=graph,
        node_registry=default_node_registry,
        type_registry=default_type_registry,
        expected_severity="error",
    )


CORPUS = [
    build_compatible_chain(),
    build_incompatible_edge(),
    build_any_wildcard(),
    build_subtype_acceptance(),
    build_unregistered_token(),
    build_dangling_required_in(),
    build_cardinality_violation(),
]
