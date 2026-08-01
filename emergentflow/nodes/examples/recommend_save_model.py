"""
emergentflow.nodes.examples.recommend_save_model
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``recommend.save_model`` — persists a recommender (1 in, 1 out).

Persists a fitted recommender to disk via ``ef.recommend.save_model`` and
returns an ``ArtifactRef``. ``execute`` calls ``emergentflow.recommend.save_model``
directly and the code emitted by ``codegen`` calls the same wrapper via the
``ef.`` alias, so the two paths are equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.recommend import save_model

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class RecommendSaveModel(NodeDefinition):
    """Save a fitted recommender to disk."""

    type = "recommend.save_model"
    version = 1
    family = "recommend"
    label = "Save Recommender"
    category = "Recommenders"
    description = "Save a fitted recommender model to disk as a reusable artifact."

    ports = [
        PortSpec(
            name="recommender",
            direction=Direction.IN,
            data_type="Recommender",
            help="The fitted recommender model to save.",
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
            help="Destination file path (e.g. 'models/popularity_v3.joblib').",
            hints=ValidationHints(widget="filepath"),
        ),
    ]

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        values = {p.name: p.value for p in node.params}
        path = values.get("path", "")
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('ref')} = ef.recommend.save_model("
                f"{ctx.in_var('recommender')}, path={path!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        path = cast(str, values.get("path", ""))
        return {"ref": save_model(inputs["recommender"], path=path)}
