"""
emergentflow.nodes.examples.llm_call
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``llm.call`` — the core Epic 9 node (0 required IN ports,
1 OUT port).

Both ``execute`` and ``codegen`` route through the same
``emergentflow.llm.call`` wrapper via the ``ef.llm.call`` alias, so the two
paths are equivalent by construction (ADR 0002) -- the sklearn-adapter trick
(ADR 0016) applied to the LLM call. This node sets ``requires_client = True``
(ADR 0017): the injected ``LLMClient`` is threaded in by
``emergentflow.codegen.executor.execute`` / the compiled module's ``main()``,
never constructed here.

``messages`` is a literal param (a JSON list of ``{role, content}`` dicts) in
this version. A later task adds an optional ``prompt`` IN port
(``PromptSpec``, from ``ef.llm.prompt``) that supersedes it when wired.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.llm import call as llm_call
from emergentflow.llm.protocol import LLMClient

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class LlmCall(NodeDefinition):
    """Run one LLM completion call (text or structured/JSON output)."""

    type = "llm.call"
    version = 2
    family = "llm"
    label = "LLM Call"
    category = "LLM"
    description = (
        "Run one completion call against a provider through the unified gateway. "
        "Use for a single completion call once you already have rendered messages."
    )
    requires_client = True
    cacheable = False  # non-deterministic network call; never cache-serve a stale result.

    ports = [
        PortSpec(
            name="response",
            direction=Direction.OUT,
            data_type="LLMResponse",
            help="The inspectable completion result (text/data, usage, cost, latency).",
        ),
    ]
    params = [
        ParamSpec(
            name="provider",
            type_token="str",
            default="anthropic",
            required=True,
            label="Provider",
            help="Gateway provider key, e.g. 'anthropic', 'openai', 'gemini'.",
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="model",
            type_token="str",
            default="claude-sonnet-5",
            required=True,
            label="Model",
            help="Provider model id, e.g. 'claude-sonnet-5'.",
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="messages",
            type_token="list[dict]",
            default=[],
            label="Messages",
            help="Literal [{role, content}] messages (superseded by wired 'prompt' port later).",
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="temperature",
            type_token="float",
            default=0.0,
            label="Temperature",
            help="Sampling temperature; 0 for reproducible output.",
            hints=ValidationHints(min=0.0, max=2.0, widget="number"),
        ),
        ParamSpec(
            name="max_tokens",
            type_token="int",
            default=None,
            label="Max tokens",
            help="Optional output token cap.",
            hints=ValidationHints(min=1, widget="number"),
        ),
        ParamSpec(
            name="response_format",
            type_token="str",
            default="text",
            label="Response format",
            help="'text' for plain completion, 'json' for structured output.",
            hints=ValidationHints(choices=["text", "json"], widget="select"),
        ),
        ParamSpec(
            name="response_schema",
            type_token="dict",
            default=None,
            label="Response schema",
            help="Optional JSON Schema the parsed 'json' output must satisfy.",
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="llm_connection",
            type_token="str",
            default=None,
            label="LLM connection",
            help=(
                "Name of a registered LLM credential profile (Manage Connections -> LLM "
                "Credentials). Resolves to an env-var name at call time; never a literal "
                "secret. Leave blank to use the provider's conventional default env var."
            ),
            hints=ValidationHints(widget="connection", connection_kind="llm"),
        ),
    ]

    def _args(
        self, node: Node
    ) -> tuple[
        str,
        str,
        list[dict[str, str]],
        float,
        int | None,
        str,
        dict[str, Any] | None,
        str | None,
    ]:
        values = {p.name: p.value for p in node.params}
        provider = cast(str, values.get("provider") or "anthropic")
        model = cast(str, values.get("model") or "claude-sonnet-5")
        messages = cast("list[dict[str, str]]", values.get("messages") or [])
        temperature = cast(float, values.get("temperature", 0.0) or 0.0)
        max_tokens = cast("int | None", values.get("max_tokens"))
        response_format = cast(str, values.get("response_format") or "text")
        response_schema = cast("dict[str, Any] | None", values.get("response_schema"))
        llm_connection = cast("str | None", values.get("llm_connection"))
        return (
            provider,
            model,
            messages,
            temperature,
            max_tokens,
            response_format,
            response_schema,
            llm_connection,
        )

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        (
            provider,
            model,
            messages,
            temperature,
            max_tokens,
            response_format,
            response_schema,
            llm_connection,
        ) = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('response')} = ef.llm.call(\n"
                f"    {messages!r},\n"
                f"    provider={provider!r},\n"
                f"    model={model!r},\n"
                f"    client=client,\n"
                f"    temperature={temperature!r},\n"
                f"    max_tokens={max_tokens!r},\n"
                f"    response_format={response_format!r},\n"
                f"    response_schema={response_schema!r},\n"
                f"    llm_connection={llm_connection!r},\n"
                f")"
            ),
        )

    def execute(
        self, node: Node, inputs: dict[str, Any], *, client: LLMClient | None = None
    ) -> dict[str, Any]:
        (
            provider,
            model,
            messages,
            temperature,
            max_tokens,
            response_format,
            response_schema,
            llm_connection,
        ) = self._args(node)
        response = llm_call(
            messages,
            provider=provider,
            model=model,
            client=client,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
            response_schema=response_schema,
            llm_connection=llm_connection,
        )
        return {"response": response}
