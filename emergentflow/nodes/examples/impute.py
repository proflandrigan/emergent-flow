"""
emergentflow.nodes.examples.impute
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``clean.impute_missing`` — a *transform* node (1 in, 1 out).

Real, scikit-learn-backed imputer (Epic 1, Story 8). ``execute`` calls
``emergentflow.clean.impute_missing`` directly and the code emitted by
``codegen`` calls the same wrapper via the ``ef.`` alias, so the two paths are
equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.clean import STRATEGIES, impute_missing
from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class ImputeMissing(NodeDefinition):
    """Impute missing values in a DataFrame column-wise."""

    type = "clean.impute_missing"
    version = 2
    family = "clean"
    label = "Impute Missing"
    category = "Transform"
    description = "Fill missing values in selected columns using a chosen strategy."

    ports = [
        PortSpec(
            name="frame",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame whose missing cells should be filled.",
        ),
        PortSpec(
            name="frame",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="The DataFrame with missing cells imputed.",
        ),
    ]
    params = [
        ParamSpec(
            name="strategy",
            type_token="str",
            default="mean",
            label="Strategy",
            help="How to compute each column's fill value.",
            hints=ValidationHints(choices=list(STRATEGIES), widget="select"),
        ),
        ParamSpec(
            name="columns",
            type_token="list[str]",
            default=None,
            label="Columns",
            help="Columns to impute; empty/unset imputes every column.",
            hints=ValidationHints(widget="text"),
        ),
    ]

    def _args(self, node: Node) -> tuple[str, list[str] | None]:
        values = {p.name: p.value for p in node.params}
        strategy = values.get("strategy", "mean") or "mean"
        columns = values.get("columns")
        return cast(str, strategy), cast("list[str] | None", columns)

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        strategy, columns = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('frame')} = ef.clean.impute_missing("
                f"{ctx.in_var('frame')}, strategy={strategy!r}, columns={columns!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        strategy, columns = self._args(node)
        return {"frame": impute_missing(inputs["frame"], strategy=strategy, columns=columns)}
