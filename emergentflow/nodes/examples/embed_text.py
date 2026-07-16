"""
emergentflow.nodes.examples.embed_text
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``embed.text`` — embed a text column in a DataFrame.

Both ``execute`` and ``codegen`` route through ``ef.embed.text()``, so the two
paths are equivalent by construction (ADR 0002). This node sets
``requires_client = True`` (ADR 0017) for the API embedding path; the local
sentence-transformers path ignores the client.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.llm.protocol import LLMClient

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class EmbedText(NodeDefinition):
    """Embed a text column using an API provider or local model."""

    type = "embed.text"
    version = 1
    family = "embed"
    label = "Embed Text"
    category = "Embeddings"
    description = (
        "Embed a text column in a DataFrame using an API provider "
        "(OpenAI, Anthropic, Gemini, etc.) or a local sentence-transformers model."
    )
    requires_client = True
    cacheable = False

    ports = [
        PortSpec(
            name="data",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="Input DataFrame containing the text column to embed.",
        ),
        PortSpec(
            name="data",
            label="Embedded Data",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="The input DataFrame augmented with an embedding column.",
        ),
    ]
    params = [
        ParamSpec(
            name="column",
            type_token="str",
            required=True,
            label="Text column",
            help="Name of the column containing text to embed.",
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="backend",
            type_token="str",
            default="api",
            label="Backend",
            help="'api' for provider-hosted models, 'local' for sentence-transformers.",
            hints=ValidationHints(choices=["api", "local"], widget="select"),
        ),
        ParamSpec(
            name="provider",
            type_token="str",
            default="openai",
            label="Provider",
            help="Gateway provider key (API backend only), e.g. 'openai'.",
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="model",
            type_token="str",
            default="text-embedding-3-small",
            label="Model",
            help="Model id (API backend), e.g. 'text-embedding-3-small'.",
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="local_model",
            type_token="str",
            default="all-MiniLM-L6-v2",
            label="Local model",
            help="Sentence-transformers model name (local backend only).",
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="output_column",
            type_token="str",
            default="embedding",
            label="Output column",
            help="Name of the column to add containing embeddings.",
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="llm_connection",
            type_token="str",
            default=None,
            label="LLM connection",
            help=(
                "Name of a registered LLM credential profile "
                "(API backend only). Leave blank for provider default."
            ),
            hints=ValidationHints(widget="connection", connection_kind="llm"),
        ),
    ]

    def _args(self, node: Node) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        return {
            "column": cast(str, values.get("column") or "text"),
            "backend": cast(str, values.get("backend") or "api"),
            "provider": cast(str, values.get("provider") or "openai"),
            "model": cast(str, values.get("model") or "text-embedding-3-small"),
            "local_model": cast(str, values.get("local_model") or "all-MiniLM-L6-v2"),
            "output_column": cast(str, values.get("output_column") or "embedding"),
            "llm_connection": cast("str | None", values.get("llm_connection")),
        }

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        args = self._args(node)
        if args["backend"] == "local":
            return CodeFragment(
                imports=["import emergentflow as ef"],
                body=(
                    f"{ctx.out_var('data')} = ef.embed.text(\n"
                    f"    {ctx.in_var('data')},\n"
                    f"    {args['column']!r},\n"
                    f"    local_model={args['local_model']!r},\n"
                    f"    output_column={args['output_column']!r},\n"
                    f")"
                ),
            )
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('data')} = ef.embed.text(\n"
                f"    {ctx.in_var('data')},\n"
                f"    {args['column']!r},\n"
                f"    provider={args['provider']!r},\n"
                f"    model={args['model']!r},\n"
                f"    client=client,\n"
                f"    output_column={args['output_column']!r},\n"
                f"    llm_connection={args['llm_connection']!r},\n"
                f")"
            ),
        )

    def execute(
        self, node: Node, inputs: dict[str, Any], *, client: LLMClient | None = None
    ) -> dict[str, Any]:
        from emergentflow.embed import text as embed_text

        args = self._args(node)
        if args["backend"] == "local":
            result = embed_text(
                inputs["data"],
                args["column"],
                local_model=args["local_model"],
                output_column=args["output_column"],
            )
        else:
            result = embed_text(
                inputs["data"],
                args["column"],
                provider=args["provider"],
                model=args["model"],
                client=client,
                output_column=args["output_column"],
                llm_connection=args["llm_connection"],
            )
        return {"data": result}
