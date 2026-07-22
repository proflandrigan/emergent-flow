"""Tests for emergentflow.codegen.inspect (issue #95: variable inspector)."""

from __future__ import annotations

from typing import Any

import pytest

from emergentflow.api import is_inspectable
from emergentflow.codegen.errors import CodegenError
from emergentflow.codegen.inspect import build_step_traces
from emergentflow.codegen.naming import build_name_map
from emergentflow.ir import Direction, Edge, Graph, Node, Paradigm, Port, PortRef
from emergentflow.nodes.contract import CodeFragment, NodeDefinition
from emergentflow.nodes.registry import register
from emergentflow.nodes.spec import PortSpec
from emergentflow.server.payload import to_payload

# ---------------------------------------------------------------------------
# Test fixture node types (analogous to test_codegen_executor.py's helpers)
# ---------------------------------------------------------------------------


@register
class _InspectSource(NodeDefinition):
    """0 in, 1 out. Always emits the constant 42."""

    type = "test.inspect_source"
    family = "test"
    label = "InspectSrc"
    ports = [PortSpec(name="out", direction=Direction.OUT, data_type="int")]

    def codegen(self, node: Node, ctx: Any) -> CodeFragment:
        return CodeFragment(body=f"{ctx.out_var('out')} = 42")

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        return {"out": 42}


@register
class _InspectDouble(NodeDefinition):
    """1 in, 1 out. out = in_ * 2."""

    type = "test.inspect_double"
    family = "test"
    label = "InspectDouble"
    ports = [
        PortSpec(name="in_", direction=Direction.IN, data_type="int"),
        PortSpec(name="out", direction=Direction.OUT, data_type="int"),
    ]

    def codegen(self, node: Node, ctx: Any) -> CodeFragment:
        return CodeFragment(body=f"{ctx.out_var('out')} = {ctx.in_var('in_')} * 2")

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        return {"out": inputs["in_"] * 2}


