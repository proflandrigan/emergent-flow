"""
emergentflow.nodes.examples.deduplicate
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``clean.deduplicate`` — a *transform* node (1 in, 1 out), Epic 16 Story 7.

Drop duplicate rows, optionally keyed on a subset of columns. ``execute`` calls
``emergentflow.clean.deduplicate`` directly and the code emitted by ``codegen`` calls the same
wrapper via the ``ef.`` alias, so the two paths are equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from emergentflow.clean import DEDUP_KEEP, deduplicate
from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class Deduplicate(NodeDefinition):
    """Drop duplicate rows, optionally keying on a subset of columns."""

    type = "clean.deduplicate"
    version = 1
    family = "clean"
    label = "Deduplicate"
    category = "Transform"
    description = "Drop duplicate rows, optionally keying on a subset of columns."

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame to deduplicate.",
        ),
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="The deduplicated DataFrame.",
        ),
    ]
    params = [
        ParamSpec(
            name="subset",
            type_token="list[str]",
            default=None,
            label="Subset",
            help="Column(s) that define a duplicate. Defaults to every column.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="keep",
            type_token="str",
            default="first",
            label="Keep",
            help=(
                "Which duplicate to retain: the first, the last, or none (drop every "
                "duplicated row)."
            ),
            hints=ValidationHints(choices=list(DEDUP_KEEP), widget="select"),
        ),
        ParamSpec(
            name="ignore_index",
            type_token="bool",
            default=False,
            label="Reset index",
            help="Renumber the result index 0..n-1.",
            hints=ValidationHints(widget="checkbox"),
        ),
    ]

    def _args(self, node: Node) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        ignore_index = values.get("ignore_index")
        return {
            "subset": values.get("subset"),
            "keep": values.get("keep") or "first",
            "ignore_index": False if ignore_index is None else ignore_index,
        }

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        args = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('frame')} = ef.clean.deduplicate("
                f"{ctx.in_var('frame')}, subset={args['subset']!r}, "
                f"keep={args['keep']!r}, ignore_index={args['ignore_index']!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        args = self._args(node)
        return {
            "frame": deduplicate(
                inputs["frame"],
                subset=args["subset"],
                keep=args["keep"],
                ignore_index=args["ignore_index"],
            )
        }
