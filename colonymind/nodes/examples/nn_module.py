"""
colonymind.nodes.examples.nn_module
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``nn.module`` — the *declarative* container node.

Unlike ``nn.linear`` / ``nn.relu`` (which are leaf layers contributing a
constructor expression), ``nn.module`` is the CONTAINER: it owns a
``subgraph`` of layer nodes and is compiled/executed only by the whole-graph
declarative paths (``colonymind.codegen.declarative.compile_declarative`` and
the matching declarative executor), never via per-node ``codegen``/``execute``.
Both methods raise ``NotImplementedError`` pointing callers at those
whole-graph paths.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from colonymind.ir.common import Paradigm
from colonymind.ir.node import Node

from ..contract import CodeFragment, NodeDefinition
from ..registry import register

if TYPE_CHECKING:
    from colonymind.codegen.context import CodegenContext


@register
class NnModule(NodeDefinition):
    """A declarative container node that owns a subgraph of layers."""

    type = "nn.module"
    version = 1
    family = "nn"
    label = "Module"
    category = "Neural Network"
    description = "An nn.Module that owns a subgraph of layers."
    paradigm = Paradigm.DECLARATIVE

    ports = []
    params = []

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        raise NotImplementedError(
            "nn.module is a declarative container; it is compiled by "
            "colonymind.codegen.declarative.compile_declarative, not via per-node "
            "codegen."
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError(
            "nn.module is a declarative container; it is run by the whole-graph "
            "declarative executor, not via per-node execute."
        )
