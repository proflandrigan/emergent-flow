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
from typing import TYPE_CHECKING

from emergentflow.codegen.naming import NameMap
from emergentflow.codegen.wiring import WiringMap
from emergentflow.ir.common import Cardinality, Direction
from emergentflow.ir.node import Node

if TYPE_CHECKING:  # pragma: no cover - typing only
    # Import-cycle guard: every node module imports `CodegenContext` from here, and
    # `emergentflow.nodes` imports every node module, so this module must never
    # import the registry at runtime -- `build_codegen_context` takes it as a
    # parameter instead (both call sites already hold one).
    from emergentflow.nodes.registry import NodeRegistry


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
    param_exprs: dict[str, str] = field(default_factory=dict)

    def in_var(self, port_name: str) -> str:
        """Return the variable name feeding the named IN port.

        Raises KeyError if the node has no IN port of that name in this context.
        """
        if port_name not in self.in_vars:
            raise KeyError(f"No IN port {port_name!r} in this codegen context.")
        return self.in_vars[port_name]

    def in_var_or_none(self, port_name: str) -> str:
        """Return the variable feeding an *optional* IN port, or the ``"None"`` literal.

        A node type's `PortSpec` may mark an IN port ``required=False``; a node
        *instance* is then free to omit that port entirely (the canvas does this
        when the user removes an unused optional input). Such a port has no entry
        in `in_vars`, and `in_var` would raise. Codegen for an optional port must
        degrade to ``None`` instead -- mirroring what the same node's `execute`
        already does with ``inputs.get(port_name)`` (ADR 0002 equivalence).

        Use this for every ``required=False`` IN port of ``Cardinality.ONE``;
        keep `in_var` for required ones, where a missing entry is a genuine bug
        worth raising on. The fallback is always the ``"None"`` literal -- this
        accessor cannot see the port's cardinality, so an optional
        ``Cardinality.MANY`` port must NOT use it (it would splice ``None`` where
        the emitted call expects a list). Such a port is covered instead by
        `build_codegen_context`'s registry backfill, which knows the cardinality
        and binds ``"[]"``.
        """
        return self.in_vars.get(port_name, "None")

    def out_var(self, port_name: str) -> str:
        """Return the variable name allocated to the named OUT port.

        Raises KeyError if the node has no OUT port of that name in this context.
        """
        if port_name not in self.out_vars:
            raise KeyError(f"No OUT port {port_name!r} in this codegen context.")
        return self.out_vars[port_name]

    def param_expr(self, param_name: str) -> str:
        """Return the Python expression to embed for the named node param.

        A param bound to a graph-level parameter reference (``ref``) emits the compiled
        ``main()`` keyword-argument variable name; a literal param emits its repr'd value.
        Raises KeyError if the node has no param of that name in this context.
        """
        if param_name not in self.param_exprs:
            raise KeyError(f"No param {param_name!r} in this codegen context.")
        return self.param_exprs[param_name]

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
        param_exprs = {p.name: repr(p.value) for p in node.params}
        return cls(in_vars=in_vars, out_vars=out_vars, param_exprs=param_exprs)


def build_codegen_context(
    node: Node,
    name_map: NameMap,
    wiring_map: WiringMap,
    node_registry: NodeRegistry | None = None,
) -> CodegenContext:
    """Compose the Stories 2-3 maps into one node's CodegenContext.

    OUT ports: each OUT port's variable is ``name_map.var_for(node.id, port.id)``.
    IN ports: resolve the upstream source(s) via ``wiring_map.upstream`` and look
    up the source OUT port's variable in ``name_map``:

      * exactly one source  -> that source's variable name;
      * no source (dangling) -> bind to the ``"None"`` literal. The whole-graph
        dangling-input guard (``compiler.py``) already rejects an unconnected
        *required* IN port before this runs (Story 5/6), so a port reaching
        this branch is genuinely optional (``PortSpec.required=False``) --
        splicing the ``None`` literal into the emitted call is the correct,
        equivalence-preserving binding (mirrors ``execute``'s ``inputs[name] =
        None`` for the same case), not a placeholder for a missing wire;
      * a MANY-cardinality port (fan-in) -> binds to a Python list-literal
        expression string over all upstream sources' variable names, e.g.
        "[a, b, c]", in the same deterministic (node_id, port_id) order
        `WiringMap.upstream` already returns -- so a node's codegen can splice
        it directly into an emitted call as a list argument. Zero sources
        binds to "[]" (distinct from a dangling Cardinality.ONE optional
        port, which binds to the "None" literal).

    A node instance may also *omit* an optional IN port altogether rather than
    declaring it unwired -- the two states are equivalent for a
    ``PortSpec.required=False`` port, and `execute` already treats them alike via
    ``inputs.get(name)``. When *node_registry* is supplied, any optional IN port
    the node type declares but this instance lacks is backfilled with the same
    literal a declared-but-dangling port would get ("None", or "[]" for a MANY
    port), so codegen never depends on which of the two states the canvas
    happens to have produced (issue #111). Passing no registry keeps the
    instance-only behaviour -- callers that hold a registry (the compiler,
    `inspect.build_step_traces`) should pass it.
    """
    in_vars: dict[str, str] = {}
    out_vars: dict[str, str] = {}
    param_exprs = {p.name: repr(p.value) for p in node.params}

    for port in node.ports:
        if port.direction == Direction.OUT:
            out_vars[port.name] = name_map.var_for(node.id, port.id)
        elif port.direction == Direction.IN:
            sources = wiring_map.upstream(node.id, port.id)
            if port.cardinality == Cardinality.MANY:
                var_names = [name_map.var_for(s.node_id, s.port_id) for s in sources]
                in_vars[port.name] = "[" + ", ".join(var_names) + "]"
            elif len(sources) == 0:
                in_vars[port.name] = "None"
            elif len(sources) == 1:
                source = sources[0]
                in_vars[port.name] = name_map.var_for(source.node_id, source.port_id)
            else:
                raise ValueError(
                    f"IN port {port.name!r} on node {node.id!r} has {len(sources)} "
                    "sources but Cardinality.ONE; only one source is allowed. This "
                    "should be unreachable -- build_wiring_map raises CardinalityError "
                    "for this case first."
                )

    if node_registry is not None:
        definition_cls = node_registry.try_get(node.type)
        if definition_cls is not None:
            for spec in definition_cls.ports:
                if spec.direction != Direction.IN or spec.required or spec.name in in_vars:
                    # Only optional ports are backfilled: an absent *required* port
                    # is a malformed node, and `in_var`'s KeyError (matching
                    # `execute`'s `inputs[name]` KeyError) is the right outcome.
                    continue
                in_vars[spec.name] = "[]" if spec.cardinality == Cardinality.MANY else "None"

    return CodegenContext(in_vars=in_vars, out_vars=out_vars, param_exprs=param_exprs)
