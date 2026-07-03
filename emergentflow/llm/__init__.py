"""
emergentflow.llm
~~~~~~~~~~~~~~~~
LLM-call seam (Epic 9, ADR 0017).

Nodes never talk to a provider directly; they build a pure, JSON-native
``LLMRequest`` and hand it to an injected ``LLMClient`` (see
:mod:`emergentflow.llm.protocol`). This keeps ``execute``/``compile_to_code``
pure per ADR 0002 while still letting real LLM calls happen at the edge.

``call()`` is the thin public wrapper every ``ef.llm.call`` node delegates to
(mirroring how ``ef.stats.anova`` wraps statsmodels): it builds the request,
delegates the one effectful step to the injected client, fills in the
authoritative cost figure, and -- for structured (``"json"``) output --
validates the parsed result against an optional JSON Schema.

``prompt()`` is the equally thin wrapper every ``ef.llm.prompt`` node
delegates to: pure ``{{var}}`` template rendering (see
:mod:`emergentflow.llm.templating`), producing the ``PromptSpec`` that feeds
``call()``'s ``messages``.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from emergentflow.api import public_op
from emergentflow.llm.aggregate import summarize_run
from emergentflow.llm.pricing import compute_cost
from emergentflow.llm.protocol import LLMClient, LLMRequest, LLMResponse
from emergentflow.llm.templating import PromptSpec, PromptVariableError, render_prompt

__all__ = [
    "call",
    "MissingClientError",
    "StructuredOutputValidationError",
    "prompt",
    "PromptSpec",
    "PromptVariableError",
    "summarize_run",
]


class MissingClientError(RuntimeError):
    """Raised by `call()` when no `LLMClient` was injected (ADR 0017).

    This is the single place that enforces "an LLM node needs a client" --
    both `execute()` and a compiled module's `main()` route through `call()`,
    so they raise identically for identical reasons (ADR 0002).
    """


class StructuredOutputValidationError(ValueError):
    """Raised by `call()` when structured output fails schema validation.

    The message lists every violation found by the constrained JSON-Schema
    subset checker (see `_validate_json_schema`).
    """


@public_op(name="ef.llm.call")
def call(
    messages: list[dict[str, str]] | tuple[dict[str, str], ...],
    *,
    provider: str,
    model: str,
    client: LLMClient | None,
    temperature: float = 0.0,
    max_tokens: int | None = None,
    response_format: str = "text",
    response_schema: dict[str, Any] | None = None,
    api_key_env: str | None = None,
) -> LLMResponse:
    """Run one LLM completion call through *client* and return an `LLMResponse`.

    Pure aside from the single delegated effect: `client.complete(request)`.
    See the module docstring for the full sequence of steps.

    Raises
    ------
    MissingClientError
        If *client* is ``None``.
    ValueError
        If *response_format* is not ``"text"`` or ``"json"``.
    StructuredOutputValidationError
        If *response_format* is ``"json"``, *response_schema* is given, and
        the parsed `response.data` fails validation against it.
    """
    if client is None:
        raise MissingClientError(
            "ef.llm.call requires an injected LLMClient; pass client=... to "
            "execute(graph, client=...) or to the compiled module's main(client=...)."
        )
    if response_format not in ("text", "json"):
        raise ValueError(f"response_format must be 'text' or 'json'; got {response_format!r}")

    request = LLMRequest(
        provider=provider,
        model=model,
        messages=tuple(dict(m) for m in messages),
        temperature=temperature,
        max_tokens=max_tokens,
        response_format=response_format,
        response_schema=response_schema,
        api_key_env=api_key_env,
    )
    response = client.complete(request)

    # Cost is always (re)computed here -- the one authoritative place -- so
    # neither client backend needs its own pricing logic (ReplayClient
    # replays whatever cost was baked into the fixture at record time, which
    # was itself computed by this same function; GatewayClient always
    # returns a 0.0 placeholder by design).
    response = dataclasses.replace(response, cost_usd=compute_cost(response.model, response.usage))

    if response_format == "json" and response_schema is not None and response.data is not None:
        errors = _validate_json_schema(response.data, response_schema)
        if errors:
            raise StructuredOutputValidationError(
                "Structured output failed schema validation: " + "; ".join(errors)
            )

    return response


@public_op(name="ef.llm.prompt")
def prompt(system: str, user: str, variables: dict[str, object]) -> PromptSpec:
    """Render *system*/*user* templates against *variables* (the ``ef.llm.prompt`` node wrapper).

    Thin pass-through to `emergentflow.llm.templating.render_prompt`, kept as
    a separate top-level name so a node's ``codegen`` can emit
    ``ef.llm.prompt(...)``, mirroring ``ef.llm.call(...)``.

    Raises
    ------
    PromptVariableError
        See `render_prompt`.
    """
    return render_prompt(system, user, variables)


_TYPE_MAP: dict[str, type | tuple[type, ...]] = {
    "object": dict,
    "array": list,
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
    "null": type(None),
}


def _matches_type(data: Any, schema_type: str) -> bool:
    """Return whether *data*'s Python type matches JSON-Schema *schema_type*."""
    expected = _TYPE_MAP.get(schema_type)
    if expected is None:
        return True  # unknown type keyword -- don't enforce
    if schema_type in ("integer", "number") and isinstance(data, bool):
        return False  # bool is a subclass of int; exclude explicitly
    return isinstance(data, expected)


def _validate_json_schema(data: Any, schema: dict[str, Any], *, path: str = "$") -> list[str]:
    """Validate *data* against a small structural subset of JSON Schema.

    Supports `type` (object/array/string/number/integer/boolean/null),
    `properties`, `required`, and `items` -- enough for typical structured-
    output schemas without pulling in a JSON-Schema library as a hard
    dependency (mirrors the constrained-templating choice in Epic 9 Story 3).
    Unsupported schema keywords are silently ignored, not enforced.

    Returns a list of human-readable violation messages (empty if valid).
    """
    errors: list[str] = []
    schema_type = schema.get("type")
    if schema_type is not None and not _matches_type(data, schema_type):
        errors.append(f"{path}: expected type {schema_type!r}, got {type(data).__name__}")
        return errors  # further checks would be meaningless on a type mismatch

    if (schema_type == "object" or (schema_type is None and isinstance(data, dict))) and isinstance(
        data, dict
    ):
        for req in schema.get("required", []):
            if req not in data:
                errors.append(f"{path}: missing required property {req!r}")
        properties = schema.get("properties", {})
        for key, sub_schema in properties.items():
            if key in data:
                sub_path = f"{path}.{key}"
                errors.extend(_validate_json_schema(data[key], sub_schema, path=sub_path))

    if (schema_type == "array" or (schema_type is None and isinstance(data, list))) and isinstance(
        data, list
    ):
        item_schema = schema.get("items")
        if item_schema is not None:
            for i, item in enumerate(data):
                errors.extend(_validate_json_schema(item, item_schema, path=f"{path}[{i}]"))

    return errors
