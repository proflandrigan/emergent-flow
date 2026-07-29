"""
emergentflow.nodes.examples.assert_data
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``research.assert_data`` -- the data-quality gate (Epic 16, Story 19).

Runs a declarative list of expectations against the input frame. Passing: the frame passes
through unchanged. Failing: the graph fails loudly with a typed
:class:`~emergentflow.research.errors.DataQualityError` carrying a tidy violations frame (see
``emergentflow.research.quality.check_data_quality`` for the full expectation-type reference).
``execute`` calls ``emergentflow.research.check_data_quality`` directly and the code emitted by
``codegen`` calls the same wrapper via the ``ef.`` alias, so the two paths are equivalent by
construction (ADR 0002) -- including the failure path, since both raise the same typed error
for the same input.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.research import check_data_quality

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class AssertData(NodeDefinition):
    """Run declarative data-quality expectations; pass through on success, fail loudly on
    violation."""

    type = "research.assert_data"
    version = 1
    family = "research"
    label = "Assert Data"
    category = "Reporting"
    description = (
        "Run declarative data-quality expectations (non-null, range, uniqueness, "
        "allowed-values, regex-match, row-count, schema) against a DataFrame; passes it "
        "through unchanged on success, raises a typed error with a violations frame on failure."
    )

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The DataFrame to check.",
        ),
        PortSpec(
            name="frame",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="The same DataFrame, unchanged, when every expectation passes.",
        ),
    ]
    params = [
        ParamSpec(
            name="expectations",
            type_token="list[dict[str, any]]",
            default=None,
            required=True,
            label="Expectations",
            help=(
                "Ordered list of expectation dicts, each with a 'type' "
                "('non_null'|'range'|'unique'|'allowed_values'|'regex_match'|'row_count'|"
                "'schema') plus type-specific keys -- see "
                "emergentflow.research.quality.check_data_quality for the full reference."
            ),
            hints=ValidationHints(widget="json"),
        ),
    ]

    def _args(self, node: Node) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        return {"expectations": values.get("expectations") or []}

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        args = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('frame')} = ef.research.check_data_quality("
                f"{ctx.in_var('frame')}, {args['expectations']!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        args = self._args(node)
        return {"frame": check_data_quality(inputs["frame"], args["expectations"])}
