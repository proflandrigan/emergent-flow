"""
emergentflow.nodes.examples.eval_judge
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``eval.judge`` — LLM-as-judge scoring of an eval-run
compare table (issue #93 part 2). 1 required IN port, 1 OUT port.

Both ``execute`` and ``codegen`` route through the same
``emergentflow.eval.judge`` wrapper via the ``ef.eval.judge`` alias, so the
two paths are equivalent by construction (ADR 0002). Like ``eval.run``,
this node sets ``requires_client = True`` (ADR 0017) -- the injected
``LLMClient`` is threaded in by ``emergentflow.codegen.executor.execute`` /
the compiled module's ``main()`` -- and it is not cacheable (network calls,
non-deterministic).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.eval import judge as eval_judge
from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.llm.protocol import LLMClient

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class EvalJudge(NodeDefinition):
    """Grade an eval-run compare table's output with an LLM judge against a rubric."""

    type = "eval.judge"
    version = 1
    family = "eval"
    label = "Eval Judge"
    category = "LLM"
    description = "LLM-as-judge: grade an eval-run compare table's output column against a rubric."
    requires_client = True
    cacheable = False  # non-deterministic network calls; never cache-serve a stale result.

    ports = [
        PortSpec(
            name="results",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The eval-run compare table (ef.eval.run's output) to judge.",
        ),
        PortSpec(
            name="judged",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="results, with judge_score and judge_rationale columns added.",
        ),
    ]
    params = [
        ParamSpec(
            name="rubric",
            type_token="str",
            default="",
            required=True,
            label="Rubric",
            help="Free-text grading criteria the judge model scores each row's output against.",
            hints=ValidationHints(widget="markdown"),
        ),
        ParamSpec(
            name="judge_provider",
            type_token="str",
            default="anthropic",
            required=True,
            label="Judge provider",
            help="Gateway provider key for the judge model, e.g. 'anthropic'.",
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="judge_model",
            type_token="str",
            default="claude-sonnet-5",
            required=True,
            label="Judge model",
            help="Provider model id used as the judge, e.g. 'claude-sonnet-5'.",
            hints=ValidationHints(widget="text"),
        ),
    ]

    def _args(self, node: Node) -> tuple[str, str, str]:
        values = {p.name: p.value for p in node.params}
        rubric = cast(str, values.get("rubric") or "")
        judge_provider = cast(str, values.get("judge_provider") or "anthropic")
        judge_model = cast(str, values.get("judge_model") or "claude-sonnet-5")
        return rubric, judge_provider, judge_model

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        rubric, judge_provider, judge_model = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('judged')} = ef.eval.judge(\n"
                f"    {ctx.in_var('results')},\n"
                f"    {rubric!r},\n"
                f"    judge_provider={judge_provider!r},\n"
                f"    judge_model={judge_model!r},\n"
                f"    client=client,\n"
                f")"
            ),
        )

    def execute(
        self, node: Node, inputs: dict[str, Any], *, client: LLMClient | None = None
    ) -> dict[str, Any]:
        rubric, judge_provider, judge_model = self._args(node)
        judged = eval_judge(
            inputs["results"],
            rubric,
            judge_provider=judge_provider,
            judge_model=judge_model,
            client=client,
        )
        return {"judged": judged}
