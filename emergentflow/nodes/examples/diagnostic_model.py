"""
emergentflow.nodes.examples.diagnostic_model
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``stats.diagnostic_model`` — the StatsModel-input half of the "diagnostic"
archetype (Epic 12, Story 6).

Runs a curated, allow-listed diagnostic that operates on an already-fitted ``StatsModel``
(currently ``"normality"``/``"heteroscedasticity"``/``"autocorrelation"``, all residual-based)
and returns a tidy diagnostic DataFrame. The ``diagnostic`` choice list is computed at import
time, restricted to diagnostics whose ``needs_model`` flag is set, from the live registry -- it
grows automatically as more model-input diagnostics are curated (no edits needed here). See
``emergentflow.nodes.examples.diagnostic_frame`` for why this is two node types instead of one
node with an optional port. ``execute`` calls ``emergentflow.stats.diagnostic`` directly and the
code emitted by ``codegen`` calls the same wrapper via the ``ef.`` alias, so the two paths are
equivalent by construction (ADR 0002).
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

_MODEL_DIAGNOSTIC_KEYS = [
    key for key in known_diagnostic_keys() if get_diagnostic_spec(key).needs_model
]


@register
class DiagnosticModel(NodeDefinition):
    """Run a curated, allow-listed StatsModel-input diagnostic (e.g. normality, Breusch-Pagan)."""

    type = "stats.diagnostic_model"
    version = 1
    family = "stats"
    label = "Diagnostic (Model)"
    category = "Statistics"
    description = "Run a curated diagnostic on a fitted StatsModel's residuals."

    ports = [
        PortSpec(
            name="model",
            direction=Direction.IN,
            data_type="StatsModel",
            help="The fitted statistical model to diagnose.",
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
            help="Which allow-listed model-input diagnostic to run.",
            hints=ValidationHints(
                choices=cast("list[ParamValue]", _MODEL_DIAGNOSTIC_KEYS),
                widget="select",
            ),
        ),
        ParamSpec(
            name="spec_extra",
            type_token="dict[str, any]",
            default={},
            label="Additional spec fields",
            help="Diagnostic-specific structured-spec fields, if any.",
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
                f"diagnostic={diag!r}, model={ctx.in_var('model')}, spec={spec!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        diag, spec = self._args(node)
        return {"diagnostics": stats_diagnostic(diagnostic=diag, model=inputs["model"], spec=spec)}
