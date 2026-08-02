"""
emergentflow.codegen.params
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Graph-level parameter resolution (issue #116).

A graph may declare a ``params`` map; a node param may carry a ``ref`` naming one of those
graph params instead of a literal ``value``. This module is the single pure seam that turns
refs into concrete values: ``resolve_graph_params`` applies runtime overrides on top of each
graph param's stored value, and ``materialize_graph`` returns a deep copy of the graph in which
every ref'd node param has its resolved value baked into ``param.value`` (recursing into
composite subgraphs). The executor, the server, and the reproducibility capture all route
through it, so per-node ``execute``/``codegen`` implementations keep reading ``node.params``
values unchanged.
"""

from __future__ import annotations

from typing import Any

from emergentflow.ir.graph import Graph
from emergentflow.ir.node import Node

__all__ = [
    "GraphParamError",
    "has_graph_param_refs",
    "resolve_graph_params",
    "materialize_graph",
]


class GraphParamError(ValueError):
    """Raised when graph-parameter resolution fails.

    Covers an override key that names no graph-level param, and (defensively, for
    callers that bypass the validator) a node ``ref`` that names no graph-level param.
    """


def has_graph_param_refs(graph: Graph) -> bool:
    """True when any node (recursively, through composite subgraphs) carries a ref'd param.

    Shared by the executor and the server to decide whether ``materialize_graph`` is needed
    before running a graph that received no explicit overrides.
    """
    for node in graph.nodes.values():
        if any(p.ref is not None for p in node.params):
            return True
        if node.subgraph is not None and has_graph_param_refs(node.subgraph):
            return True
    return False


def resolve_graph_params(
    graph: Graph, *, overrides: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Return every graph-level param's resolved value, applying *overrides*.

    Pure: reads only *graph* and returns a new dict; never mutates the graph. An
    override key that names no graph-level param raises ``GraphParamError``.
    """
    resolved: dict[str, Any] = {}
    for name, param in graph.params.items():
        if overrides is not None and name in overrides:
            resolved[name] = overrides[name]
        else:
            resolved[name] = param.value
    if overrides:
        unknown = sorted(set(overrides) - set(graph.params))
        if unknown:
            defined = sorted(graph.params)
            listed = ", ".join(repr(k) for k in defined)
            suffix = f"graph defines: {listed}" if defined else "graph defines none"
            raise GraphParamError(
                "unknown graph-parameter override(s): "
                + ", ".join(repr(k) for k in unknown)
                + "; "
                + suffix
            )
    return resolved


def _resolve_node_params(node: Node, resolved: dict[str, Any]) -> None:
    """Bake resolved values into every ref'd param of *node* (mutating only *node*)."""
    if node.subgraph is not None:
        for sub_node in node.subgraph.nodes.values():
            _resolve_node_params(sub_node, resolved)
    for param in node.params:
        if param.ref is not None:
            if param.ref not in resolved:
                raise GraphParamError(
                    f"node {node.id!r} param {param.name!r} references graph parameter "
                    f"{param.ref!r} which is not defined"
                )
            param.value = resolved[param.ref]


def materialize_graph(graph: Graph, *, params: dict[str, Any] | None = None) -> Graph:
    """Return a deep copy of *graph* with every ref'd node param resolved to a concrete value.

    *params* are runtime overrides applied on top of each graph-level param's stored value
    (see ``resolve_graph_params``). Composite node subgraphs are resolved recursively. The
    input *graph* is never mutated; the returned copy's ``params`` map is left untouched.
    """
    materialized = graph.model_copy(deep=True)
    resolved = resolve_graph_params(graph, overrides=params)
    for node in materialized.nodes.values():
        _resolve_node_params(node, resolved)
    return materialized
