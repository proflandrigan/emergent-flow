"""
emergentflow.nodes.examples.llm_prompt
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``llm.prompt`` — the "write prompts" half of the Prompt Lab
loop (Epic 9 Story 3). 1 required IN port, 1 OUT port.

Both ``execute`` and ``codegen`` route through the same
``emergentflow.llm.prompt`` wrapper via the ``ef.llm.prompt`` alias, so the
two paths are equivalent by construction (ADR 0002). Unlike ``llm.call``,
this node is pure -- template substitution touches no network and needs no
injected client (``requires_client`` stays at its default ``False``), and it
is deterministic, so it stays cacheable (``cacheable`` stays at its default
``True``).

The ``variables`` param is a declared name -> type-token mapping (documentary
metadata for the canvas/config UI only, per Epic 9 Story 3's param list); the
actual missing/extra-variable validation happens inside
``emergentflow.llm.templating.render_prompt`` against the *wired* IN port
binding at execute/compile time (the shared validation gate the whole
codebase already uses for other errors), not against this param.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.llm import prompt as llm_prompt

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class LlmPrompt(NodeDefinition):
    """Render a system/user prompt template against a variable binding."""

    type = "llm.prompt"
    version = 1
    family = "llm"
    label = "LLM Prompt"
    category = "LLM"
    description = "Render a system + user prompt template with {{variable}} substitution."

    ports = [
        PortSpec(
            name="variables",
            direction=Direction.IN,
            data_type="VariableBinding",
            help="One row of variable-name -> value bindings used to render the templates.",
        ),
        PortSpec(
            name="prompt",
            direction=Direction.OUT,
            data_type="PromptSpec",
            help="The rendered {system, user, messages} prompt, ready for ef.llm.call.",
        ),
    ]
    params = [
        ParamSpec(
            name="system",
            type_token="str",
            default="",
            required=True,
            label="System template",
            help="System-message template, e.g. 'You are a {{persona}} assistant.'",
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="user",
            type_token="str",
            default="",
            required=True,
            label="User template",
            help="User-message template, e.g. 'Answer this: {{question}}'",
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="variables",
            type_token="dict[str,str]",
            default={},
            label="Declared variables",
            help="Documentary name -> type-token map shown in the canvas (e.g. {'q': 'str'}).",
            hints=ValidationHints(widget="text"),
        ),
    ]

    def _args(self, node: Node) -> tuple[str, str]:
        values = {p.name: p.value for p in node.params}
        system = cast(str, values.get("system") or "")
        user = cast(str, values.get("user") or "")
        return system, user

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        system, user = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('prompt')} = ef.llm.prompt(\n"
                f"    {system!r},\n"
                f"    {user!r},\n"
                f"    {ctx.in_var('variables')},\n"
                f")"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        system, user = self._args(node)
        prompt_spec = llm_prompt(system, user, inputs["variables"])
        return {"prompt": prompt_spec}
