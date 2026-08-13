"""Tests for emergentflow.codegen.executor."""

from __future__ import annotations

import subprocess
import sys
from typing import Any

import pytest

import emergentflow as ef
from emergentflow.api import is_inspectable
from emergentflow.codegen.compiler import compile_to_code
from emergentflow.codegen.composite import COMPOSITE_NODE_TYPE, resolve_composite_boundary
from emergentflow.codegen.errors import CodegenError, GraphValidationError
from emergentflow.codegen.executor import execute
from emergentflow.ir import Direction, Edge, Graph, Node, Paradigm, Port, PortRef
from emergentflow.ir.common import Cardinality
from emergentflow.nodes.contract import CodeFragment, NodeDefinition
from emergentflow.nodes.registry import register
from emergentflow.nodes.spec import PortSpec


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


@register
class _ExecOptionalAdd(NodeDefinition):
    """Test fixture: 1 required in, 1 optional in, 1 out. out = in_ + (bonus or 0)."""

    type = "test.exec_optional_add"
    family = "test"
    label = "OptionalAdd"
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


def _optional_add_node(node_id: str) -> Node:
    return Node(
        id=node_id,
        type=_ExecOptionalAdd.type,
        label=_ExecOptionalAdd.label,
        ports=[
            Port(id=f"{node_id}-in", name="in_", direction=Direction.IN, data_type="int"),
            Port(id=f"{node_id}-bonus", name="bonus", direction=Direction.IN, data_type="int"),
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


def test_unconnected_optional_in_port_is_not_an_error() -> None:
    """An unconnected *optional* (`required=False`) IN port is not rejected.

    `execute` receives `None` for the dangling optional port; `compile_to_code`
    binds it to the `None` literal -- both paths agree (ADR 0002 equivalence).
    """
    src = _source_node()
    add = _optional_add_node("add")
    edge = _edge(src, "out", add, "in_")
    graph = _graph([src, add], [edge])

    results = execute(graph)
    assert results["add"] == {"out": 1}

    code = compile_to_code(graph)
    assert "None or 0" in code

    namespace: dict[str, Any] = {}
    exec(compile(code, "<generated>", "exec"), namespace)
    assert namespace["main"]()["optionaladd_out"] == 1


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
    """ef.execute is lazily wired."""
    script = """
import sys
import emergentflow as ef

# emergentflow.codegen should not be imported yet
assert 'emergentflow.codegen' not in sys.modules

# Accessing ef.execute should trigger the import
_ = ef.execute

# Now it should be imported
assert 'emergentflow.codegen' in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, f"Subprocess failed:\n{result.stderr}\n{result.stdout}"
    assert "execute" in ef.__all__


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


def test_multi_source_fan_in_collects_a_list_in_deterministic_order() -> None:
    """A MANY IN port fed by 2 sources receives a list of both upstream values, in
    the same deterministic (node_id, port_id) order build_wiring_map defines."""
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
    dbl = Node(
        id="dbl",
        type=_ExecDouble.type,
        label=_ExecDouble.label,
        ports=[
            Port(id="dbl-in", name="in_", direction=Direction.IN, data_type="int"),
            Port(id="dbl-out", name="out", direction=Direction.OUT, data_type="int"),
        ],
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
            source=PortRef(node_id="src_b", port_id="src_b-out"),
            target=PortRef(node_id="dbl", port_id="dbl-in"),
        ),
        Edge(
            source=PortRef(node_id="src_a", port_id="src_a-out"),
            target=PortRef(node_id="fan", port_id="fan-in"),
        ),
        Edge(
            source=PortRef(node_id="dbl", port_id="dbl-out"),
            target=PortRef(node_id="fan", port_id="fan-in"),
        ),
    ]
    graph = _graph([src_a, src_b, dbl, fan], edges)

    results = execute(graph)

    # fan-in's two sources are node "dbl" (src_b doubled: 1 * 2 = 2) and node
    # "src_a" (value 1). build_wiring_map orders sources by (node_id, port_id);
    # "dbl" < "src_a" lexicographically, so dbl's value (2) comes first.
    assert results["fan"]["out"] == [2, 1]


# ---------------------------------------------------------------------------
# layout.composite (issue #117 stage 3)
# ---------------------------------------------------------------------------


def _composite_node(node_id: str, subgraph: Graph, *, num_in: int = 1, num_out: int = 1) -> Node:
    ports = [
        Port(id=f"{node_id}-in{i}", name=f"in{i}", direction=Direction.IN, data_type="int")
        for i in range(num_in)
    ] + [
        Port(id=f"{node_id}-out{i}", name=f"out{i}", direction=Direction.OUT, data_type="int")
        for i in range(num_out)
    ]
    return Node(
        id=node_id, type=COMPOSITE_NODE_TYPE, label="Composite", ports=ports, subgraph=subgraph
    )


def test_resolve_composite_boundary_single_unwired_node():
    """A lone, unwired Double node: its `in_` is dangling, its `out` is exposed."""
    dbl = _double_node("dbl")
    subgraph = _graph([dbl])

    boundary = resolve_composite_boundary(subgraph)

    assert boundary.dangling_in == [PortRef(node_id="dbl", port_id="dbl-in")]
    assert boundary.exposed_out == [PortRef(node_id="dbl", port_id="dbl-out")]


def test_resolve_composite_boundary_internal_wiring_excluded():
    """source -> double, internal to the subgraph: double's `in_` is bound, not dangling."""
    src = _source_node()
    dbl = _double_node("dbl")
    edge = _edge(src, "out", dbl, "in_")
    subgraph = _graph([src, dbl], [edge])

    boundary = resolve_composite_boundary(subgraph)

    assert boundary.dangling_in == []
    assert boundary.exposed_out == [PortRef(node_id="dbl", port_id="dbl-out")]


def test_composite_executes_subgraph_and_binds_boundary_ports():
    """A composite wrapping a single unwired Double node doubles its outer input."""
    inner = _double_node("inner_dbl")
    subgraph = _graph([inner])
    composite = _composite_node("composite1", subgraph)

    outer_src = _source_node()
    edge = Edge(
        source=PortRef(node_id=outer_src.id, port_id=_out_port(outer_src, "out").id),
        target=PortRef(node_id=composite.id, port_id=_in_port(composite, "in0").id),
    )
    outer_graph = _graph([outer_src, composite], [edge])

    results = execute(outer_graph)

    assert results["src"] == {"out": 1}
    assert results["composite1"] == {"out0": 2}
    # The subgraph's own internal node id never leaks into the outer results -- a
    # composite is a black box from the outside.
    assert "inner_dbl" not in results


def test_composite_with_no_subgraph_raises():
    composite = Node(
        id="composite1",
        type=COMPOSITE_NODE_TYPE,
        label="Composite",
        ports=[Port(id="composite1-out0", name="out0", direction=Direction.OUT, data_type="int")],
    )
    graph = _graph([composite])

    with pytest.raises(CodegenError, match="no subgraph"):
        execute(graph)


def test_composite_port_count_mismatch_raises():
    """Declaring 2 IN ports for a subgraph with only 1 dangling IN port is rejected."""
    inner = _double_node("inner_dbl")
    subgraph = _graph([inner])
    composite = _composite_node("composite1", subgraph, num_in=2)

    outer_src_a = _source_node()
    outer_src_a.id = "src_a"
    edge = Edge(
        source=PortRef(node_id="src_a", port_id="src-out"),
        target=PortRef(node_id=composite.id, port_id=_in_port(composite, "in0").id),
    )
    outer_graph = Graph(
        nodes={"src_a": outer_src_a, composite.id: composite},
        edges={edge.id: edge},
    )

    with pytest.raises(CodegenError, match="IN port"):
        execute(outer_graph)


def test_composite_compiles_and_runs():
    """The symmetric compile_to_code path: a composite becomes a nested function.

    Also cross-checks against execute() directly, reinforcing the ADR-0002
    equivalence the formal corpus in tests/test_codegen_equivalence.py covers.
    """
    inner = _double_node("inner_dbl")
    subgraph = _graph([inner])
    composite = _composite_node("composite1", subgraph)

    outer_src = _source_node()
    edge = Edge(
        source=PortRef(node_id=outer_src.id, port_id=_out_port(outer_src, "out").id),
        target=PortRef(node_id=composite.id, port_id=_in_port(composite, "in0").id),
    )
    outer_graph = _graph([outer_src, composite], [edge])

    code = compile_to_code(outer_graph)
    assert "def _composite_" in code

    namespace: dict[str, Any] = {}
    exec(compile(code, "<generated>", "exec"), namespace)
    results = namespace["main"]()

    assert len(results) == 1
    compiled_value = next(iter(results.values()))
    assert compiled_value == 2
    assert execute(outer_graph)["composite1"]["out0"] == compiled_value


def test_composite_many_dangling_boundary_in_port_seeds_value() -> None:
    """A composite whose subgraph leaves a MANY IN port dangling (a boundary port) must
    thread the outer value through -- not hand the node an empty list.

    Regression for an ADR-0002 divergence: `compile_to_code` rebound the MANY boundary
    port to a positional arg and passed the outer value through, but the executor's MANY
    branch only looked at intra-subgraph sources (none, since the port is dangling) and
    so delivered `[]`, silently dropping the seeded value.
    """
    inner = Node(
        id="inner_fan",
        type=_ExecFanIn.type,
        label=_ExecFanIn.label,
        ports=[
            Port(
                id="inner_fan-in",
                name="in_",
                direction=Direction.IN,
                data_type="int",
                cardinality=Cardinality.MANY,
            ),
            Port(id="inner_fan-out", name="out", direction=Direction.OUT, data_type="int"),
        ],
    )
    subgraph = _graph([inner])
    # Mirror the MANY cardinality on the composite's exposed IN port so the boundary
    # value flows through as a list on both paths (compile_to_code emits `[src_out]`).
    composite = Node(
        id="composite1",
        type=COMPOSITE_NODE_TYPE,
        label="Composite",
        ports=[
            Port(
                id="composite1-in0",
                name="in0",
                direction=Direction.IN,
                data_type="int",
                cardinality=Cardinality.MANY,
            ),
            Port(id="composite1-out0", name="out0", direction=Direction.OUT, data_type="int"),
        ],
        subgraph=subgraph,
    )

    outer_src = _source_node()
    edge = Edge(
        source=PortRef(node_id=outer_src.id, port_id=_out_port(outer_src, "out").id),
        target=PortRef(node_id=composite.id, port_id=_in_port(composite, "in0").id),
    )
    outer_graph = _graph([outer_src, composite], [edge])

    executed = execute(outer_graph)
    assert executed["composite1"]["out0"] == [1]  # src emits 1 -> MANY in0 -> [1]

    code = compile_to_code(outer_graph)
    namespace: dict[str, Any] = {}
    exec(compile(code, "<generated>", "exec"), namespace)
    compiled_value = next(iter(namespace["main"]().values()))
    assert compiled_value == executed["composite1"]["out0"] == [1]


def test_composite_codegen_no_subgraph_raises():
    composite = Node(
        id="composite1",
        type=COMPOSITE_NODE_TYPE,
        label="Composite",
        ports=[Port(id="composite1-out0", name="out0", direction=Direction.OUT, data_type="int")],
    )
    graph = _graph([composite])

    with pytest.raises(CodegenError, match="no subgraph"):
        compile_to_code(graph)


def test_composite_codegen_port_count_mismatch_raises():
    inner = _double_node("inner_dbl")
    subgraph = _graph([inner])
    composite = _composite_node("composite1", subgraph, num_in=2)

    outer_src_a = _source_node()
    outer_src_a.id = "src_a"
    edge = Edge(
        source=PortRef(node_id="src_a", port_id="src-out"),
        target=PortRef(node_id=composite.id, port_id=_in_port(composite, "in0").id),
    )
    outer_graph = Graph(
        nodes={"src_a": outer_src_a, composite.id: composite},
        edges={edge.id: edge},
    )

    with pytest.raises(CodegenError, match="IN port"):
        compile_to_code(outer_graph)
