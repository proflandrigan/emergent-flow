"""
emergentflow.nodes.examples.diagnostic_frame
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``stats.diagnostic_frame`` — the DataFrame-input half of the "diagnostic"
archetype (Epic 12, Story 6).

Runs a curated, allow-listed diagnostic that operates on a raw DataFrame (currently just
``"vif"`` -- variance-inflation factors) and returns a tidy diagnostic DataFrame. The
``diagnostic`` choice list is computed at import time, restricted to diagnostics whose
``needs_frame`` flag is set, from the live registry -- it grows automatically as more
frame-based diagnostics are curated (no edits needed here). A companion node,
``stats.diagnostic_model``, covers the model-input diagnostics (normality/heteroscedasticity/
autocorrelation) -- see that file for why this is two node types instead of one node with an
optional port. ``execute`` calls ``emergentflow.stats.diagnostic`` directly and the code emitted
by ``codegen`` calls the same wrapper via the ``ef.`` alias, so the two paths are equivalent by
construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.ir.params import ParamValue
from emergentflow.stats import diagnostic as stats_diagnostic
from emergentflow.stats.diagnostics import get_diagnostic_spec, known_diagnostic_keys

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext

_FRAME_DIAGNOSTIC_KEYS = [
    key for key in known_diagnostic_keys() if get_diagnostic_spec(key).needs_frame
]


@register
class DiagnosticFrame(NodeDefinition):
    """Run a curated, allow-listed DataFrame-input diagnostic (e.g. VIF)."""

    type = "stats.diagnostic_frame"
    version = 1
    family = "stats"
    label = "Diagnostic (DataFrame)"
    category = "Statistics"
    description = "Run a curated diagnostic that operates on a raw DataFrame (e.g. VIF)."

    ports = [
        PortSpec(
            name="frame",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame to diagnose.",
        ),
        PortSpec(
            name="diagnostics",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="The tidy diagnostic result frame.",
        ),
    ]
    params = [
        ParamSpec(
            name="diagnostic",
            type_token="str",
            required=True,
            label="Diagnostic",
            help="Which allow-listed DataFrame-input diagnostic to run.",
            hints=ValidationHints(
                choices=cast("list[ParamValue]", _FRAME_DIAGNOSTIC_KEYS),
                widget="select",
            ),
        ),
        ParamSpec(
            name="spec_extra",
            type_token="dict[str, any]",
            default={},
            label="Additional spec fields",
            help="Diagnostic-specific structured-spec fields (e.g. VIF's 'columns'/'threshold').",
        ),
    ]

    def _args(self, node: Node) -> tuple[str, dict[str, Any]]:
        values = {p.name: p.value for p in node.params}
        diag = cast(str, values.get("diagnostic"))
        spec = cast("dict[str, Any]", values.get("spec_extra") or {})
        return diag, spec

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        diag, spec = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('diagnostics')} = ef.stats.diagnostic("
                f"{ctx.in_var('frame')}, diagnostic={diag!r}, spec={spec!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        diag, spec = self._args(node)
        return {"diagnostics": stats_diagnostic(inputs["frame"], diagnostic=diag, spec=spec)}
