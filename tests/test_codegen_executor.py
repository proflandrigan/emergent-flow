"""Tests for colonymind.codegen.executor."""

from __future__ import annotations

import subprocess
import sys
from typing import Any

import pytest

import colonymind as cm
from colonymind.api import is_inspectable
from colonymind.codegen.errors import CodegenError, GraphValidationError
from colonymind.codegen.executor import execute
from colonymind.ir import Direction, Edge, Graph, Node, Paradigm, Port, PortRef
from colonymind.ir.common import Cardinality
from colonymind.nodes.contract import CodeFragment, NodeDefinition
from colonymind.nodes.registry import register
from colonymind.nodes.spec import PortSpec


@register
class _ExecSource(NodeDefinition):
    """Test fixture: 0 in, 1 out. Always emits the constant 1."""

    type = "test.exec_source"
    family = "test"
    label = "Src"
    ports = [PortSpec(name="out", direction=Direction.OUT, data_type="int")]

    def codegen(self, node: Node, ctx: Any) -> CodeFragment:
        return CodeFragment(body=f"{ctx.out_var('out')} = 1")

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        return {"out": 1}


@register
class _ExecDouble(NodeDefinition):
    """Test fixture: 1 in, 1 out. out = in_ * 2."""

    type = "test.exec_double"
    family = "test"
    label = "Double"
    ports = [
        PortSpec(name="in_", direction=Direction.IN, data_type="int"),
        PortSpec(name="out", direction=Direction.OUT, data_type="int"),
    ]

    def codegen(self, node: Node, ctx: Any) -> CodeFragment:
        return CodeFragment(body=f"{ctx.out_var('out')} = {ctx.in_var('in_')} * 2")

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        return {"out": inputs["in_"] * 2}


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
        type=_ExecSource.type,
        label=_ExecSource.label,
        ports=[Port(id="src-out", name="out", direction=Direction.OUT, data_type="int")],
    )


def _double_node(node_id: str) -> Node:
    return Node(
        id=node_id,
        type=_ExecDouble.type,
        label=_ExecDouble.label,
        ports=[
            Port(id=f"{node_id}-in", name="in_", direction=Direction.IN, data_type="int"),
            Port(id=f"{node_id}-out", name="out", direction=Direction.OUT, data_type="int"),
        ],
    )


def _edge(
    source_node: Node, source_port_name: str, target_node: Node, target_port_name: str
) -> Edge:
    return Edge(
        source=PortRef(node_id=source_node.id, port_id=_out_port(source_node, source_port_name).id),
        target=PortRef(node_id=target_node.id, port_id=_in_port(target_node, target_port_name).id),
    )


def test_empty_graph() -> None:
    """An empty graph executes to an empty result dict."""
    assert execute(Graph()) == {}


def test_single_source() -> None:
    """A lone source node executes and returns its output."""
    src = _source_node()
    graph = _graph([src])

    assert execute(graph) == {"src": {"out": 1}}


def test_linear_chain() -> None:
    """source -> double threads the source's output into double's input."""
    src = _source_node()
    dbl = _double_node("dbl")
    edge = _edge(src, "out", dbl, "in_")
    graph = _graph([src, dbl], [edge])

    results = execute(graph)
    assert results["src"] == {"out": 1}
    assert results["dbl"] == {"out": 2}


def test_fan_out() -> None:
    """source -> (double, double): both consumers see the same input value."""
    src = _source_node()
    dbl_a = _double_node("dbl_a")
    dbl_b = _double_node("dbl_b")
    edge_a = _edge(src, "out", dbl_a, "in_")
    edge_b = _edge(src, "out", dbl_b, "in_")
    graph = _graph([src, dbl_a, dbl_b], [edge_a, edge_b])

    results = execute(graph)
    assert results["src"] == {"out": 1}
    assert results["dbl_a"] == {"out": 2}
    assert results["dbl_b"] == {"out": 2}


def test_dangling_required_in_port_is_error() -> None:
    """A Double node with no incoming edge is rejected by the Story 6 gate.

    The shared `enforce_validation_gate` runs first and reports the unconnected
    required IN port as a `required_input_unconnected` error before the
    lower-level `UnboundInputError` guard in `execute` is reached — matching how
    `compile_to_code` rejects the same graph (ADR 0002 equivalence).
    """
    dbl = _double_node("dbl")
    graph = _graph([dbl])

    with pytest.raises(GraphValidationError) as exc_info:
        execute(graph)

    assert "required_input_unconnected" in str(exc_info.value)
    assert "in_" in str(exc_info.value)


def test_non_functional_graph_rejected() -> None:
    """A node with paradigm=DECLARATIVE is rejected with a Story-8 pointer."""
    src = _source_node()
    src_declarative = src.model_copy(update={"paradigm": Paradigm.DECLARATIVE})
    graph = _graph([src_declarative])

    with pytest.raises(CodegenError) as exc_info:
        execute(graph)
    assert "Story 8" in str(exc_info.value)


def test_return_is_inspectable() -> None:
    """execute()'s return value satisfies the SDK inspectable-result contract."""
    src = _source_node()
    dbl = _double_node("dbl")
    edge = _edge(src, "out", dbl, "in_")
    graph = _graph([src, dbl], [edge])

    assert is_inspectable(execute(graph))


