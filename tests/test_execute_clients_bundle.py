from __future__ import annotations

import pytest

from emergentflow.clients import ClientKind, Clients
from emergentflow.codegen.executor import execute
from emergentflow.ir import Direction, Graph, Node, Paradigm, Port, Position
from emergentflow.nodes import register
from emergentflow.nodes.contract import CodeFragment, NodeDefinition
from emergentflow.nodes.spec import PortSpec


class _EchoWarehouse:
    """A stand-in warehouse client whose identity we can assert was threaded."""

    marker = "WAREHOUSE_CLIENT_REACHED"


@register
class _WarehouseEchoNode(NodeDefinition):
    type = "_test.warehouse_echo"
    family = "_test"
    label = "Warehouse Echo (test-only)"
    requires = frozenset({ClientKind.WAREHOUSE})
    ports = [PortSpec(name="out", direction=Direction.OUT, data_type="str")]

    def codegen(self, node, ctx):  # pragma: no cover - not exercised here
        return CodeFragment(imports=(), body=f"{ctx.out_var('out')} = 'x'")

    def execute(self, node, inputs, *, client=None):
        # Return an inspectable marker proving which client was injected.
        return {"out": getattr(client, "marker", "NO_CLIENT")}


def _one_node_graph() -> Graph:
    node = Node(
        id="n1",
        type="_test.warehouse_echo",
        label="echo",
        paradigm=Paradigm.FUNCTIONAL,
        params=[],
        ports=[Port(id="p1", name="out", direction=Direction.OUT, data_type="str")],
        position=Position(x=0.0, y=0.0),
    )
    return Graph(name="g", nodes={node.id: node})


def test_warehouse_node_receives_warehouse_seam():
    results = execute(_one_node_graph(), clients=Clients(warehouse=_EchoWarehouse()))
    assert results["n1"]["out"] == "WAREHOUSE_CLIENT_REACHED"


def test_warehouse_node_absent_client_is_none():
    results = execute(_one_node_graph(), clients=Clients())
    assert results["n1"]["out"] == "NO_CLIENT"


def test_both_client_and_clients_raises():
    with pytest.raises(ValueError):
        execute(_one_node_graph(), client="x", clients=Clients())


def test_legacy_client_still_maps_to_llm():
    assert Clients.from_legacy_client("L").llm == "L"
    results = execute(_one_node_graph(), client="L")
    # An LLM client is NOT handed to a warehouse node — capability isolation.
    assert results["n1"]["out"] == "NO_CLIENT"
