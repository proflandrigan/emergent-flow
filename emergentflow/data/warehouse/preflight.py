"""
emergentflow.data.warehouse.preflight
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Pre-flight connection/credential presence check (Epic 13 Story 3, ADR 0018) —
the ``emergentflow.llm.secrets`` analog for warehouses. Runs BEFORE a run starts
so a missing profile or unset credential fails fast with a clear error naming the
missing profile / env var (never a value), rather than deep inside a query.

Reads ``os.environ`` (an edge-level effect, like the effectful client) but never
the IR beyond the connection-profile *name* the node carries (ADR 0018).
"""

from __future__ import annotations

import os
from collections.abc import Collection

from emergentflow.data.warehouse.credentials import required_env_vars
from emergentflow.data.warehouse.profiles import ProfileStore
from emergentflow.ir import Graph, Node


class MissingConnectionProfileError(RuntimeError):
    """Raised when a node references a connection profile absent from the store."""


def connection_name_for_node(node: Node) -> str | None:
    """Return the connection-profile name a node references, or ``None``.

    A warehouse node carries a ``connection`` param whose value is the profile
    name (ADR 0018). Detection is by that param's presence — no other node family
    carries a ``connection`` param — so this stays correct without importing the
    (Story 4/5) query node types.
    """
    for param in node.params:
        if param.name == "connection" and isinstance(param.value, str) and param.value:
            return param.value
    return None


def validate_connections_present(
    graph: Graph, store: ProfileStore, node_ids: Collection[str] | None = None
) -> None:
    """Raise if any warehouse node's profile is unknown or its env vars are unset.

    Parameters
    ----------
    graph: the graph about to run.
    store: the local connection-profile store to resolve names against.
    node_ids: if given, only these nodes are checked; else every node.

    Raises
    ------
    MissingConnectionProfileError
        Naming the first unknown profile found (and the node referencing it).
    emergentflow.data.warehouse.credentials.MissingConnectionCredentialError
        Naming the first unset credential env var found (never a value).
    """
    from emergentflow.data.warehouse.credentials import MissingConnectionCredentialError

    targets = graph.nodes.values() if node_ids is None else (graph.nodes[nid] for nid in node_ids)
    for node in targets:
        name = connection_name_for_node(node)
        if name is None:
            continue
        if name not in store:
            raise MissingConnectionProfileError(
                f"Node {node.label or node.id!r} references connection profile {name!r}, "
                f"which is not in the local store. Known profiles: "
                f"{', '.join(store.names()) or '<none>'}."
            )
        profile = store.get(name)
        for env_name in required_env_vars(profile):
            if not os.environ.get(env_name):
                raise MissingConnectionCredentialError(
                    f"Node {node.label or node.id!r} (connection {name!r}) needs the "
                    f"{env_name!r} environment variable, which is not set. Export it before "
                    f"running this graph, e.g.:\n    export {env_name}=<value>"
                )
