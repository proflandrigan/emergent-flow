"""
emergentflow.nodes.examples.recommend_load_model
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``recommend.load_model`` — a source node (0 in, 1 out).

Loads a fitted recommender from disk via ``ef.recommend.load_model`` and
returns it as a ``Recommender``. ``execute`` calls ``emergentflow.recommend.load_model``
directly and the code emitted by ``codegen`` calls the same wrapper via the
``ef.`` alias, so the two paths are equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.recommend import load_model

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class RecommendLoadModel(NodeDefinition):
    """Load a fitted recommender from disk."""

    type = "recommend.load_model"
    version = 1
    family = "recommend"
    label = "Load Recommender"
    category = "Recommenders"
    description = "Load a fitted recommender model from a saved artifact on disk."

    ports = [
        PortSpec(
            name="recommender",
            direction=Direction.OUT,
            data_type="Recommender",
            help="The loaded fitted recommender model.",
        ),
    ]
    params = [
        ParamSpec(
            name="path",
            type_token="str",
            required=True,
            label="File path",
            help="Path to the saved model file (e.g. 'models/popularity_v3.joblib').",
            hints=ValidationHints(widget="filepath"),
        ),
    ]

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        values = {p.name: p.value for p in node.params}
        path = values.get("path", "")
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(f"{ctx.out_var('recommender')} = ef.recommend.load_model({path!r})"),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        path = cast(str, values.get("path", ""))
        return {"recommender": load_model(path)}
