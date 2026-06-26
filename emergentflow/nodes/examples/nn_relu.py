"""
emergentflow.nodes.examples.nn_relu
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``nn.relu`` — a *declarative* layer node (1 in, 1 out).

Unlike the functional reference nodes, this is a DECLARATIVE layer (ADR 0003):
it does not emit a full statement. ``codegen`` returns the bare constructor
EXPRESSION (``nn.ReLU()``); the whole-graph declarative generator (Epic 2,
Story 8) binds that expression to ``self.<attr> = <expr>`` in ``__init__`` and
calls it in ``forward``. ``execute`` likewise builds and returns the layer
object itself rather than running a forward pass — the whole-graph
declarative executor composes the layers.

``torch`` is not a project dependency, so the import is LAZY (inside
``execute``) — importing this module never requires torch.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from emergentflow.ir.common import Direction, Paradigm
from emergentflow.ir.node import Node

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import PortSpec

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class NnReLU(NodeDefinition):
    """A ``nn.ReLU`` activation layer."""

    type = "nn.relu"
    version = 1
    family = "nn"
    label = "ReLU"
    category = "Neural Network"
    description = "A ReLU activation layer."
    paradigm = Paradigm.DECLARATIVE

    ports = [
        PortSpec(
            name="x",
            direction=Direction.IN,
            data_type="Tensor",
            help="The input tensor to the activation.",
        ),
        PortSpec(
            name="out",
            direction=Direction.OUT,
            data_type="Tensor",
            help="The activation's output tensor.",
        ),
    ]
    params = []

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        return CodeFragment(
            imports=["import torch.nn as nn"],
            body="nn.ReLU()",
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        import torch.nn as nn

        return {"out": nn.ReLU()}
