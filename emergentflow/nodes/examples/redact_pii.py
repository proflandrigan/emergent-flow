"""
emergentflow.nodes.examples.redact_pii
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``clean.redact_pii`` — a *transform* node (1 in, 1 out).

Regex-based PII detection + masking in the base install, plus NER-based detection via presidio
(``engine="presidio"``, requires the optional ``[pii]`` extra) (Epic 16, Story 21); positioned
to run right after ingestion. ``execute`` calls ``emergentflow.clean.redact_pii`` directly and
the code emitted by ``codegen`` calls the same wrapper via the ``ef.`` alias, so the two paths
are equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.clean import redact_pii
from emergentflow.clean.pii import DEFAULT_MASK
from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class RedactPii(NodeDefinition):
    """Detect and mask common PII patterns (email, phone, SSN-like, credit-card-like)."""

    type = "clean.redact_pii"
    version = 1
    family = "clean"
    label = "Redact PII"
    category = "Transform"
    description = (
        "Detect and mask common PII (email, phone, SSN-like, credit-card-like) in text "
        "columns via regex, or NER-based via presidio ([pii] extra); positioned to run "
        "right after ingestion."
    )

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame to scan for PII.",
        ),
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="The DataFrame with detected PII masked.",
        ),
    ]
    params = [
        ParamSpec(
            name="columns",
            type_token="list[str]",
            default=None,
            label="Columns",
            help="Columns to scan; defaults to every text column when unset.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="categories",
            type_token="list[str]",
            default=None,
            label="Categories",
            help="Which PII categories to redact ('email'|'phone'|'ssn'|'credit_card'); "
            "defaults to all of them.",
            hints=ValidationHints(widget="json"),
        ),
        ParamSpec(
            name="mask",
            type_token="str",
            default=DEFAULT_MASK,
            label="Mask text",
            help="Replacement text for each detected match.",
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="engine",
            type_token="str",
            default="regex",
            label="Engine",
            help="'regex' (base install) or 'presidio' (NER-based, requires the optional "
            "[pii] extra).",
            hints=ValidationHints(choices=["regex", "presidio"], widget="select"),
        ),
    ]

    def _args(self, node: Node) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        return {
            "columns": cast("list[str] | None", values.get("columns")),
            "categories": cast("list[str] | None", values.get("categories")),
            "mask": values.get("mask") or DEFAULT_MASK,
            "engine": values.get("engine") or "regex",
        }

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        args = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('frame')} = ef.clean.redact_pii("
                f"{ctx.in_var('frame')}, columns={args['columns']!r}, "
                f"categories={args['categories']!r}, mask={args['mask']!r}, "
                f"engine={args['engine']!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        args = self._args(node)
        return {
            "frame": redact_pii(
                inputs["frame"],
                columns=args["columns"],
                categories=args["categories"],
                mask=args["mask"],
                engine=args["engine"],
            )
        }
