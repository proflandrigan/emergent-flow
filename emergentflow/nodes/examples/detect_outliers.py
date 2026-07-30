"""
emergentflow.nodes.examples.detect_outliers
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``clean.detect_outliers`` — a *transform* node (1 in, 1 out).

Flags outlying rows using z-score, modified z-score/MAD, IQR, quantile, or
percent thresholds. ``execute`` calls ``emergentflow.clean.detect_outliers``
directly and the code emitted by ``codegen`` calls the same wrapper via the
``ef.`` alias, so the two paths are equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.clean import detect_outliers
from emergentflow.clean.outliers import OUTLIER_COMBINE, OUTLIER_METHODS
from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.ir.params import ParamValue

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class DetectOutliers(NodeDefinition):
    """Flag outlying rows with z-score, modified z-score, IQR, quantile, or percent rules."""

    type = "clean.detect_outliers"
    version = 1
    family = "clean"
    label = "Detect Outliers"
    category = "Transform"
    description = (
        "Flag outlying rows using z-score, modified z-score, IQR, quantile, or "
        "percent thresholds. Adds boolean 'is_outlier' and 'outlier_score' columns."
    )

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame whose numeric columns should be scanned for outliers.",
        ),
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="A NEW frame with added 'is_outlier' and 'outlier_score' columns.",
        ),
    ]
    params = [
        ParamSpec(
            name="columns",
            type_token="list[str]",
            default=None,
            label="Columns",
            help="Columns to scan; empty/unset scans all numeric columns.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="method",
            type_token="str",
            default="zscore",
            label="Method",
            help="Which outlier rule to apply.",
            hints=ValidationHints(
                choices=cast("list[ParamValue]", list(OUTLIER_METHODS)),
                widget="select",
            ),
        ),
        ParamSpec(
            name="threshold",
            type_token="float",
            default=3.0,
            label="Threshold",
            help="Rule cutoff, per method: SDs > 0 for zscore/modified_zscore, k > 0 for "
            "iqr, a tail quantile in (0, 0.5) for quantile, a fraction in (0, 1) for "
            "percent. The 3.0 default suits the first three; lower it when switching "
            "to quantile or percent.",
            hints=ValidationHints(widget="number", min=0),
        ),
        ParamSpec(
            name="combine",
            type_token="str",
            default="any",
            label="Combine",
            help="Flag a row when ANY or ALL target columns flag it.",
            hints=ValidationHints(
                choices=cast("list[ParamValue]", list(OUTLIER_COMBINE)),
                widget="select",
            ),
        ),
        ParamSpec(
            name="drop",
            type_token="bool",
            default=False,
            label="Drop outliers",
            help="If true, return only inlier rows and omit the added columns.",
            hints=ValidationHints(widget="checkbox"),
        ),
    ]

    def _args(self, node: Node) -> tuple[list[str] | None, str, float, str, bool]:
        values = {p.name: p.value for p in node.params}
        columns = values.get("columns")
        method = values.get("method") or "zscore"
        threshold = values.get("threshold")
        if threshold is None:
            threshold = 3.0
        combine = values.get("combine") or "any"
        drop = values.get("drop") or False
        return (
            cast("list[str] | None", columns),
            cast(str, method),
            cast(float, threshold),
            cast(str, combine),
            cast(bool, drop),
        )

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        columns, method, threshold, combine, drop = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('frame')} = ef.clean.detect_outliers("
                f"{ctx.in_var('frame')}, columns={columns!r}, method={method!r}, "
                f"threshold={threshold!r}, combine={combine!r}, drop={drop!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        columns, method, threshold, combine, drop = self._args(node)
        return {
            "frame": detect_outliers(
                inputs["frame"],
                columns=columns,
                method=method,
                threshold=threshold,
                combine=combine,
                drop=drop,
            )
        }
