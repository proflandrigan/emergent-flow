"""
emergentflow.llm.secrets
~~~~~~~~~~~~~~~~~~~~~~~~
Pre-flight API-key presence check (Epic 9 Story 9). Runs BEFORE a graph/node execution starts
so a missing key fails fast with a clear, actionable error naming the env var -- never its
value -- rather than surfacing deep inside a `GatewayClient.complete()` call partway through a
run. Reads `os.environ` (an edge-level effect, like `GatewayClient` itself) but never the IR;
the graph only ever carries an env-var *name* (ADR 0017), so there is no key value in this
module's reach to begin with.
"""

from __future__ import annotations

import os
from collections.abc import Collection
from typing import Any, cast

from emergentflow.ir import Graph, Node
from emergentflow.llm.env import MissingAPIKeyError, resolve_api_key_env_name
from emergentflow.nodes import get as get_node_definition


def provider_api_key_pairs(node: Node) -> list[tuple[str, str | None]]:
    """Return every `(provider, api_key_env)` pair *node* would resolve a key for at run time.

    Handles the two node shapes that currently set `requires_client = True`:
    - `llm.call`: one pair from its own `provider`/`api_key_env` params.
    - `eval.run`: one pair per entry in its `variants` param (each a dict with its own
      `provider` and optional `api_key_env`).
    Any other `requires_client` node type found in the future would need a case added here --
    until then, a node type this function doesn't recognize contributes no pairs (so it's
    silently not pre-flight-checked rather than raising a confusing internal error; a real
    missing key for such a node would still surface at `GatewayClient.complete()` time).
    """
    values = {p.name: p.value for p in node.params}
    if node.type == "llm.call":
        provider = cast(str, values.get("provider") or "anthropic")
        api_key_env = cast("str | None", values.get("api_key_env"))
        return [(provider, api_key_env)]
    if node.type == "eval.run":
        variants = cast("list[dict[str, Any]]", values.get("variants") or [])
        return [(v["provider"], v.get("api_key_env")) for v in variants if "provider" in v]
    return []


def validate_api_keys_present(graph: Graph, node_ids: Collection[str] | None = None) -> None:
    """Raise `MissingAPIKeyError` if any client-requiring node's resolved API key env var is
    unset in `os.environ`, before a run of *graph* starts.

    Parameters
    ----------
    graph:
        The graph about to run.
    node_ids:
        If given, only these node ids are checked (e.g. `execute_node`'s single target node);
        otherwise every node in the graph is checked (e.g. a full `execute_graph`/
        `execute_graph_stream` run).

    Raises
    ------
    MissingAPIKeyError
        Naming the first unresolved/unset env var found (never a key value).
    """
    targets = graph.nodes.values() if node_ids is None else (graph.nodes[nid] for nid in node_ids)
    for node in targets:
        definition_cls = get_node_definition(node.type)
        if not definition_cls.requires_client:
            continue
        for provider, api_key_env in provider_api_key_pairs(node):
            env_name = resolve_api_key_env_name(provider, api_key_env)
            if not os.environ.get(env_name):
                raise MissingAPIKeyError(
                    f"Node {node.label or node.id!r} (type {node.type!r}) needs the "
                    f"{env_name!r} environment variable, which is not set. Export it before "
                    f"running this graph, e.g.:\n    export {env_name}=<your api key>"
                )
