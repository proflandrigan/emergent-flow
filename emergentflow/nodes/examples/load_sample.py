"""
emergentflow.nodes.examples.load_sample
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``data.load_sample`` — a *source* node (0 inputs, 1 output).

Real, bundled, scikit-learn-backed sample dataset loader (Epic 6, Story 3). ``execute`` calls
``emergentflow.data.load_sample`` directly and the code emitted by ``codegen`` calls the
same wrapper via the ``ef.`` alias, so the two paths are equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.data import SAMPLE_DATASETS, load_sample
from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class LoadSample(NodeDefinition):
    """Load a small bundled sample dataset (zero filesystem setup)."""

    type = "data.load_sample"
    version = 1
    family = "data"
    label = "Load Sample"
    category = "Ingest"
    description = "Load a small bundled sample dataset (zero filesystem setup)."

    ports = [
        PortSpec(
            name="frame",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="The loaded data as a pandas DataFrame.",
        ),
    ]
    params = [
        ParamSpec(
            name="name",
            type_token="str",
            default="iris",
            label="Dataset",
            help="Which bundled sample dataset to load.",
            hints=ValidationHints(choices=list(SAMPLE_DATASETS), widget="select"),
        ),
    ]

    def _args(self, node: Node) -> str:
        values = {p.name: p.value for p in node.params}
        name = values.get("name", "iris")
        if name is None:
            name = "iris"
        return cast(str, name)

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        name = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=f"{ctx.out_var('frame')} = ef.data.load_sample(name={name!r})",
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        name = self._args(node)
        return {"frame": load_sample(name=name)}
