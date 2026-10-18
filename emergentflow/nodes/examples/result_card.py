"""
emergentflow.nodes.examples.result_card
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``reports.result_card`` -- a notebook-style presentation card.

The card is presentation-only: it accepts any number of upstream results on its
``results`` port and carries an ordered list of blocks (markdown prose and
references to upstream outputs) in ``blocks_json``. ``codegen`` always emits an
empty body and ``execute`` always returns ``{}``, so ADR 0002 is satisfied
trivially (empty vs. empty). The UI renders the blocks live from the execute
cache; nothing about the card flows into compiled code.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from emergentflow.ir.common import Cardinality, Direction
from emergentflow.ir.node import Node

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class ResultCard(NodeDefinition):
    """A notebook-style card showing upstream results and prose on the canvas."""

    type = "reports.result_card"
    version = 1
    family = "reports"
    label = "Result Card"
    category = "Reporting"
    description = (
        "A notebook-style card that shows upstream results (tables, charts, metrics) "
        "and prose directly on the canvas."
    )

    ports = [
        PortSpec(
            name="results",
            label="Results",
            direction=Direction.IN,
            data_type="any",
            cardinality=Cardinality.MANY,
            required=False,
            help="Upstream outputs shown on the card.",
        ),
    ]
    params = [
        ParamSpec(
            name="title",
            type_token="str",
            default="Results",
            required=False,
            label="Title",
            help="Card heading.",
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="blocks_json",
            type_token="str",
            default="[]",
            required=False,
            label="Blocks",
            help=(
                "JSON list of ordered blocks. Each block is "
                '{"kind": "markdown", "text": str} or '
                '{"kind": "result", "source": "<node_id>:<out_port_name>", "caption": str}.'
            ),
        ),
        ParamSpec(
            name="width",
            type_token="int",
            default=480,
            required=False,
            label="Width",
            help="Card width in px.",
        ),
    ]

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        return CodeFragment(imports=[], body="")

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        return {}
