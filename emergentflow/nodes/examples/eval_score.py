"""
emergentflow.nodes.examples.eval_score
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``eval.score`` — deterministic scoring of an eval-run
compare table (issue #93 part 2). 1 required IN port, 2 OUT ports.

Both ``execute`` and ``codegen`` route through the same
``emergentflow.eval.score``/``summarize_scores`` wrappers via the
``ef.eval.score``/``ef.eval.summarize_scores`` aliases, so the two paths are
equivalent by construction (ADR 0002). Unlike ``eval.run``, this node needs
no injected client -- scoring is a pure, deterministic function of its
inputs -- so it does not set ``requires_client``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.eval import score as eval_score
from emergentflow.eval import summarize_scores as eval_summarize_scores
from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class EvalScore(NodeDefinition):
    """Score an eval-run compare table with deterministic scorers and roll up metrics."""

    type = "eval.score"
    version = 1
    family = "eval"
    label = "Eval Score"
    category = "LLM"
    description = (
        "Grade an eval-run compare table with deterministic scorers and summarize per variant."
    )

    ports = [
        PortSpec(
            name="results",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The eval-run compare table (ef.eval.run's output) to score.",
        ),
        PortSpec(
            name="scored",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="results, with one score_<name> column added per scorer.",
        ),
        PortSpec(
            name="metrics",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="One row per variant: n, plus mean_<name> for every score_<name> column.",
        ),
    ]
    params = [
        ParamSpec(
            name="scorers",
            type_token="list[dict]",
            default=[],
            required=True,
            label="Scorers",
            help=(
                "Scorer specs, e.g. "
                "[{'name': 'exact', 'kind': 'exact_match', 'reference_column': 'expected'}]."
            ),
            hints=ValidationHints(widget="text"),
        ),
    ]

    def _scorers(self, node: Node) -> list[dict[str, Any]]:
        values = {p.name: p.value for p in node.params}
        return cast("list[dict[str, Any]]", values.get("scorers") or [])

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        scorers = self._scorers(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('scored')} = ef.eval.score({ctx.in_var('results')}, {scorers!r})\n"
                f"{ctx.out_var('metrics')} = ef.eval.summarize_scores({ctx.out_var('scored')})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        scorers = self._scorers(node)
        scored = eval_score(inputs["results"], scorers)
        metrics = eval_summarize_scores(scored)
        return {"scored": scored, "metrics": metrics}
