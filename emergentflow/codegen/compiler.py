"""emergentflow.codegen.compiler
~~~~~~~~~~~~~~~~~~~~~~~~~~~
This module implements the core graph compiler for Emergent Flow. It provides the
`compile_to_code` function, which transforms a functional IR graph into runnable
Python source code.

This compiler is committed to by ADR 0002 for pure `compile_to_code(graph) -> str`
transformation. It composes the Story 2 traversal and wiring plumbing, the Story 3
naming map, and the Story 4 per-node binding context into a single Python module.
It leverages ADR 0008 for templating in the functional paradigm and uses `ruff format`
for a final formatting pass. ADR 0009 defines the binding context, and ADR 0010
specifies the entry point and package placement.

`compile_to_code` dispatches on `graph.paradigm`: `Paradigm.FUNCTIONAL` graphs are
assembled via the string-template pipeline in this module, while
`Paradigm.DECLARATIVE` graphs are delegated to `compile_declarative`
(`emergentflow.codegen.declarative`), the libcst-based `nn.Module` generator (ADR
0008, Epic 2 Story 8). Both paths share the same final `format_source` pass.
"""

from __future__ import annotations

import contextlib
import textwrap
from dataclasses import dataclass, replace

from emergentflow.api import public_op
from emergentflow.clients import ClientKind
from emergentflow.codegen.composite import COMPOSITE_NODE_TYPE, resolve_composite_boundary
from emergentflow.codegen.context import CodegenContext, build_codegen_context
from emergentflow.codegen.declarative import compile_declarative
from emergentflow.codegen.errors import CodegenError, UnboundInputError
from emergentflow.codegen.formatting import format_source
from emergentflow.codegen.naming import NameMap, _sanitize_identifier, _slugify, build_name_map
from emergentflow.codegen.traversal import topological_sort
from emergentflow.codegen.validation import enforce_validation_gate, required_in_port_names
from emergentflow.codegen.wiring import build_wiring_map
from emergentflow.ir import Direction, Graph, Node, Paradigm
from emergentflow.llm.env import MissingAPIKeyError, resolve_api_key_env_name
from emergentflow.llm.secrets import provider_api_key_pairs
from emergentflow.nodes import get as get_node_definition
from emergentflow.nodes import registry as default_node_registry
from emergentflow.nodes.contract import CodeFragment

# The catalog key of the markdown-note node type (emergentflow/nodes/examples/
# markdown_note.py). The compiler special-cases this one node type so an
# *anchored* note's text is emitted as a comment adjacent to whatever it
# annotates -- a note has zero ports/edges, so plain topological order alone
# can't place its text near its anchor. This is intentionally a small,
# contained exception in the assembly pass, not a change to topological_sort
# itself or to the generic per-node codegen contract (the note's own
# `codegen()` still always returns an empty body; this string constant is the
# only place compiler.py knows about a specific node type).
_NOTE_NODE_TYPE = "notes.markdown"


def _describe(node: Node) -> str:
    """Human-readable identifier for a node in error messages."""
    label = (node.label or "").strip()
    if label:
        return f"{label!r} (id={node.id})"
    return f"{node.type!r} (id={node.id})"


def _note_target_node_id(graph: Graph, anchor_id: str) -> str | None:
    """Resolve a note's `anchor_id` to the node id it should be emitted next to.

    `anchor_id` may name a node directly, or an edge (in which case the note
    is emitted next to the edge's *target* node -- by the time that node's
    code runs, both the connection's source and target are bound, so the
    comment reads naturally as explaining the incoming connection). A stale
    or unresolvable `anchor_id` returns None (not an error -- see
    markdown_note.py's docstring: this node type does not validate
    `anchor_id` against the graph).
    """
    if anchor_id in graph.nodes:
        return anchor_id
    edge = graph.edges.get(anchor_id)
    if edge is not None:
        return edge.target.node_id
    return None


def _format_note_comment(content: str) -> str:
    """Render a note's markdown `content` as a Python comment block."""
    lines = content.splitlines() or [""]
    commented = "\n".join(f"# {line}" if line else "#" for line in lines)
    return f"# --- Note ---\n{commented}"


