"""
cm_texttools.nodes
~~~~~~~~~~~~~~~~~~
Out-of-core node plugin for Colony Mind (Epic 1, Story 4).

Defines a single transform node, ``text.reverse``, that reverses an input
string.  The module is dependency-free (standard Python only) and conforms
to the ``NodeDefinition`` contract without decorating with ``@register`` —
the entry point declared in ``pyproject.toml`` under the ``colonymind.nodes``
group is the *only* integration surface; no core change is needed.

ADR-0002: both ``execute`` and the code emitted by ``codegen`` route through
the shared runtime helper ``reverse_text``, so they are equivalent by
construction.
"""

from __future__ import annotations

from typing import Any

from colonymind.ir.common import Direction
from colonymind.ir.node import Node
from colonymind.nodes.contract import CodeFragment, NodeDefinition
from colonymind.nodes.spec import PortSpec


def reverse_text(value: str) -> str:
    """Return *value* with its characters in reverse order (the shared runtime helper).

    Both ``ReverseText.execute`` and the code emitted by ``ReverseText.codegen``
    call this function, so the two execution paths are equivalent by construction
    (ADR-0002).
    """
    return value[::-1]


class ReverseText(NodeDefinition):
    """Reverse a text string (IN ``text`` → OUT ``text``)."""

    type = "text.reverse"
    version = 1
    family = "text"
    label = "Reverse Text"

    ports = [
        PortSpec(name="text", direction=Direction.IN, data_type="Text"),
        PortSpec(name="text", direction=Direction.OUT, data_type="Text"),
    ]
    params = []

    def codegen(self, node: Node) -> CodeFragment:
        return CodeFragment(
            imports=["from cm_texttools.nodes import reverse_text"],
            body="text = reverse_text(text)",
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        return {"text": reverse_text(inputs["text"])}
