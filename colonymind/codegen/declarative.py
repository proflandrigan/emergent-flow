"""
colonymind.codegen.declarative
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The declarative (``nn.Module``) code-generation engine (Epic 2, Story 8).

`compiler.py` (Story 5) compiles `Paradigm.FUNCTIONAL` graphs into a flat
script. This module is the sibling path for `Paradigm.DECLARATIVE` graphs: a
single `nn.module` node owning a subgraph of layer nodes is compiled into an
`nn.Module` subclass, with the layer subgraph's topological order driving both
`__init__` (one `self.<attr> = <layer ctor>` per layer) and `forward` (a
rolling-variable chain of calls through the layers).

This is a narrow seam, not the full declarative compiler:

* **Layer catalog.** Only the reference layers registered for this story
  (``nn.linear``, ``nn.relu``) are supported. The full PyTorch layer catalog,
  along with tensor-shape-aware codegen, is Epic 10.
* **Forward shape.** The `forward` body assumes a single linear chain (no
  branching/fan-out DAGs). General DAG forward codegen is Epic 10.
* **Agent/LangGraph seam.** Node types prefixed ``"agent."`` or
  ``"langgraph."`` are detected and explicitly rejected here with a
  `CodegenError` pointing at Epic 11 — this module documents that seam but
  does not implement it.

`compile_declarative` is built, like `compile_to_code`, as a pure
``(graph) -> str`` transform (ADR 0002): no I/O, no global state. Per ADR
0008, the class/method structure is assembled as REAL libcst nodes
(`ClassDef`, `FunctionDef`, `IndentedBlock`, `Parameters`, `Param`) rather than
string concatenation; only leaf statement lines go through
`cst.parse_statement`. The returned source is UNFORMATTED — the caller
(Story 9 / Task 04) runs the single shared `ruff format` pass via
`colonymind.codegen.formatting.format_source`.
"""

from __future__ import annotations

import keyword

import libcst as cst

from colonymind.codegen.context import CodegenContext
from colonymind.codegen.errors import CodegenError
from colonymind.codegen.naming import _base_name
from colonymind.codegen.traversal import topological_sort
from colonymind.codegen.wiring import WiringMap, build_wiring_map
from colonymind.ir import Direction, Graph, Node
from colonymind.ir.common import IRId
from colonymind.nodes import get as get_node_definition

_SUPPORTED_LAYER_TYPES = {"nn.linear", "nn.relu"}
_AGENT_NODE_PREFIXES = ("agent.", "langgraph.")
_MODULE_TYPE = "nn.module"


def _check_for_agent_nodes(graph: Graph) -> None:
    """Raise CodegenError if *graph* contains any agent/LangGraph node.

    Documents the Epic 11 seam: this module proves only the declarative
    nn.Module path, not the agent/LangGraph one.
    """
    for node in graph.nodes.values():
        if node.type.startswith(_AGENT_NODE_PREFIXES):
            raise CodegenError(
                "Agent/LangGraph codegen is deferred to Epic 11; the declarative "
                "seam in this epic only proves the nn.Module path."
            )


def _class_name(label: str | None) -> str:
    """Derive a valid Python class name from a node *label*.

    A non-empty label that is already a valid, non-keyword identifier is
    returned verbatim (preserving author-chosen names like
    ``"SimpleClassifier"``). Otherwise a PascalCase name is derived from the
    `_base_name`-style snake_case slug; an empty/unusable label falls back to
    ``"Module"``.
    """
    if label and label.isidentifier() and not keyword.iskeyword(label):
        return label

    slug = (label or "").strip()
    if not slug:
        return "Module"

    # Reuse the naming module's slugification rules via a throwaway Node so
    # we don't reimplement the ASCII/keyword-safety logic here.
    pseudo_node = Node(type=_MODULE_TYPE, label=slug)
    base = _base_name(pseudo_node)
    pascal = "".join(part.capitalize() for part in base.split("_") if part)
    return pascal or "Module"


def _layer_constructor(node: Node) -> tuple[str, list[str]]:
    """Return *(constructor_expression, imports)* for a layer *node*.

    Looks up the node's `NodeDefinition`, runs its `codegen` against a
    `CodegenContext.preview` (layer constructors ignore the context), and
    returns the bare constructor expression body plus that fragment's
    imports.
    """
    definition = get_node_definition(node.type)()
    fragment = definition.codegen(node, CodegenContext.preview(node))
    return fragment.body, list(fragment.imports)


def _assign_attr_names(order: list[IRId], subgraph: Graph) -> dict[IRId, str]:
    """Assign collision-safe, deterministic attribute names to layer nodes.

    Walks *order* (already deterministic topo order) and assigns each node's
    `_base_name`; a base name already used by an earlier node in the same
    walk is disambiguated by appending ``_2``, ``_3``, ... until unique.
    """
    attr_for: dict[IRId, str] = {}
    used: set[str] = set()
    for node_id in order:
        node = subgraph.nodes[node_id]
        base = _base_name(node)
        candidate = base
        suffix = 2
        while candidate in used:
            candidate = f"{base}_{suffix}"
            suffix += 1
        used.add(candidate)
        attr_for[node_id] = candidate
    return attr_for


