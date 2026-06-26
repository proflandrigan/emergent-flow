"""
emergentflow.codegen.context
~~~~~~~~~~~~~~~~~~~~~~~~~~~
The per-node binding context for the code-generation engine (Epic 2, Story 4).

`naming.py` (Story 3) assigns one Python variable name to every OUT port in a
graph; `wiring.py` (Story 2) resolves every IN port's upstream OUT port(s). This
module composes the two into the small, node-local lookup a node's `codegen`
actually wants: "what variable feeds my IN port named X" and "what variable did
I get allocated for my OUT port named Y" — both keyed by port *name*, since a
node's `codegen` knows its own ports by name, not by id (ADR 0009).

Port names are unique only within a direction — a node may have an IN port and
an OUT port both named ``"frame"`` (the impute node does). This is why
`CodegenContext` keeps two separate dicts instead of one.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from emergentflow.codegen.naming import NameMap
from emergentflow.codegen.wiring import WiringMap
from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node


@dataclass(frozen=True)
class CodegenContext:
    """The per-node binding context the whole-graph compiler passes into codegen.

    Supplies, for the node currently being compiled, the input variable name
    bound to each IN port (resolved from the upstream OUT port that feeds it) and
    the output variable name allocated to each OUT port. A node asks the context
    for names instead of inventing them (ADR 0009).
    """

    in_vars: dict[str, str] = field(default_factory=dict)
    out_vars: dict[str, str] = field(default_factory=dict)

    def in_var(self, port_name: str) -> str:
        """Return the variable name feeding the named IN port.

        Raises KeyError if the node has no IN port of that name in this context.
        """
        if port_name not in self.in_vars:
            raise KeyError(f"No IN port {port_name!r} in this codegen context.")
        return self.in_vars[port_name]

    def out_var(self, port_name: str) -> str:
        """Return the variable name allocated to the named OUT port.

        Raises KeyError if the node has no OUT port of that name in this context.
        """
        if port_name not in self.out_vars:
            raise KeyError(f"No OUT port {port_name!r} in this codegen context.")
        return self.out_vars[port_name]

    @classmethod
    def preview(cls, node: Node) -> CodegenContext:
        """Build a trivial preview context: every port's variable IS its port name.

        Used for single-node preview / the canvas "show code" panel (Epic 3), so a
        node previewed alone renders exactly as it did before Story 4
        (e.g. data.load_csv -> ``frame = ef.data.load_csv(...)``). IN and OUT names
        are kept in separate dicts, so a node with IN and OUT both named "frame"
        (impute) maps each to "frame" without conflict.
        """
        in_vars = {p.name: p.name for p in node.ports if p.direction == Direction.IN}
        out_vars = {p.name: p.name for p in node.ports if p.direction == Direction.OUT}
        return cls(in_vars=in_vars, out_vars=out_vars)


def build_codegen_context(node: Node, name_map: NameMap, wiring_map: WiringMap) -> CodegenContext:
    """Compose the Stories 2-3 maps into one node's CodegenContext.

    OUT ports: each OUT port's variable is ``name_map.var_for(node.id, port.id)``.
    IN ports: resolve the upstream source(s) via ``wiring_map.upstream`` and look
    up the source OUT port's variable in ``name_map``:

      * exactly one source  -> that source's variable name;
      * no source (dangling) -> fall back to the IN port's own name (mirrors the
        preview fallback; whole-graph dangling policy is Story 5);
      * more than one source (fan-in, Cardinality.MANY) -> raise ValueError
        naming the port. None of the reference nodes use MANY inputs;
        supporting multi-source fan-in is deferred.
    """
    in_vars: dict[str, str] = {}
    out_vars: dict[str, str] = {}

    for port in node.ports:
        if port.direction == Direction.OUT:
            out_vars[port.name] = name_map.var_for(node.id, port.id)
        elif port.direction == Direction.IN:
            sources = wiring_map.upstream(node.id, port.id)
            if len(sources) == 0:
                in_vars[port.name] = port.name
            elif len(sources) == 1:
                source = sources[0]
                in_vars[port.name] = name_map.var_for(source.node_id, source.port_id)
            else:
                raise ValueError(
                    f"IN port {port.name!r} on node {node.id!r} has {len(sources)} "
                    "sources; multi-source fan-in is not yet supported by codegen "
                    "context."
                )

    return CodegenContext(in_vars=in_vars, out_vars=out_vars)
