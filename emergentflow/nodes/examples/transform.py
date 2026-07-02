"""
emergentflow.nodes.examples.transform
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``ml.transform`` — the apply archetype for a fitted ``Transformer``
(Epic 8, ADR 0016).

Applies a fitted ``Transformer`` (from ``ml.fit_transform``) to a NEW DataFrame via
``transform`` or ``score_samples``, returning a new DataFrame. This is the ``Transformer``-typed
sibling of ``ml.apply_estimator`` (which applies a fitted ``Model`` via ``predict`` /
``score_samples``) — kept as a separate node type because the ``Model``/``Transformer`` type
tokens are declared incompatible (``docs/type-system-spec.md``), so a single shared node cannot
have one IN port that accepts both. ``execute`` calls ``emergentflow.ml.apply_estimator``
directly and the code emitted by ``codegen`` calls the same wrapper via the ``ef.`` alias, so
the two paths are equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.ml import apply_estimator

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class Transform(NodeDefinition):
    """Apply a fitted Transformer to data via transform or score_samples."""

    type = "ml.transform"
    version = 1
    family = "ml"
    label = "Transform"
    category = "Machine Learning"
    description = "Apply a fitted Transformer to data via transform or score_samples."

    ports = [
        PortSpec(
            name="transformer",
            direction=Direction.IN,
            data_type="Transformer",
            help="The fitted transformer to apply.",
        ),
        PortSpec(
            name="frame",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The data to apply the transformer to.",
        ),
        PortSpec(
            name="result",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="Input rows plus the op's output column(s).",
        ),
    ]
    params = [
        ParamSpec(
            name="op",
            type_token="str",
            default="transform",
            label="Operation",
            help="Which operation to apply: transform adds 'component_N' columns, "
            "score_samples adds a 'score' column.",
            hints=ValidationHints(choices=["transform", "score_samples"], widget="select"),
        ),
    ]

    def _op(self, node: Node) -> str:
        values = {p.name: p.value for p in node.params}
        op = values.get("op", "transform") or "transform"
        return cast(str, op)

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        op = self._op(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('result')} = ef.ml.apply_estimator("
                f"{ctx.in_var('transformer')}, {ctx.in_var('frame')}, op={op!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        op = self._op(node)
        return {"result": apply_estimator(inputs["transformer"], inputs["frame"], op=op)}
