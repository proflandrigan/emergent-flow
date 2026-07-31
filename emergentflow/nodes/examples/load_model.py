"""
emergentflow.nodes.examples.load_model
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``ml.load_model`` — a source node (0 in, 1 out).

Loads a fitted model or transformer from disk via ``ef.ml.load_model`` and
returns it as a ``Model``. ``execute`` calls ``emergentflow.ml.load_model``
directly and the code emitted by ``codegen`` calls the same wrapper via the
``ef.`` alias, so the two paths are equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.ml import load_model

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class LoadModel(NodeDefinition):
    """Load a fitted model from disk."""

    type = "ml.load_model"
    version = 1
    family = "ml"
    label = "Load Model"
    category = "Machine Learning"
    description = "Load a fitted model or transformer from a saved artifact on disk."

    ports = [
        PortSpec(
            name="model",
            direction=Direction.OUT,
            data_type="Model",
            help="The loaded fitted model or transformer.",
        ),
    ]
    params = [
        ParamSpec(
            name="path",
            type_token="str",
            required=True,
            label="File path",
            help="Path to the saved model file (e.g. 'models/churn_rf_v3.joblib').",
            hints=ValidationHints(widget="filepath"),
        ),
    ]

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        values = {p.name: p.value for p in node.params}
        path = values.get("path", "")
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(f"{ctx.out_var('model')} = ef.ml.load_model({path!r})"),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        path = cast(str, values.get("path", ""))
        return {"model": load_model(path)}