@register
class _InspectOptionalAdd(NodeDefinition):
    """1 required in, 1 optional in, 1 out. out = in_ + (bonus or 0)."""

    type = "test.inspect_optional_add"
    family = "test"
    label = "InspectOptionalAdd"
    ports = [
        PortSpec(name="in_", direction=Direction.IN, data_type="int"),
        PortSpec(name="bonus", direction=Direction.IN, data_type="int", required=False),
        PortSpec(name="out", direction=Direction.OUT, data_type="int"),
    ]

    def codegen(self, node: Node, ctx: Any) -> CodeFragment:
        return CodeFragment(
            body=f"{ctx.out_var('out')} = {ctx.in_var('in_')} + ({ctx.in_var('bonus')} or 0)"
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        return {"out": inputs["in_"] + (inputs.get("bonus") or 0)}


# ---------------------------------------------------------------------------
# Graph-building helpers
# ---------------------------------------------------------------------------


def _out_port(node: Node, name: str) -> Port:
    return next(p for p in node.ports if p.direction == Direction.OUT and p.name == name)


def _in_port(node: Node, name: str) -> Port:
    return next(p for p in node.ports if p.direction == Direction.IN and p.name == name)


def _graph(nodes: list[Node], edges: list[Edge] | None = None) -> Graph:
    edges = edges or []
    return Graph(nodes={n.id: n for n in nodes}, edges={e.id: e for e in edges})


def _source_node() -> Node:
    return Node(
        id="src",
        type=_InspectSource.type,
        label=_InspectSource.label,
        ports=[Port(id="src-out", name="out", direction=Direction.OUT, data_type="int")],
    )


def _double_node(node_id: str) -> Node:
    return Node(
        id=node_id,
        type=_InspectDouble.type,
        label=_InspectDouble.label,
        ports=[
            Port(id=f"{node_id}-in", name="in_", direction=Direction.IN, data_type="int"),
            Port(id=f"{node_id}-out", name="out", direction=Direction.OUT, data_type="int"),
        ],
    )


def _optional_add_node(node_id: str) -> Node:
    return Node(
        id=node_id,
        type=_InspectOptionalAdd.type,
        label=_InspectOptionalAdd.label,
        ports=[
            Port(id=f"{node_id}-in", name="in_", direction=Direction.IN, data_type="int"),
            Port(id=f"{node_id}-bonus", name="bonus", direction=Direction.IN, data_type="int"),
            Port(id=f"{node_id}-out", name="out", direction=Direction.OUT, data_type="int"),
        ],
    )


def _edge(
    source_node: Node,
    source_port_name: str,
    target_node: Node,
    target_port_name: str,
) -> Edge:
    return Edge(
        source=PortRef(node_id=source_node.id, port_id=_out_port(source_node, source_port_name).id),
        target=PortRef(node_id=target_node.id, port_id=_in_port(target_node, target_port_name).id),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_two_node_chain_returns_two_traces() -> None:
    """source -> double yields exactly 2 StepTrace entries in topological order."""
    src = _source_node()
    dbl = _double_node("dbl")
    edge = _edge(src, "out", dbl, "in_")
    graph = _graph([src, dbl], [edge])

    traces = build_step_traces(graph)

    assert len(traces) == 2
    assert traces[0].node_id == "src"
    assert traces[1].node_id == "dbl"


def test_source_trace_inputs_empty_output_var_matches_name_map() -> None:
    """Source node's trace has no inputs; its output var_name matches NameMap."""
    src = _source_node()
    graph = _graph([src])
    out_port = _out_port(src, "out")

    traces = build_step_traces(graph)

    assert len(traces) == 1
    src_trace = traces[0]
    assert src_trace.inputs == []
    assert len(src_trace.outputs) == 1

    name_map = build_name_map(graph)
    expected_var = name_map.var_for(src.id, out_port.id)
    assert src_trace.outputs[0].var_name == expected_var


def test_transform_input_var_and_payload_match_upstream() -> None:
    """The double node's input var_name equals the source node's output var_name,
    and its payload matches to_payload of the source node's actual output value."""
    src = _source_node()
    dbl = _double_node("dbl")
    edge = _edge(src, "out", dbl, "in_")
    graph = _graph([src, dbl], [edge])

    traces = build_step_traces(graph)

    # Source's output variable name
    src_out_var = traces[0].outputs[0].var_name
    # Double's first (and only) input variable name
    dbl_in_var = traces[1].inputs[0].var_name

    assert dbl_in_var == src_out_var
    # Source produces value 42
    assert traces[1].inputs[0].payload == to_payload(42)


def test_dangling_optional_in_port_binds_to_none_literal() -> None:
    """An unbound optional IN port gets var_name="None" and payload=to_payload(None)."""
    src = _source_node()
    add = _optional_add_node("add")
    edge = _edge(src, "out", add, "in_")  # bonus is left unconnected
    graph = _graph([src, add], [edge])

    traces = build_step_traces(graph)

    # The optional_add node should have two input VarBindings: in_ and bonus
    add_trace = traces[1]
    assert len(add_trace.inputs) == 2

    bonus_binding = next(v for v in add_trace.inputs if v.port_name == "bonus")
    assert bonus_binding.var_name == "None"
    assert bonus_binding.payload == to_payload(None)


def test_all_traces_have_ok_status() -> None:
    """Every StepTrace in a successfully-executing graph has status 'ok'."""
    src = _source_node()
    dbl = _double_node("dbl")
    edge = _edge(src, "out", dbl, "in_")
    graph = _graph([src, dbl], [edge])

    traces = build_step_traces(graph)

    for trace in traces:
        assert trace.status == "ok"


def test_declarative_graph_raises_codegen_error() -> None:
    """A DECLARATIVE graph propagates the CodegenError execute() raises."""
    graph = Graph(paradigm=Paradigm.DECLARATIVE)

    with pytest.raises(CodegenError):
        build_step_traces(graph)


def test_result_is_inspectable() -> None:
    """The list[StepTrace] return value satisfies the SDK inspectable contract."""
    src = _source_node()
    dbl = _double_node("dbl")
    edge = _edge(src, "out", dbl, "in_")
    graph = _graph([src, dbl], [edge])

    result = build_step_traces(graph)

    assert is_inspectable(result)
