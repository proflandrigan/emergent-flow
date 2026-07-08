"""Compiler-side coverage for the Clients bundle (ADR 0018, Story 3).

Mirrors `tests/test_execute_clients_bundle.py`'s registration pattern but
exercises `compile_to_code` instead of `execute`: a warehouse-only, LLM-only,
and combined graph must each emit the right `main()` signature and
client-threading boilerplate, while the LLM-only and no-client shapes stay
byte-identical to the pre-ADR-0018 output (the hard back-compat gate this
task exists to protect).
"""

from __future__ import annotations

import ast

from emergentflow.clients import ClientKind
from emergentflow.codegen.compiler import compile_to_code
from emergentflow.ir import Direction, Graph, Node, Paradigm, Port, Position
from emergentflow.nodes import register
from emergentflow.nodes.contract import CodeFragment, NodeDefinition
from emergentflow.nodes.spec import PortSpec


@register
class _LLMRefNode(NodeDefinition):
    type = "_test.llm_ref"
    family = "_test"
    label = "LLM Ref (test-only)"
    requires = frozenset({ClientKind.LLM})
    ports = [PortSpec(name="out", direction=Direction.OUT, data_type="str")]

    def codegen(self, node, ctx):
        return CodeFragment(imports=(), body=f"{ctx.out_var('out')} = client")

    def execute(self, node, inputs, *, client=None):
        return {"out": "x"}


@register
class _WarehouseRefNode(NodeDefinition):
    type = "_test.warehouse_ref"
    family = "_test"
    label = "Warehouse Ref (test-only)"
    requires = frozenset({ClientKind.WAREHOUSE})
    ports = [PortSpec(name="out", direction=Direction.OUT, data_type="str")]

    def codegen(self, node, ctx):
        return CodeFragment(imports=(), body=f"{ctx.out_var('out')} = warehouse")

    def execute(self, node, inputs, *, client=None):
        return {"out": "x"}


def _llm_graph() -> Graph:
    node = Node(
        id="n1",
        type="_test.llm_ref",
        label="llm",
        paradigm=Paradigm.FUNCTIONAL,
        params=[],
        ports=[Port(id="p1", name="out", direction=Direction.OUT, data_type="str")],
        position=Position(x=0.0, y=0.0),
    )
    return Graph(name="g", nodes={node.id: node})


def _warehouse_graph() -> Graph:
    node = Node(
        id="n1",
        type="_test.warehouse_ref",
        label="warehouse",
        paradigm=Paradigm.FUNCTIONAL,
        params=[],
        ports=[Port(id="p1", name="out", direction=Direction.OUT, data_type="str")],
        position=Position(x=0.0, y=0.0),
    )
    return Graph(name="g", nodes={node.id: node})


def _both_graph() -> Graph:
    llm_node = Node(
        id="n1",
        type="_test.llm_ref",
        label="llm",
        paradigm=Paradigm.FUNCTIONAL,
        params=[],
        ports=[Port(id="p1", name="out", direction=Direction.OUT, data_type="str")],
        position=Position(x=0.0, y=0.0),
    )
    warehouse_node = Node(
        id="n2",
        type="_test.warehouse_ref",
        label="warehouse",
        paradigm=Paradigm.FUNCTIONAL,
        params=[],
        ports=[Port(id="p2", name="out", direction=Direction.OUT, data_type="str")],
        position=Position(x=1.0, y=0.0),
    )
    return Graph(name="g", nodes={llm_node.id: llm_node, warehouse_node.id: warehouse_node})


def test_no_client_graph_emits_plain_main():
    graph = Graph(
        name="g",
        nodes={
            "n1": Node(
                id="n1",
                type="data.load_sample",
                label="sample",
                paradigm=Paradigm.FUNCTIONAL,
                params=[],
                ports=[Port(id="p1", name="frame", direction=Direction.OUT, data_type="DataFrame")],
                position=Position(x=0.0, y=0.0),
            )
        },
    )
    code = compile_to_code(graph)
    assert "def main() -> dict[str, object]:" in code
    assert "clients" not in code


def test_llm_only_graph_unchanged():
    code = compile_to_code(_llm_graph())
    assert "def main(*, client: object | None = None) -> dict[str, object]:" in code
    assert "main(client=GatewayClient())" in code
    assert "clients" not in code


def test_warehouse_graph_threads_clients():
    code = compile_to_code(_warehouse_graph())
    assert "def main(*, clients: object | None = None) -> dict[str, object]:" in code
    assert "warehouse = clients.warehouse if clients is not None else None" in code
    assert "main(clients=Clients(warehouse=None))" in code
    assert "client = clients.llm" not in code


def test_both_graph_threads_both():
    code = compile_to_code(_both_graph())
    assert "def main(*, clients: object | None = None) -> dict[str, object]:" in code
    assert "warehouse = clients.warehouse if clients is not None else None" in code
    assert "client = clients.llm if clients is not None else None" in code
    assert "main(clients=Clients(llm=GatewayClient(), warehouse=None))" in code


def test_all_emitted_modules_parse():
    for graph in (_llm_graph(), _warehouse_graph(), _both_graph()):
        src = compile_to_code(graph)
        tree = ast.parse(src)
        compile(src, "<gen>", "exec")
        assert isinstance(tree, ast.Module)
