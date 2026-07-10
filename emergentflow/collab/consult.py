"""
emergentflow.collab.consult
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Mode-B one-shot consult (Epic 14 Story 8): composes a persona's system prompt +
a graph slice + catalog context into an LLM call, parses the structured response
into a ``set_params``-only ``GraphMutation``.

Works without agents: never imported by ``emergentflow/__init__.py``,
``emergentflow/ir/__init__.py``, or anything under ``emergentflow/codegen/`` --
collaboration is an additive, opt-in layer (ADR 0019).
"""

from __future__ import annotations

from typing import Any

from emergentflow.collab.personas import get_persona
from emergentflow.ir.graph import Graph
from emergentflow.ir.mutation import GraphMutation
from emergentflow.llm.protocol import LLMClient


class ConsultError(RuntimeError):
    """Raised when a consult cannot produce a usable GraphMutation.

    Covers: an unknown target node id, or an LLM response that passed
    ``llm.call``'s own structured-output schema check but still doesn't carry a
    usable ``set_params`` mapping (e.g. the wrong Python type inside a value the
    schema subset doesn't check deeply enough to catch).
    """


_SET_PARAMS_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["set_params"],
    "properties": {
        "set_params": {"type": "object"},
    },
}


def _catalog_entry_for(node_type: str) -> dict[str, Any] | None:
    """Return the /catalog entry dict for *node_type*, or None if not found."""
    from emergentflow.server.service import get_catalog

    for entry in get_catalog()["nodes"]:
        if entry["type"] == node_type:
            return entry
    return None


def build_consult_messages(
    graph: Graph, *, persona_slug: str, node_ids: list[str], ask: str
) -> list[dict[str, str]]:
    """Build the [system, user] messages for a consult LLM call.

    Raises
    ------
    UnknownPersonaError
        If *persona_slug* is not registered.
    ConsultError
        If any id in *node_ids* is not present in *graph*.
    """
    persona = get_persona(persona_slug)

    missing = [nid for nid in node_ids if nid not in graph.nodes]
    if missing:
        raise ConsultError(f"consult target node id(s) not found in the graph: {missing!r}")

    target_nodes = []
    for nid in node_ids:
        node = graph.nodes[nid]
        catalog_entry = _catalog_entry_for(node.type)
        target_nodes.append(
            {
                "id": node.id,
                "type": node.type,
                "current_params": [p.model_dump(mode="json") for p in node.params],
                "legal_params": catalog_entry["params"] if catalog_entry else [],
            }
        )

    system = persona.system_prompt or (
        f"You are {persona.label}, an assistant that fills in graph node parameters."
    )
    user = (
        f"Task: {ask}\n\n"
        f"Target nodes (fill params ONLY for these ids, using ONLY the legal_params "
        f"names listed for each):\n"
        f"{target_nodes!r}\n\n"
        'Respond with JSON of the exact shape {"set_params": {"<node_id>": '
        '{"<param_name>": <value>, ...}, ...}} -- no other keys, no prose.'
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def run_consult(
    graph: Graph,
    *,
    persona_slug: str,
    node_ids: list[str],
    ask: str,
    base_version: int,
    client: LLMClient,
    provider: str = "anthropic",
    model: str = "claude-sonnet-5",
) -> GraphMutation:
    """Run one Mode-B consult and return the resulting ``set_params``-only GraphMutation.

    Raises
    ------
    UnknownPersonaError, ConsultError
        See ``build_consult_messages``.
    MissingClientError, StructuredOutputValidationError, GatewayResponseError, MissingAPIKeyError
        Propagated from ``emergentflow.llm.call`` / the injected client -- a malformed or
        failed LLM interaction surfaces as one of these typed errors, never a crash.
    """
    from emergentflow.llm import call as llm_call

    messages = build_consult_messages(graph, persona_slug=persona_slug, node_ids=node_ids, ask=ask)
    response = llm_call(
        messages,
        provider=provider,
        model=model,
        client=client,
        response_format="json",
        response_schema=_SET_PARAMS_RESPONSE_SCHEMA,
    )
    if response.data is None or not isinstance(response.data.get("set_params"), dict):
        raise ConsultError(
            "consult response did not contain a usable 'set_params' object "
            f"(got: {response.data!r})"
        )
    return GraphMutation(
        base_version=base_version,
        set_params=response.data["set_params"],
        description=f"Consult ({persona_slug}): {ask}",
        author=persona_slug,
    )