@dataclass(frozen=True)
class _AssembledModule:
    """Structured intermediate shared by compile_to_code and the equivalence harness."""

    imports: list[str]  # sorted, de-duplicated import lines
    body_statements: list[str]  # per-node fragment bodies, topo order, UNINDENTED
    name_map: NameMap
    out_ports: list[tuple[str, str, str]]  # (node_id, out_port_name, var_name), topo order
    leaf_vars: list[str]  # OUT-port vars with no downstream consumer
    needs_llm: bool  # True iff any node needs the LLM client seam (ADR 0017/0018)
    needs_warehouse: bool  # True iff any node needs the warehouse client seam (ADR 0018)
    needs_http: bool  # True iff any node needs the HTTP client seam (Epic 16 Story 1)
    env_hints: tuple[str, ...]  # sorted, deduped env vars a standalone run of this script needs
    connection_hints: tuple[str, ...]  # sorted, deduped LLM connection profile NAMES referenced
    # by nodes whose credential can't be resolved to a real env var without I/O (ADR 0002)


def _assemble(
    graph: Graph,
    *,
    param_overrides: dict[tuple[str, str], str] | None = None,
) -> _AssembledModule:
    """Runs the per-node compilation pipeline and returns its structured result.

    Shared seam between `compile_to_code` and the equivalence harness so both
    can build on the same graph traversal, naming, and codegen without
    duplicating the per-node assembly logic.

    `param_overrides`, when given, maps specific `(node_id, port_name)` dangling IN ports to a
    Python expression string to bind instead of the `"None"` literal, and exempts them from the
    dangling-*required*-input guard below — used exactly once, by `_codegen_composite`, to bind
    a composite node's subgraph boundary ports to the enclosing nested function's own parameter
    names (issue #117 stage 3). `compile_to_code`'s top-level call always passes
    `param_overrides=None`.
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

    # Step 3: Dangling-input guard (required IN ports only -- optional IN ports
    # may legitimately be unconnected; `build_codegen_context` binds those to
    # the `None` literal below).
    wiring_map = build_wiring_map(graph)
    for node_id in topo_order_ids:
        node = graph.nodes[node_id]
        required_in_names = required_in_port_names(node.type, default_node_registry)
        for port in node.ports:
            if port.direction != Direction.IN:
                continue
            if port.name not in required_in_names:
                continue
            if param_overrides is not None and (node.id, port.name) in param_overrides:
                continue
            if not wiring_map.upstream(node.id, port.id):
                raise UnboundInputError(
                    f"Input port {port.name!r} of node {_describe(node)} is unbound. "
                    "All input ports must be connected."
                )

    # Step 4: Per-node codegen
    name_map = build_name_map(graph)
    code_fragments: list[CodeFragment] = []
    needs_llm = False
    needs_warehouse = False
    needs_http = False
    env_hint_set: set[str] = set()
    connection_hint_set: set[str] = set()

    # Anchored notes: map each resolved target node id -> ordered list of
    # comment-formatted note bodies. Built in graph insertion order for
    # determinism when more than one note anchors to the same target (graph
    # insertion order matters when UUID-based ids make topo-order unstable
    # for zero-dependency nodes).
    note_comments_by_target: dict[str, list[str]] = {}
    for node_id in graph.nodes:
        node = graph.nodes[node_id]
        if node.type != _NOTE_NODE_TYPE:
            continue
        values = {p.name: p.value for p in node.params}
        raw_anchor_id = values.get("anchor_id")
        raw_content = values.get("content")
        if not isinstance(raw_anchor_id, str) or not isinstance(raw_content, str):
            continue
        anchor_id: str = raw_anchor_id
        content: str = raw_content
        if not anchor_id or not content:
            continue
        target_id = _note_target_node_id(graph, anchor_id)
        if target_id is None:
            continue
        note_comments_by_target.setdefault(target_id, []).append(content)

    for node_id in topo_order_ids:
        node = graph.nodes[node_id]
        ctx = build_codegen_context(node, name_map, wiring_map, default_node_registry)
        if param_overrides is not None:
            # A dangling boundary IN port normally binds to the "None" literal (Step 4's
            # generic per-node context has no idea it's meant to be externally supplied) --
            # rebind it to the enclosing composite's chosen expression instead. `CodegenContext`
            # is frozen, so this produces a new instance rather than mutating the shared one.
            overrides_for_node = {
                port_name: expr
                for (nid, port_name), expr in param_overrides.items()
                if nid == node.id
            }
            if overrides_for_node:
                ctx = replace(ctx, in_vars={**ctx.in_vars, **overrides_for_node})

        if node.type == COMPOSITE_NODE_TYPE:
            # A composite is compiled recursively (see `_codegen_composite`), never via
            # generic per-node dispatch -- its own `codegen()` raises NotImplementedError
            # on purpose. Its subgraph's own client/env/connection needs must still bubble
            # up into the enclosing module's `main()` signature and docstring hints.
            fragment, inner = _codegen_composite(node, ctx)
            needs_llm = needs_llm or inner.needs_llm
            needs_warehouse = needs_warehouse or inner.needs_warehouse
            needs_http = needs_http or inner.needs_http
            env_hint_set.update(inner.env_hints)
            connection_hint_set.update(inner.connection_hints)
        else:
            definition_cls = get_node_definition(node.type)
            definition = definition_cls()
            kinds = definition_cls.required_client_kinds()
            if ClientKind.LLM in kinds:
                needs_llm = True
                for provider, api_key_env, llm_connection in provider_api_key_pairs(node):
                    if llm_connection:
                        # A profile-name reference can't be resolved to a real env-var name here
                        # without reading connections.toml (I/O), which compile_to_code must
                        # never do (ADR 0002 purity) -- hint at the profile name itself instead.
                        connection_hint_set.add(llm_connection)
                        continue
                    # Best-effort hint only -- an unresolvable provider/api_key_env pair here is
                    # a real problem for an actual run (GatewayClient/the pre-flight check in
                    # emergentflow.llm.secrets will raise clearly when it matters), but
                    # compile_to_code's docstring hint is a courtesy, not a validation gate --
                    # skip it rather than making compilation itself fail on this.
                    with contextlib.suppress(MissingAPIKeyError):
                        env_hint_set.add(resolve_api_key_env_name(provider, api_key_env))
            if ClientKind.WAREHOUSE in kinds:
                needs_warehouse = True
            if ClientKind.HTTP in kinds:
                needs_http = True
            fragment = definition.codegen(node, ctx)

        code_fragments.append(fragment)
        for note_content in note_comments_by_target.get(node_id, []):
            code_fragments.append(CodeFragment(imports=[], body=_format_note_comment(note_content)))

    # Step 5: Import collection
    all_imports: set[str] = set()
    for fragment in code_fragments:
        all_imports.update(fragment.imports)
    imports = sorted(all_imports)

    # Step 6: Body assembly
    body_statements = [fragment.body for fragment in code_fragments if fragment.body]

    # Every per-node fragment binds a variable to each of its OUT ports. An OUT
    # port with no downstream consumer (a leaf/terminal result, e.g. the final
    # ANOVA result in a fan-out) is the pipeline's actual output: compile_to_code
    # collects these `leaf_vars` and `main()` returns them keyed by variable name
    # (Story 7), which also keeps them "used" under the project's ruff lint gate.
    leaf_vars: list[str] = []
    out_ports: list[tuple[str, str, str]] = []
    for node_id in topo_order_ids:
        node = graph.nodes[node_id]
        for port in node.ports:
            if port.direction != Direction.OUT:
                continue
            var_name = name_map.var_for(node.id, port.id)
            out_ports.append((node.id, port.name, var_name))
            if not wiring_map.consumers(node.id, port.id):
                leaf_vars.append(var_name)

    return _AssembledModule(
        imports=imports,
        body_statements=body_statements,
        name_map=name_map,
        out_ports=out_ports,
        leaf_vars=leaf_vars,
        needs_llm=needs_llm,
        needs_warehouse=needs_warehouse,
        needs_http=needs_http,
        env_hints=tuple(sorted(env_hint_set)),
        connection_hints=tuple(sorted(connection_hint_set)),
    )


def _codegen_composite(node: Node, ctx: CodegenContext) -> tuple[CodeFragment, _AssembledModule]:
    """Recursively compile a `layout.composite` node's subgraph into a nested function.

    Emits `def <fn_name>(...): ...subgraph body...; return ...` followed by a call-site
    statement, both as a single fragment body -- the whole-module compiler indents it
    uniformly into `main()`'s body (or an enclosing composite's own nested function body, for
    nested composites) exactly like any other node's fragment. Giving the subgraph its own
    nested Python scope means its variable names can never collide with the outer graph's or
    with a sibling composite's, without either graph needing name-uniqueness across the
    boundary -- the symmetric counterpart of `executor.py`'s `_execute_composite`, sharing the
    same `resolve_composite_boundary` canonical port mapping so ADR-0002 equivalence holds.

    Returns the node's own `CodeFragment` (for the enclosing `_assemble` call to append and to
    collect imports from, exactly like any other fragment) alongside the subgraph's full
    `_AssembledModule`, so the caller can bubble up its `needs_llm`/`needs_warehouse`/
    `needs_http`/env/connection hints into the enclosing module.
    """
    if node.subgraph is None:
        raise CodegenError(f"Composite node {_describe(node)} has no subgraph to compile.")

    boundary = resolve_composite_boundary(node.subgraph)
    in_ports = [p for p in node.ports if p.direction == Direction.IN]
    out_ports = [p for p in node.ports if p.direction == Direction.OUT]
    if len(in_ports) != len(boundary.dangling_in):
        raise CodegenError(
            f"Composite node {_describe(node)} declares {len(in_ports)} IN port(s) but its "
            f"subgraph has {len(boundary.dangling_in)} dangling IN port(s); they must match."
        )
    if len(out_ports) != len(boundary.exposed_out):
        raise CodegenError(
            f"Composite node {_describe(node)} declares {len(out_ports)} OUT port(s) but its "
            f"subgraph has {len(boundary.exposed_out)} exposed OUT port(s); they must match."
        )

    # Give each dangling boundary IN port a simple positional parameter name (p0, p1, ...) --
    # distinct from anything `build_name_map` would generate for the subgraph itself, since
    # those are always derived from node labels/types, never bare "p<N>".
    param_names = [f"p{i}" for i in range(len(in_ports))]
    param_overrides: dict[tuple[str, str], str] = {}
    for param_name, ref in zip(param_names, boundary.dangling_in, strict=True):
        owner = node.subgraph.nodes[ref.node_id]
        port_name = next(p.name for p in owner.ports if p.id == ref.port_id)
        param_overrides[(ref.node_id, port_name)] = param_name

    inner = _assemble(node.subgraph, param_overrides=param_overrides)

    return_vars = [inner.name_map.var_for(ref.node_id, ref.port_id) for ref in boundary.exposed_out]
    if not return_vars:
        return_stmt = "return None"
    elif len(return_vars) == 1:
        return_stmt = f"return {return_vars[0]}"
    else:
        return_stmt = f"return ({', '.join(return_vars)})"

    inner_body_lines = [*inner.body_statements, return_stmt]
    inner_body = textwrap.indent("\n".join(inner_body_lines), "    ")

    fn_name = "_composite_" + _sanitize_identifier(_slugify(node.id))
    call_args = [ctx.in_var(p.name) for p in in_ports]
    call_expr = f"{fn_name}({', '.join(call_args)})"
    out_vars = [ctx.out_var(p.name) for p in out_ports]
    if not out_vars:
        call_line = call_expr
    elif len(out_vars) == 1:
        call_line = f"{out_vars[0]} = {call_expr}"
    else:
        call_line = f"{', '.join(out_vars)} = {call_expr}"

    body = f"def {fn_name}({', '.join(param_names)}):\n{inner_body}\n{call_line}"

    return CodeFragment(imports=inner.imports, body=body), inner


@public_op(name="ef.compile_to_code")
def compile_to_code(graph: Graph) -> str:
    """Compiles an Emergent Flow IR graph into runnable Python source code.

    Args:
        graph: The IR graph to compile.

    Returns:
        A string containing the generated Python source code.

    Raises:
        CodegenError: If `format_source` encounters an error. DECLARATIVE
                      graphs are compiled via `compile_declarative`, which
                      raises `CodegenError` for declarative node types
                      outside the supported catalog (full catalog is Epic
                      10) and for agent/LangGraph targets (deferred to Epic
                      11).
        UnboundInputError: If a *required* input port (per its `PortSpec`) is
                           not connected to an upstream output port. An
                           optional (`required=False`) IN port left
                           unconnected is instead bound to the `None` literal.
        CycleError: If the graph contains a cycle (propagated from
                    `topological_sort`).
        GraphValidationError: If the graph has an error-severity validation
                              diagnostic (type incompatibility, cardinality
                              violation, or unconnected required IN port). Raised
                              before any code is emitted. Warnings do not block.
    """
    if graph.paradigm is Paradigm.DECLARATIVE:
        return format_source(compile_declarative(graph))

    # Story 6: gate the FUNCTIONAL path on validation before emitting any code,
    # so compile_to_code and execute reject identical graphs for identical
    # reasons (ADR 0002 equivalence extends to rejection). Warnings pass through.
    enforce_validation_gate(graph)

    assembled = _assemble(graph)

    import_block = "\n".join(assembled.imports)

    # A warehouse or HTTP graph threads the extensible Clients bundle; main()
    # unpacks each needed seam into the local names node fragments reference
    # (`warehouse`, `http`, and `client` when an LLM node is also present).
    # Emitted before the node bodies so those locals are in scope.
    needs_bundle = assembled.needs_warehouse or assembled.needs_http
    preamble_lines: list[str] = []
    if needs_bundle:
        if assembled.needs_warehouse:
            preamble_lines.append("warehouse = clients.warehouse if clients is not None else None")
        if assembled.needs_http:
            preamble_lines.append("http = clients.http if clients is not None else None")
        if assembled.needs_llm:
            preamble_lines.append("client = clients.llm if clients is not None else None")

    body_lines = [
        textwrap.indent(stmt, "    ") for stmt in preamble_lines + assembled.body_statements
    ]

    return_items = ", ".join(f'"{var}": {var}' for var in assembled.leaf_vars)
    return_line = textwrap.indent(f"return {{{return_items}}}", "    ")
    body_lines.append(return_line)

    main_body = "\n".join(body_lines)

    if needs_bundle:
        main_signature = "def main(*, clients: object | None = None) -> dict[str, object]:"
        boiler = "    from emergentflow.clients import Clients\n"
        seams = []
        if assembled.needs_llm:
            boiler += "    from emergentflow.llm.gateway import GatewayClient\n"
            seams.append("llm=GatewayClient()")
        if assembled.needs_warehouse:
            seams.append("warehouse=None")
        if assembled.needs_http:
            seams.append("http=None")
        boiler += "\n"
        if assembled.needs_warehouse:
            boiler += (
                "    # A warehouse graph needs a WarehouseClient injected "
                "(emergentflow.data.warehouse);\n"
                "    # replace warehouse=None with your configured client before running.\n"
            )
        if assembled.needs_http:
            boiler += (
                "    # An HTTP graph needs an HttpClient injected "
                "(emergentflow.data.http);\n"
                "    # replace http=None with your configured client before running.\n"
            )
        boiler += f"    _results = main(clients=Clients({', '.join(seams)}))"
        main_call = boiler
    elif assembled.needs_llm:
        # Byte-identical to the pre-ADR-0018 LLM path (Epic 9 Story 1 back-compat gate).
        main_signature = "def main(*, client: object | None = None) -> dict[str, object]:"
        # A standalone run of this script needs a real client to reach an LLM
        # provider (ADR 0017), so the boilerplate constructs a `GatewayClient`
        # rather than calling `main()` with no arguments -- otherwise every
        # exported script for an LLM graph would raise `MissingClientError`
        # unconditionally when run directly.
        main_call = (
            "    from emergentflow.llm.gateway import GatewayClient\n\n"
            "    _results = main(client=GatewayClient())"
        )
    else:
        main_signature = "def main() -> dict[str, object]:"
        main_call = "    _results = main()"

    # Step 7: Module assembly
    if assembled.needs_llm and (assembled.env_hints or assembled.connection_hints):
        hint_lines = [f"    export {name}=..." for name in assembled.env_hints]
        hint_lines += [
            f"    uses LLM connection profile {name!r} -- configure it via the canvas's "
            "Manage Connections panel or `emergentflow connections list`"
            for name in assembled.connection_hints
        ]
        docstring_body = (
            "Generated by Emergent Flow. Do not edit by hand.\n\n"
            "This script calls an LLM provider. Before running it, set:\n" + "\n".join(hint_lines)
        )
    else:
        docstring_body = "Generated by Emergent Flow. Do not edit by hand."

    # `docstring_body` embeds env-var names (from `api_key_env` node params) and LLM connection
    # profile names (from `llm_connection` node params) -- escape backslashes and double quotes
    # so a value containing `"""` can't break out of the docstring literal and inject statements
    # into the generated module (unlike the sibling `!r`-formatted values in each node's own
    # codegen, this hint is assembled here as raw text, not through `repr`).
    escaped_docstring_body = docstring_body.replace("\\", "\\\\").replace('"', '\\"')
    module_source = f'''
"""{escaped_docstring_body}"""

{import_block}

{main_signature}
{main_body}

if __name__ == "__main__":
{main_call}
    for _name, _value in _results.items():
        print(f"{{_name}} = {{_value!r}}")
'''

    # Step 8: Format pass
    return format_source(module_source)