def _forward_input_name(order: list[IRId], subgraph: Graph, wiring: WiringMap) -> str:
    """Return the module's forward-input name: the first dangling IN port name.

    Scans *order* for the first layer with a dangling IN port (no upstream
    edge inside the subgraph) and returns that port's name. Falls back to
    ``"x"`` if every layer's IN ports are bound (should not happen for a
    well-formed single-chain subgraph, but keeps this function total).
    """
    for node_id in order:
        node = subgraph.nodes[node_id]
        for port in node.ports:
            if port.direction != Direction.IN:
                continue
            if not wiring.upstream(node.id, port.id):
                return port.name
    return "x"


def compile_declarative(graph: Graph) -> str:
    """Compile a `Paradigm.DECLARATIVE` graph into `nn.Module` source.

    The graph must own exactly one ``nn.module`` node, whose `subgraph` holds
    a single linear chain of supported layer nodes (currently ``nn.linear``
    and ``nn.relu``). The module's class body is built as real libcst nodes
    (ADR 0008): `__init__` assigns one `self.<attr>` per layer (in
    topological order), and `forward` threads a rolling variable through each
    layer's call and returns it.

    Returns the UNFORMATTED module source as a string — the caller runs the
    shared `ruff format` pass (Story 9 / Task 04); this function does not
    format or otherwise shell out.

    Raises
    ------
    CodegenError
        If the graph (or the module's subgraph) contains an agent/LangGraph
        node (Epic 11), if the graph does not have exactly one ``nn.module``
        node, if that node has no subgraph, or if the subgraph contains a
        layer type outside `_SUPPORTED_LAYER_TYPES` (the full PyTorch layer
        catalog is Epic 10).
    """
    # Step 1: Agent/LangGraph seam, top level.
    _check_for_agent_nodes(graph)

    # Step 2: Locate the single nn.module node.
    module_nodes = [n for n in graph.nodes.values() if n.type == _MODULE_TYPE]
    if len(module_nodes) == 0:
        raise CodegenError(
            "Declarative codegen requires exactly one 'nn.module' node; the full "
            "declarative catalog is Epic 10."
        )
    if len(module_nodes) > 1:
        raise CodegenError(
            "Declarative codegen supports a single 'nn.module' node; multi-module "
            "graphs are Epic 10."
        )
    module_node = module_nodes[0]
    if module_node.subgraph is None:
        raise CodegenError(f"nn.module node {module_node.id!r} has no subgraph to compile.")

    # Step 3: Validate the subgraph's layer types.
    subgraph = module_node.subgraph
    _check_for_agent_nodes(subgraph)
    for node in subgraph.nodes.values():
        if node.type != _MODULE_TYPE and node.type not in _SUPPORTED_LAYER_TYPES:
            raise CodegenError(
                f"Declarative layer type {node.type!r} is not supported by the "
                "Story 8 seam; the full PyTorch layer catalog is Epic 10."
            )

    # Step 4: Deterministic traversal + wiring.
    order = topological_sort(subgraph)
    wiring = build_wiring_map(subgraph)

    # Step 5: Collision-safe attribute names, in topo order.
    attr_for = _assign_attr_names(order, subgraph)

    # Step 6: Forward input name (the first dangling IN port in topo order).
    forward_input_name = _forward_input_name(order, subgraph, wiring)

    # Step 7: Collect imports + per-layer constructor expressions.
    imports: set[str] = set()
    ctor_for: dict[IRId, str] = {}
    for node_id in order:
        node = subgraph.nodes[node_id]
        body, node_imports = _layer_constructor(node)
        ctor_for[node_id] = body
        imports.update(node_imports)

    class_name = _class_name(module_node.label)

    # Step 8: Build the CST.

    # __init__ body: super().__init__() then one self.<attr> = <ctor> per layer.
    init_body: list[cst.BaseStatement] = [cst.parse_statement("super().__init__()")]
    for node_id in order:
        attr = attr_for[node_id]
        ctor_expr = ctor_for[node_id]
        init_body.append(cst.parse_statement(f"self.{attr} = {ctor_expr}"))

    init_fn = cst.FunctionDef(
        name=cst.Name("__init__"),
        params=cst.Parameters(params=[cst.Param(cst.Name("self"))]),
        body=cst.IndentedBlock(body=init_body),
    )

    # forward body: rolling variable threaded through each layer call, in
    # topo order, then a final return. This assumes a single linear chain;
    # general DAG/branching forward codegen is Epic 10.
    forward_body: list[cst.BaseStatement] = []
    cur = forward_input_name
    for node_id in order:
        attr = attr_for[node_id]
        forward_body.append(cst.parse_statement(f"{cur} = self.{attr}({cur})"))
    forward_body.append(cst.parse_statement(f"return {cur}"))

    forward_fn = cst.FunctionDef(
        name=cst.Name("forward"),
        params=cst.Parameters(
            params=[cst.Param(cst.Name("self")), cst.Param(cst.Name(forward_input_name))]
        ),
        body=cst.IndentedBlock(body=forward_body),
    )

    class_def = cst.ClassDef(
        name=cst.Name(class_name),
        bases=[cst.Arg(cst.Attribute(value=cst.Name("nn"), attr=cst.Name("Module")))],
        body=cst.IndentedBlock(body=[init_fn, forward_fn]),
    )

    header_docstring_line = cst.parse_statement(
        '"""Generated by Colony Mind. Do not edit by hand."""'
    )
    # The Story 8 seam's only supported layers (nn.linear, nn.relu) both import
    # `torch.nn as nn`; the single collected import line is emitted verbatim.
    import_line = cst.parse_statement(next(iter(sorted(imports))))

    module = cst.Module(body=[header_docstring_line, import_line, class_def])

    return module.code
