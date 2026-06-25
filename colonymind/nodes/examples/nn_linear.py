"""
colonymind.nodes.examples.nn_linear
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``nn.linear`` — a *declarative* layer node (1 in, 1 out).

Unlike the functional reference nodes, this is a DECLARATIVE layer (ADR 0003):
it does not emit a full statement. ``codegen`` returns the bare constructor
EXPRESSION (e.g. ``nn.Linear(128, 64)``); the whole-graph declarative
generator (Epic 2, Story 8) binds that expression to ``self.<attr> = <expr>``
in ``__init__`` and calls it in ``forward``. ``execute`` likewise builds and
returns the layer object itself rather than running a forward pass — the
whole-graph declarative executor composes the layers.

``torch`` is not a project dependency, so the import is LAZY (inside
``execute``) — importing this module never requires torch.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from colonymind.ir.common import Direction, Paradigm
from colonymind.ir.node import Node

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec

if TYPE_CHECKING:
    from colonymind.codegen.context import CodegenContext


@register
class NnLinear(NodeDefinition):
    """A fully-connected (``nn.Linear``) layer."""

    type = "nn.linear"
    version = 1
    family = "nn"
    label = "Linear"
    category = "Neural Network"
    description = "A linear (fully-connected) layer."
    paradigm = Paradigm.DECLARATIVE

    ports = [
        PortSpec(
            name="x",
            direction=Direction.IN,
            data_type="Tensor",
            help="The input tensor to the linear layer.",
        ),
        PortSpec(
            name="out",
            direction=Direction.OUT,
            data_type="Tensor",
            help="The linear layer's output tensor.",
        ),
    ]
    params = [
        ParamSpec(
            name="in_features",
            type_token="int",
            required=True,
            label="In features",
            help="Size of each input sample.",
        ),
        ParamSpec(
            name="out_features",
            type_token="int",
            required=True,
            label="Out features",
            help="Size of each output sample.",
        ),
    ]

    def _args(self, node: Node) -> tuple[int, int]:
        values = {p.name: p.value for p in node.params}
        in_features = values.get("in_features")
        out_features = values.get("out_features")
        return cast(int, in_features), cast(int, out_features)

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        in_features, out_features = self._args(node)
        return CodeFragment(
            imports=["import torch.nn as nn"],
            body=f"nn.Linear({in_features}, {out_features})",
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        in_features, out_features = self._args(node)
        import torch.nn as nn

        return {"out": nn.Linear(in_features, out_features)}