def test_cm_execute_is_lazily_wired() -> None:
    """cm.execute is lazily wired."""
    script = """
import sys
import colonymind as cm

# colonymind.codegen should not be imported yet
assert 'colonymind.codegen' not in sys.modules

# Accessing cm.execute should trigger the import
_ = cm.execute

# Now it should be imported
assert 'colonymind.codegen' in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, f"Subprocess failed:\n{result.stderr}\n{result.stdout}"
    assert "execute" in cm.__all__


@register
class _ExecSplit(NodeDefinition):
    """Test fixture: 1 in, 2 distinctly-named outs. lo = in_, hi = in_ * 10."""

    type = "test.exec_split"
    family = "test"
    label = "Split"
    ports = [
        PortSpec(name="in_", direction=Direction.IN, data_type="int"),
        PortSpec(name="lo", direction=Direction.OUT, data_type="int"),
        PortSpec(name="hi", direction=Direction.OUT, data_type="int"),
    ]

    def codegen(self, node: Node, ctx: Any) -> CodeFragment:
        return CodeFragment(
            body=(
                f"{ctx.out_var('lo')} = {ctx.in_var('in_')}\n"
                f"{ctx.out_var('hi')} = {ctx.in_var('in_')} * 10"
            )
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        return {"lo": inputs["in_"], "hi": inputs["in_"] * 10}


@register
class _ExecFanIn(NodeDefinition):
    """Test fixture: one MANY-cardinality IN port (allows >1 upstream source)."""

    type = "test.exec_fan_in"
    family = "test"
    label = "FanIn"
    ports = [
        PortSpec(
            name="in_",
            direction=Direction.IN,
            data_type="int",
            cardinality=Cardinality.MANY,
        ),
        PortSpec(name="out", direction=Direction.OUT, data_type="int"),
    ]

    def codegen(self, node: Node, ctx: Any) -> CodeFragment:
        return CodeFragment(body=f"{ctx.out_var('out')} = {ctx.in_var('in_')}")

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        return {"out": inputs["in_"]}


def test_multi_output_threads_each_out_port_by_name() -> None:
    """A 2-output node's ports are resolved by name (not position) downstream."""
    src = _source_node()
    split = Node(
        id="split",
        type=_ExecSplit.type,
        label=_ExecSplit.label,
        ports=[
            Port(id="split-in", name="in_", direction=Direction.IN, data_type="int"),
            Port(id="split-lo", name="lo", direction=Direction.OUT, data_type="int"),
            Port(id="split-hi", name="hi", direction=Direction.OUT, data_type="int"),
        ],
    )
    # Two doublers consume the two DISTINCT out ports: one off `hi`, one off `lo`.
    dbl_hi = _double_node("dbl_hi")
    dbl_lo = _double_node("dbl_lo")
    edges = [
        _edge(src, "out", split, "in_"),
        Edge(
            source=PortRef(node_id="split", port_id="split-hi"),
            target=PortRef(node_id="dbl_hi", port_id="dbl_hi-in"),
        ),
        Edge(
            source=PortRef(node_id="split", port_id="split-lo"),
            target=PortRef(node_id="dbl_lo", port_id="dbl_lo-in"),
        ),
    ]
    graph = _graph([src, split, dbl_hi, dbl_lo], edges)

    results = execute(graph)
    assert results["split"] == {"lo": 1, "hi": 10}
    # dbl_hi must double `hi` (10 -> 20); dbl_lo must double `lo` (1 -> 2). If the
    # executor resolved OUT ports positionally these would be swapped.
    assert results["dbl_hi"] == {"out": 20}
    assert results["dbl_lo"] == {"out": 2}


def test_multi_source_fan_in_is_error() -> None:
    """A MANY IN port fed by 2 sources raises ValueError (parity with codegen)."""
    src_a = Node(
        id="src_a",
        type=_ExecSource.type,
        label=_ExecSource.label,
        ports=[Port(id="src_a-out", name="out", direction=Direction.OUT, data_type="int")],
    )
    src_b = Node(
        id="src_b",
        type=_ExecSource.type,
        label=_ExecSource.label,
        ports=[Port(id="src_b-out", name="out", direction=Direction.OUT, data_type="int")],
    )
    fan = Node(
        id="fan",
        type=_ExecFanIn.type,
        label=_ExecFanIn.label,
        ports=[
            Port(
                id="fan-in",
                name="in_",
                direction=Direction.IN,
                data_type="int",
                cardinality=Cardinality.MANY,
            ),
            Port(id="fan-out", name="out", direction=Direction.OUT, data_type="int"),
        ],
    )
    edges = [
        Edge(
            source=PortRef(node_id="src_a", port_id="src_a-out"),
            target=PortRef(node_id="fan", port_id="fan-in"),
        ),
        Edge(
            source=PortRef(node_id="src_b", port_id="src_b-out"),
            target=PortRef(node_id="fan", port_id="fan-in"),
        ),
    ]
    graph = _graph([src_a, src_b, fan], edges)

    with pytest.raises(ValueError, match="multi-source fan-in"):
        execute(graph)
