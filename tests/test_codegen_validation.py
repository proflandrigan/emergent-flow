"""
tests/test_codegen_validation.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Tests for emergentflow.codegen.validation — the graph validation pass &
diagnostics (Epic 3, Story 5). Covers a compatible chain (no diagnostics), an
incompatible edge (error), an unregistered token (warning), the "any" wildcard,
a dangling required IN port (error), a cardinality violation (error, no crash),
the apply_type_compatibility side-output, the inspectable/JSON-native
contract, and the `enforce_validation_gate` shared gate (Epic 3, Story 6).
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from emergentflow.api import is_inspectable
from emergentflow.codegen.errors import GraphValidationError
from emergentflow.codegen.validation import (
    Diagnostics,
    Severity,
    apply_type_compatibility,
    enforce_validation_gate,
    validate,
)
from emergentflow.ir import Cardinality, Direction, Edge, Graph, Node, Port, PortRef
from emergentflow.nodes.contract import NodeDefinition
from emergentflow.nodes.registry import NodeRegistry
from emergentflow.nodes.spec import PortSpec


def _graph(nodes: list[Node], edges: list[Edge]) -> Graph:
    return Graph(nodes={n.id: n for n in nodes}, edges={e.id: e for e in edges})


def _out(node_id: str, port_id: str, data_type: str) -> Node:
    return Node(
        id=node_id,
        type="test.source",
        ports=[Port(id=port_id, name="out0", direction=Direction.OUT, data_type=data_type)],
    )


def _in(
    node_id: str,
    port_id: str,
    data_type: str,
    cardinality: Cardinality = Cardinality.ONE,
) -> Node:
    return Node(
        id=node_id,
        type="test.sink",
        ports=[
            Port(
                id=port_id,
                name="in0",
                direction=Direction.IN,
                data_type=data_type,
                cardinality=cardinality,
            )
        ],
    )


def _edge(edge_id: str, src: Node, tgt: Node) -> Edge:
    return Edge(
        id=edge_id,
        source=PortRef(node_id=src.id, port_id=src.ports[0].id),
        target=PortRef(node_id=tgt.id, port_id=tgt.ports[0].id),
    )


def test_compatible_chain_has_no_diagnostics() -> None:
    src = _out("n-src", "p-out", "DataFrame")
    sink = _in("n-sink", "p-in", "DataFrame")
    g = _graph([src, sink], [_edge("e1", src, sink)])

    diags = validate(g)

    assert diags.ok
    assert diags.diagnostics == []
    assert diags.edge_compatibility == {"e1": True}


def test_incompatible_edge_is_error() -> None:
    src = _out("n-src", "p-out", "HTML")
    sink = _in("n-sink", "p-in", "DataFrame")
    g = _graph([src, sink], [_edge("e1", src, sink)])

    diags = validate(g)

    assert not diags.ok
    assert len(diags.errors) == 1
    d = diags.errors[0]
    assert d.severity == Severity.ERROR
    assert d.code == "type_incompatible"
    assert d.edge_id == "e1"
    assert d.expected_type == "DataFrame"
    assert d.actual_type == "HTML"
    assert diags.edge_compatibility == {"e1": False}


def test_unregistered_token_is_warning() -> None:
    src = _out("n-src", "p-out", "Mystery")
    sink = _in("n-sink", "p-in", "DataFrame")
    g = _graph([src, sink], [_edge("e1", src, sink)])

    diags = validate(g)

    assert diags.ok  # warnings do not flip ok
    assert len(diags.warnings) == 1
    assert diags.warnings[0].code == "type_unknown"
    assert diags.edge_compatibility == {"e1": None}


def test_any_wildcard_is_compatible() -> None:
    src = _out("n-src", "p-out", "HTML")
    sink = _in("n-sink", "p-in", "any")
    g = _graph([src, sink], [_edge("e1", src, sink)])

    diags = validate(g)

    assert diags.ok
    assert diags.edge_compatibility == {"e1": True}


class _RequiredSink(NodeDefinition):
    """Fixture: a node type with a required IN port."""

    type = "test.required_sink"
    family = "test"
    label = "Required Sink"

    ports = [
        PortSpec(name="in0", direction=Direction.IN, data_type="DataFrame", required=True),
        PortSpec(name="out0", direction=Direction.OUT, data_type="DataFrame"),
    ]

    def codegen(self, node: Node, ctx: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:  # pragma: no cover
        raise NotImplementedError


def _required_registry() -> NodeRegistry:
    reg = NodeRegistry()
    reg.register(_RequiredSink)
    return reg


def test_dangling_required_in_is_error() -> None:
    sink = Node(
        id="n-sink",
        type="test.required_sink",
        ports=[Port(id="p-in", name="in0", direction=Direction.IN, data_type="DataFrame")],
    )
    g = _graph([sink], [])

    diags = validate(g, node_registry=_required_registry())

    assert not diags.ok
    err = next(d for d in diags.errors if d.code == "required_input_unconnected")
    assert err.node_id == "n-sink"
    assert err.port_name == "in0"


def test_cardinality_violation_is_error_and_does_not_crash() -> None:
    src1 = _out("n-a", "p-a", "DataFrame")
    src2 = _out("n-b", "p-b", "DataFrame")
    sink = _in("n-sink", "p-in", "DataFrame", cardinality=Cardinality.ONE)
    g = _graph([src1, src2, sink], [_edge("e1", src1, sink), _edge("e2", src2, sink)])

    diags = validate(g)  # must not raise

    assert not diags.ok
    assert any(d.code == "cardinality_violation" for d in diags.errors)


def test_diagnostics_order_is_deterministic_regardless_of_dict_insertion_order() -> None:
    # Two incompatible edges feeding a MANY sink so cardinality never fires;
    # only the type_incompatible ordering is under test here.
    src_z = _out("n-z", "p-z", "HTML")
    src_a = _out("n-a", "p-a", "HTML")
    sink = _in("n-m", "p-m", "DataFrame", cardinality=Cardinality.MANY)
    edge_z = _edge("e-z", src_z, sink)
    edge_a = _edge("e-a", src_a, sink)

    g1 = _graph([src_z, src_a, sink], [edge_z, edge_a])
    g2 = _graph([src_a, src_z, sink], [edge_a, edge_z])  # same graph, different insertion order

    order1 = [d.edge_id for d in validate(g1).diagnostics]
    order2 = [d.edge_id for d in validate(g2).diagnostics]

    assert order1 == order2 == ["e-a", "e-z"]  # ascending edge id, independent of insertion order


def test_apply_type_compatibility_populates_without_mutating_input() -> None:
    src = _out("n-src", "p-out", "DataFrame")
    sink = _in("n-sink", "p-in", "DataFrame")
    g = _graph([src, sink], [_edge("e1", src, sink)])

    diags = validate(g)
    updated = apply_type_compatibility(g, diags)

    assert updated is not g
    assert updated.edges["e1"].type_compatible is True
    assert g.edges["e1"].type_compatible is None  # input untouched


def test_diagnostics_is_inspectable_and_json_native() -> None:
    src = _out("n-src", "p-out", "HTML")
    sink = _in("n-sink", "p-in", "DataFrame")
    g = _graph([src, sink], [_edge("e1", src, sink)])

    diags = validate(g)

    assert isinstance(diags, Diagnostics)
    assert is_inspectable(diags)
    payload = diags.model_dump(mode="json")
    restored = json.loads(json.dumps(payload))
    assert restored["diagnostics"][0]["code"] == "type_incompatible"
    assert restored["edge_compatibility"]["e1"] is False


def test_gate_passes_on_clean_graph() -> None:
    src = _out("n-src", "p-out", "DataFrame")
    sink = _in("n-sink", "p-in", "DataFrame")
    g = _graph([src, sink], [_edge("e1", src, sink)])

    diags = enforce_validation_gate(g)

    assert isinstance(diags, Diagnostics)
    assert diags.ok


def test_gate_raises_on_type_incompatible() -> None:
    src = _out("n-src", "p-out", "HTML")
    sink = _in("n-sink", "p-in", "DataFrame")
    g = _graph([src, sink], [_edge("e1", src, sink)])

    with pytest.raises(GraphValidationError) as excinfo:
        enforce_validation_gate(g)

    message = str(excinfo.value)
    assert "type_incompatible" in message
    assert "e1" in message


def test_gate_does_not_raise_on_warning_only() -> None:
    src = _out("n-src", "p-out", "Mystery")
    sink = _in("n-sink", "p-in", "DataFrame")
    g = _graph([src, sink], [_edge("e1", src, sink)])

    diags = enforce_validation_gate(g)

    assert isinstance(diags, Diagnostics)
    assert diags.warnings
