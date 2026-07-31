"""
emergentflow.nodes.examples.composite
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``layout.composite`` — the FUNCTIONAL-paradigm container node for
"Extract to composite" (issue #117 stage 3).

Unlike ``layout.group`` (a purely visual, zero-port container), a composite node owns a real
``subgraph`` whose nodes are excluded from the outer graph's own topological walk and instead
compiled/executed as a unit. Its ports are dynamic per instance: whoever builds a composite
node (the canvas's "Extract to composite" action) populates ``Node.ports`` directly rather than
through this class's declared (empty) ``ports`` spec, the same way ``Node.subgraph`` is opaque
per-instance data. `Graph`'s structural validator has no opinion on a node's ports matching its
registered type's declared spec, so this is a supported shape, not a workaround.

A composite's IN ports correspond, in a fixed deterministic order, to its subgraph's dangling
IN ports (ports with no *internal* upstream source); its OUT ports correspond to its subgraph's
OUT ports with no internal consumer ("exposed" outputs). Both ``emergentflow.codegen.compiler``
and ``emergentflow.codegen.executor`` special-case this node type inside their FUNCTIONAL
per-node walk — mirroring how ``compiler.py`` already special-cases ``notes.markdown`` — so a
composite is recursively compiled/executed rather than dispatched through the generic
``NodeDefinition.codegen``/``execute`` methods below, which exist only to satisfy the abstract
base class and are never actually invoked (mirroring ``nn.module``'s container node, which is
never called via the same seam because whole-graph declarative handling intercepts it first).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from emergentflow.ir.node import Node

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class Composite(NodeDefinition):
    """A FUNCTIONAL container node that owns a subgraph, extracted from a selection."""

    type = "layout.composite"
    version = 1
    family = "layout"
    label = "Composite"
    category = "Organization"
    description = "A reusable container owning an extracted subgraph."

    ports = []
    params = [
        ParamSpec(
            name="label",
            type_token="str",
            default="Composite",
            required=False,
            label="Label",
            help="Display name for this composite.",
        ),
    ]

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        raise NotImplementedError(
            "layout.composite is compiled recursively by "
            "emergentflow.codegen.compiler's per-node walk, never via generic per-node "
            "codegen."
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError(
            "layout.composite is executed recursively by "
            "emergentflow.codegen.executor's per-node walk, never via generic per-node "
            "execute."
        )
