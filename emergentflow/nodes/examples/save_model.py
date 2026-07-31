"""
emergentflow.nodes.examples.save_model
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``ml.save_model`` — a terminal node (1 in, 1 out).

Persists a fitted model or transformer to disk via ``ef.ml.save_model`` and
returns an ``ArtifactRef``. ``execute`` calls ``emergentflow.ml.save_model``
directly and the code emitted by ``codegen`` calls the same wrapper via the
``ef.`` alias, so the two paths are equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.ml import save_model

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class SaveModel(NodeDefinition):
    """Save a fitted model to disk."""

    type = "ml.save_model"
    version = 1
    family = "ml"
    label = "Save Model"
    category = "Machine Learning"
    description = "Save a fitted model or transformer to disk as a reusable artifact."

    ports = [
        PortSpec(
            name="model",
            direction=Direction.IN,
            data_type="Model",
            help="The fitted model or transformer to save.",
        ),
        PortSpec(
            name="ref",
            direction=Direction.OUT,
            data_type="ArtifactRef",
            help="A reference to the saved artifact on disk.",
        ),
    ]
    params = [
        ParamSpec(
            name="path",
            type_token="str",
            required=True,
            label="File path",
            help="Destination file path (e.g. 'models/churn_rf_v3.joblib').",
            hints=ValidationHints(widget="filepath"),
        ),
    ]

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        values = {p.name: p.value for p in node.params}
        path = values.get("path", "")
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(f"{ctx.out_var('ref')} = ef.ml.save_model({ctx.in_var('model')}, path={path!r})"),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        path = cast(str, values.get("path", ""))
        return {"ref": save_model(inputs["model"], path=path)}
