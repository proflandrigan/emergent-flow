"""
emergentflow.nodes.examples.eval_run
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``eval.run`` — the compare/eval-run harness node (Epic 9
Story 5). 1 required IN port, 1 OUT port.

Both ``execute`` and ``codegen`` route through the same
``emergentflow.eval.run`` wrapper via the ``ef.eval.run`` alias, so the two
paths are equivalent by construction (ADR 0002). Like ``llm.call``, this node
sets ``requires_client = True`` (ADR 0017) -- the injected ``LLMClient`` is
threaded in by ``emergentflow.codegen.executor.execute`` / the compiled
module's ``main()`` -- and it is not cacheable (network calls, non-deterministic).

The ``dataset`` IN port carries a ``DataFrame`` (consistent with every other
tabular port in the catalog); ``execute``/``codegen`` convert it to the
``list[dict]`` of variable-binding rows ``emergentflow.eval.run.run()``
expects via ``to_dict(orient="records")``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.eval import run as eval_run
from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.llm.protocol import LLMClient

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class EvalRun(NodeDefinition):
    """Run a prompt template over a dataset x variant matrix, producing a compare table."""

    type = "eval.run"
    version = 1
    family = "eval"
    label = "Eval Run"
    category = "LLM"
    description = "Run one prompt over N inputs x M model variants for side-by-side compare."
    requires_client = True
    cacheable = False  # non-deterministic network calls; never cache-serve a stale result.

    ports = [
        PortSpec(
            name="dataset",
            direction=Direction.IN,
            data_type="DataFrame",
            help="One row per variable-binding to render the prompt template against.",
        ),
        PortSpec(
            name="results",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="Tidy compare table: one row per (input_row, variant).",
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
            name="variants",
            type_token="list[dict]",
            default=[],
            required=True,
            label="Variants",
            help="Model variants, e.g. [{'provider': 'anthropic', 'model': 'claude-sonnet-5'}].",
            hints=ValidationHints(widget="text"),
        ),
    ]

    def _args(self, node: Node) -> tuple[str, str, list[dict[str, Any]]]:
        values = {p.name: p.value for p in node.params}
        system = cast(str, values.get("system") or "")
        user = cast(str, values.get("user") or "")
        variants = cast("list[dict[str, Any]]", values.get("variants") or [])
        return system, user, variants

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        system, user, variants = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('results')} = ef.eval.run(\n"
                f"    {system!r},\n"
                f"    {user!r},\n"
                f"    {ctx.in_var('dataset')}.to_dict(orient='records'),\n"
                f"    {variants!r},\n"
                f"    client=client,\n"
                f")"
            ),
        )

    def execute(
        self, node: Node, inputs: dict[str, Any], *, client: LLMClient | None = None
    ) -> dict[str, Any]:
        system, user, variants = self._args(node)
        dataset = inputs["dataset"].to_dict(orient="records")
        results = eval_run(system, user, dataset, variants, client=client)
        return {"results": results}
