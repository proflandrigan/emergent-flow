"""
colonymind.codegen.executor
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The reference IR interpreter for the code-generation engine (Epic 2, Story 6).

`execute` is the structural twin of `compile_to_code` (`colonymind/codegen/compiler.py`):
it topo-walks a functional IR graph, but instead of emitting Python source for
each node, it calls the node's `execute(node, inputs)` directly and threads each
OUT port's value to every downstream IN port that consumes it. It reuses the same
Story 2/3 plumbing the compiler does (`topological_sort`, `build_wiring_map`) and
applies the same guards with the same error messages, so a graph that compiles
also executes, and vice versa.

This is a pure, in-process reference implementation: no sandboxing, no resource
limits, no subprocess isolation. It exists to let the rest of the system (tests,
previews, the ADR-0002 equivalence harness) run a graph without going through
`compile_to_code` + `exec`. The productionized, sandboxed execution runtime is
Epic 6.
"""

from __future__ import annotations

from typing import Any

from colonymind.api import public_op
from colonymind.codegen.errors import CodegenError, UnboundInputError
from colonymind.codegen.traversal import topological_sort
from colonymind.codegen.wiring import build_wiring_map
from colonymind.ir import Direction, Graph, Node, Paradigm
from colonymind.nodes import get as get_node_definition


def _describe(node: Node) -> str:
    """Human-readable identifier for a node in error messages."""
    label = (node.label or "").strip()
    if label:
        return f"{label!r} (id={node.id})"
    return f"{node.type!r} (id={node.id})"


@public_op(name="cm.execute")
def execute(graph: Graph) -> dict[str, dict[str, Any]]:
    """Run *graph* in-process, node by node, in topological order.

    Args:
        graph: The IR graph to execute.

    Returns:
        A mapping from node id to that node's outputs, themselves keyed by
        OUT-port name: ``{node_id: {out_port_name: value}}``.

    Raises:
        CodegenError: If the graph contains declarative paradigm nodes.
        UnboundInputError: If any input port in the graph is not connected to
                           an upstream output port.
        CycleError: If the graph contains a cycle (propagated from
                    `topological_sort`).
    """
    # Step 1: Paradigm guard
    if graph.paradigm is not Paradigm.FUNCTIONAL:
        raise CodegenError(
            f"Graph {graph.name!r} has paradigm {graph.paradigm!r}. Only "
            f"{Paradigm.FUNCTIONAL!r} is supported by this compiler. "
            "Declarative codegen is Epic 2 Story 8."
        )

    for node in graph.nodes.values():
        if node.paradigm is not Paradigm.FUNCTIONAL:
            raise CodegenError(
                f"Node {_describe(node)} has paradigm {node.paradigm!r}. Only "
                f"{Paradigm.FUNCTIONAL!r} is supported by this compiler. "
                "Declarative codegen is Epic 2 Story 8."
            )

    # Step 2: Topological order
    topo_order_ids = topological_sort(graph)

    # Step 3: Dangling-input guard
    wiring_map = build_wiring_map(graph)
    for node_id in topo_order_ids:
        node = graph.nodes[node_id]
        for port in node.ports:
            if port.direction != Direction.IN:
                continue
            if not wiring_map.upstream(node.id, port.id):
                raise UnboundInputError(
                    f"Input port {port.name!r} of node {_describe(node)} is unbound. "
                    "All input ports must be connected."
                )

    # Step 4: Execution walk
    results: dict[str, dict[str, Any]] = {}
    for node_id in topo_order_ids:
        node = graph.nodes[node_id]

        inputs: dict[str, Any] = {}
        for port in node.ports:
            if port.direction != Direction.IN:
                continue
            sources = wiring_map.upstream(node.id, port.id)
            if len(sources) > 1:
                raise ValueError(
                    f"IN port {port.name!r} on node {node.id!r} has {len(sources)} "
                    "sources; multi-source fan-in is not yet supported by codegen "
                    "context."
                )
            # Zero sources cannot occur here: the dangling-input guard above
            # already raised UnboundInputError for any unbound IN port.
            src = sources[0]
            src_node = graph.nodes[src.node_id]
            src_port_name = next(p.name for p in src_node.ports if p.id == src.port_id)
            inputs[port.name] = results[src.node_id][src_port_name]

        definition = get_node_definition(node.type)()
        results[node.id] = definition.execute(node, inputs)

    # Step 5: Return collected results
    return results
