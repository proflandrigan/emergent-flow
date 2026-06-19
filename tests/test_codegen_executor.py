"""Tests for colonymind.codegen.executor."""

from __future__ import annotations

import subprocess
import sys
from typing import Any

import pytest

import colonymind as cm
from colonymind.api import is_inspectable
from colonymind.codegen.errors import CodegenError, UnboundInputError
from colonymind.codegen.executor import execute
from colonymind.ir import Direction, Edge, Graph, Node, Paradigm, Port, PortRef
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
        source=PortRef(
            node_id=source_node.id, port_id=_out_port(source_node, source_port_name).id
        ),
        target=PortRef(
            node_id=target_node.id, port_id=_in_port(target_node, target_port_name).id
        ),
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
    """A Double node with no incoming edge raises UnboundInputError."""
    dbl = _double_node("dbl")
    graph = _graph([dbl])

    with pytest.raises(UnboundInputError) as exc_info:
        execute(graph)

    assert "Double" in str(exc_info.value)
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
