"""
emergentflow.codegen.inspect
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Pure, step-by-step variable-binding trace over a FUNCTIONAL graph's
execution (issue #95: the variable inspector). Composes the SAME
naming/wiring/context builders `compile_to_code` uses
(`naming.build_name_map`, `wiring.build_wiring_map`,
`context.build_codegen_context`), so every traced variable name is
guaranteed identical to what the compiler would emit for the same graph --
the inspector is "grounded in the generated code" by construction, not by a
parallel naming scheme.

Declarative (`nn.Module`) graphs are out of scope here (the same scope
note as the issue itself) -- `execute()` already raises for those before
this module's logic runs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from emergentflow.api import public_op
from emergentflow.clients import Clients
from emergentflow.codegen.context import build_codegen_context
from emergentflow.codegen.executor import execute
from emergentflow.codegen.naming import build_name_map
from emergentflow.codegen.traversal import topological_sort
from emergentflow.codegen.wiring import WiringMap, build_wiring_map
from emergentflow.ir.common import Cardinality, Direction
from emergentflow.ir.graph import Graph
from emergentflow.ir.node import Node
from emergentflow.server.payload import to_payload


@dataclass(frozen=True)
class VarBinding:
    """One port's compiler-allocated variable name, bound to a JSON-safe value snapshot."""

    var_name: str
    port_name: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class StepTrace:
    """One node's execution step: its bound inputs and produced outputs."""

    step: int
    node_id: str
    node_label: str
    status: str  # "ok" | "error" | "skipped"
    inputs: list[VarBinding] = field(default_factory=list)
    outputs: list[VarBinding] = field(default_factory=list)


def _resolve_input_value(
    node: Node,
    port: Any,
    wiring_map: WiringMap,
    graph: Graph,
    results: dict[str, dict[str, Any]],
) -> Any:
    """Look up the already-computed value feeding *port*, mirroring executor.py's Step 4.

    Cardinality.MANY -> a list of upstream values (fan-in); zero sources (a
    dangling optional port) -> None; exactly one source -> that value.
    """
    sources = wiring_map.upstream(node.id, port.id)
    if port.cardinality == Cardinality.MANY:
        values: list[Any] = []
        for src in sources:
            src_node = graph.nodes[src.node_id]
            src_port_name = next(p.name for p in src_node.ports if p.id == src.port_id)
            values.append(results[src.node_id][src_port_name])
        return values
    if not sources:
        return None
    src = sources[0]
    src_node = graph.nodes[src.node_id]
    src_port_name = next(p.name for p in src_node.ports if p.id == src.port_id)
    return results[src.node_id][src_port_name]


@public_op(name="ef.codegen.build_step_traces")
def build_step_traces(
    graph: Graph,
    *,
    clients: Clients | None = None,
    client: Any | None = None,
) -> list[StepTrace]:
    """Run *graph* and return one `StepTrace` per node, in topological order.

    Every traced variable name comes from the SAME `NameMap`/`WiringMap`/
    `CodegenContext` the compiler uses, so it is byte-identical to what
    `compile_to_code(graph)` would emit for the same port. Values are
    snapshotted through `to_payload` so the result is JSON-safe.

    Runs the graph exactly once via `execute()` (which already threads
    `clients`/`client` and validates the graph identically to
    `compile_to_code`) and does not re-invoke any node's `execute` a second
    time -- this function only reads already-computed results to build the
    trace metadata.

    Every trace's `status` is `"ok"`: `execute()` is all-or-nothing (it
    raises on the first node error rather than returning partial results),
    so `"error"`/`"skipped"` per-node statuses are a property of the
    SSE-streaming execution path (`emergentflow/server/service.py`'s
    `_execute_functional_stream`), not of this synchronous pure helper.

    Parameters
    ----------
    graph, clients, client:
        Passed straight through to `execute()` -- see its docstring.

    Returns
    -------
    list[StepTrace]
        One entry per node, in the same topological order `execute()` runs
        them.
    """
    results = execute(graph, clients=clients, client=client)
    name_map = build_name_map(graph)
    wiring_map = build_wiring_map(graph)
    topo_order = topological_sort(graph)

    traces: list[StepTrace] = []
    for step, node_id in enumerate(topo_order):
        node = graph.nodes[node_id]
        ctx = build_codegen_context(node, name_map, wiring_map)

        inputs: list[VarBinding] = []
        outputs: list[VarBinding] = []
        for port in node.ports:
            if port.direction == Direction.IN:
                var_name = ctx.in_var(port.name)
                value = _resolve_input_value(node, port, wiring_map, graph, results)
                inputs.append(
                    VarBinding(var_name=var_name, port_name=port.name, payload=to_payload(value))
                )
            elif port.direction == Direction.OUT:
                var_name = ctx.out_var(port.name)
                value = results[node.id][port.name]
                outputs.append(
                    VarBinding(var_name=var_name, port_name=port.name, payload=to_payload(value))
                )

        traces.append(
            StepTrace(
                step=step,
                node_id=node.id,
                node_label=node.label or node.type,
                status="ok",
                inputs=inputs,
                outputs=outputs,
            )
        )

    return traces
