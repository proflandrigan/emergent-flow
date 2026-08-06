"""
emergentflow.nodes.examples.sample_rows
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``clean.sample_rows`` — a *transform* node (1 in, 1 out).

Reproducible row sampling (random / stratified / top-n). ``execute`` calls
``emergentflow.clean.sample_rows`` directly and the code emitted by ``codegen`` calls the same
wrapper via the ``ef.`` alias, so the two paths are equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from emergentflow.clean import SAMPLE_MODES, sample_rows
from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ColumnEffect, ColumnEffectKind, ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class SampleRows(NodeDefinition):
    """Draw a reproducible subset of rows (random, stratified, or top-n)."""

    type = "clean.sample_rows"
    version = 1
    family = "clean"
    label = "Sample Rows"
    category = "Transform"
    description = (
        "Draw a subset of rows -- uniformly at random, stratified within groups, or the first "
        "n rows -- with an always-captured seed so the result is reproducible."
    )

    column_effect = ColumnEffect(kind=ColumnEffectKind.PASSTHROUGH)

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame to sample from.",
        ),
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="The sampled subset of rows.",
        ),
    ]
    params = [
        ParamSpec(
            name="mode",
            type_token="str",
            default="random",
            label="Mode",
            help=(
                "random samples uniformly; stratified samples within each group; top_n takes "
                "the first n rows."
            ),
            hints=ValidationHints(choices=list(SAMPLE_MODES), widget="select"),
        ),
        ParamSpec(
            name="n",
            type_token="int",
            default=None,
            label="N",
            help=(
                "Number of rows to draw. Required for top_n; use either n or frac for the "
                "other modes."
            ),
            hints=ValidationHints(widget="number", min=1),
        ),
        ParamSpec(
            name="frac",
            type_token="float",
            default=None,
            label="Fraction",
            help="Fraction of rows to draw, between 0 and 1. Alternative to n.",
            hints=ValidationHints(widget="number", min=0, max=1),
        ),
        ParamSpec(
            name="by",
            type_token="list[str]",
            default=None,
            label="Stratify by",
            help="Stratified mode only: column(s) defining the groups to sample within.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="seed",
            type_token="int",
            default=0,
            label="Seed",
            help=(
                "Random seed, always captured so the same graph draws the same rows on every run."
            ),
            hints=ValidationHints(widget="number"),
        ),
    ]

    def _args(self, node: Node) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        seed = values.get("seed")
        return {
            "mode": values.get("mode") or "random",
            "n": values.get("n"),
            "frac": values.get("frac"),
            "by": values.get("by"),
            # An unset seed resolves to the wrapper's default rather than None: sampling must stay
            # reproducible, and a None seed would break ADR-0002 equivalence.
            "seed": 0 if seed is None else seed,
        }

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        args = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('frame')} = ef.clean.sample_rows("
                f"{ctx.in_var('frame')}, mode={args['mode']!r}, n={args['n']!r}, "
                f"frac={args['frac']!r}, by={args['by']!r}, seed={args['seed']!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        args = self._args(node)
        return {
            "frame": sample_rows(
                inputs["frame"],
                mode=args["mode"],
                n=args["n"],
                frac=args["frac"],
                by=args["by"],
                seed=args["seed"],
            )
        }
