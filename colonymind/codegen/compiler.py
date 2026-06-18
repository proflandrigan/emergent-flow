"""colonymind.codegen.compiler
~~~~~~~~~~~~~~~~~~~~~~~~~~~
This module implements the core graph compiler for Colony Mind. It provides the
`compile_to_code` function, which transforms a functional IR graph into runnable
Python source code.

This compiler is committed to by ADR 0002 for pure `compile_to_code(graph) -> str`
transformation. It composes the Story 2 traversal and wiring plumbing, the Story 3
naming map, and the Story 4 per-node binding context into a single Python module.
It leverages ADR 0008 for templating in the functional paradigm and uses `ruff format`
for a final formatting pass. ADR 0009 defines the binding context, and ADR 0010
specifies the entry point and package placement.

Currently, only `Paradigm.FUNCTIONAL` graphs are handled by this compiler. The
`Paradigm.DECLARATIVE` branch is a separate compiler path, slated for Epic 2 Story 8.
"""

from __future__ import annotations

import textwrap

from colonymind.api import public_op
from colonymind.codegen.context import build_codegen_context
from colonymind.codegen.errors import CodegenError, UnboundInputError
from colonymind.codegen.formatting import format_source
from colonymind.codegen.naming import build_name_map
from colonymind.codegen.traversal import topological_sort
from colonymind.codegen.wiring import build_wiring_map
from colonymind.ir import Direction, Graph, Node, Paradigm
from colonymind.nodes import get as get_node_definition
from colonymind.nodes.contract import CodeFragment


def _describe(node: Node) -> str:
    """Human-readable identifier for a node in error messages."""
    label = (node.label or "").strip()
    if label:
        return f"{label!r} (id={node.id})"
    return f"{node.type!r} (id={node.id})"


@public_op(name="cm.compile_to_code")
def compile_to_code(graph: Graph) -> str:
    """Compiles a Colony Mind IR graph into runnable Python source code.

    Args:
        graph: The IR graph to compile.

    Returns:
        A string containing the generated Python source code.

    Raises:
        CodegenError: If the graph contains declarative paradigm nodes, or if
                      `format_source` encounters an error.
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

    # Step 4: Per-node codegen
    name_map = build_name_map(graph)
    code_fragments: list[CodeFragment] = []
    for node_id in topo_order_ids:
        node = graph.nodes[node_id]
        definition_cls = get_node_definition(node.type)
        definition = definition_cls()
        ctx = build_codegen_context(node, name_map, wiring_map)
        fragment = definition.codegen(node, ctx)
        code_fragments.append(fragment)

    # Step 5: Import collection
    all_imports: set[str] = set()
    for fragment in code_fragments:
        all_imports.update(fragment.imports)
    import_block = "\n".join(sorted(all_imports))

    # Step 6: Body assembly
    body_lines: list[str] = []
    for fragment in code_fragments:
        if fragment.body:
            body_lines.append(textwrap.indent(fragment.body, "    "))

    # Every per-node fragment binds a variable to each of its OUT ports, but an
    # OUT port with no downstream consumer (a leaf/terminal result, e.g. the
    # final ANOVA result in a fan-out) would otherwise be "assigned but never
    # used" and fail the project's ruff lint gate. Explicitly `del` those leaf
    # bindings rather than changing main()'s `-> None` shape to return them;
    # exposing leaf results from an exported script is Story 7's concern.
    leaf_vars: list[str] = []
    for node_id in topo_order_ids:
        node = graph.nodes[node_id]
        for port in node.ports:
            if port.direction == Direction.OUT and not wiring_map.consumers(node.id, port.id):
                leaf_vars.append(name_map.var_for(node.id, port.id))
    if leaf_vars:
        body_lines.append(textwrap.indent(f"del {', '.join(leaf_vars)}", "    "))

    main_body = "\n".join(body_lines) if body_lines else "    pass"

    # Step 7: Module assembly
    module_source = f'''
"""Generated by Colony Mind. Do not edit by hand."""

{import_block}

def main() -> None:
{main_body}

if __name__ == "__main__":
    main()
'''

    # Step 8: Format pass
    return format_source(module_source)
