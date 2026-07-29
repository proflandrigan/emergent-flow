"""
emergentflow.nodes.examples.fuzzy_join
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``clean.fuzzy_join`` — a *transform* node (2 in, 1 out).

String-similarity keyed merge over two DataFrames. ``execute`` calls
``emergentflow.clean.fuzzy_join`` directly and the code emitted by ``codegen`` calls the same
wrapper via the ``ef.`` alias, so the two paths are equivalent by construction (ADR 0002).

This module must NOT import ``rapidfuzz`` — the optional ``[fuzzy]`` extra is gated lazily
inside the ``fuzzy_join`` wrapper itself, so importing this node module (and therefore the
whole node registry) never requires it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.clean import FUZZY_HOWS, FUZZY_SCORERS, fuzzy_join
from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class FuzzyJoin(NodeDefinition):
    """Merge two DataFrames on a string-similarity match between key columns."""

    type = "clean.fuzzy_join"
    version = 1
    family = "clean"
    label = "Fuzzy Join"
    category = "Transform"
    description = (
        "Merge two DataFrames on a string-similarity match between one left and one right key "
        "column, rather than on exact equality. Requires the [fuzzy] extra."
    )

    ports = [
        PortSpec(
            name="left",
            label="Left",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The left DataFrame.",
        ),
        PortSpec(
            name="right",
            label="Right",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The right DataFrame.",
        ),
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="The fuzzy-matched join result, with a similarity-score column.",
        ),
    ]
    params = [
        ParamSpec(
            name="left_on",
            type_token="str",
            default=None,
            required=True,
            label="Left on",
            help="Left-frame key column to match on.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="right_on",
            type_token="str",
            default=None,
            required=True,
            label="Right on",
            help="Right-frame key column to match against.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="threshold",
            type_token="float",
            default=85.0,
            label="Threshold",
            help="Minimum similarity score (0-100) for a pair to count as a match.",
            hints=ValidationHints(widget="number", min=0, max=100),
        ),
        ParamSpec(
            name="scorer",
            type_token="str",
            default="ratio",
            label="Scorer",
            help="Similarity metric used to score candidate pairs.",
            hints=ValidationHints(choices=list(FUZZY_SCORERS), widget="select"),
        ),
        ParamSpec(
            name="how",
            type_token="str",
            default="inner",
            label="How",
            help=(
                "inner drops unmatched left rows; left keeps them with NaN on the right-hand "
                "columns."
            ),
            hints=ValidationHints(choices=list(FUZZY_HOWS), widget="select"),
        ),
        ParamSpec(
            name="limit",
            type_token="int",
            default=1,
            label="Limit",
            help="Matches to keep per left row: 1 for a one-to-one join, more for one-to-many.",
            hints=ValidationHints(widget="number", min=1),
        ),
        ParamSpec(
            name="suffixes",
            type_token="list[str]",
            default=["_x", "_y"],
            label="Suffixes",
            help="Suffixes appended to overlapping column names from (left, right).",
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="score_column",
            type_token="str",
            default="match_score",
            label="Score column",
            help="Name of the output column holding the realised similarity score.",
            hints=ValidationHints(widget="text"),
        ),
    ]

    def _args(self, node: Node) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        suffixes = cast(list, values.get("suffixes") or ["_x", "_y"])
        threshold = values.get("threshold")
        limit = values.get("limit")
        return {
            "left_on": values.get("left_on"),
            "right_on": values.get("right_on"),
            "threshold": 85.0 if threshold is None else threshold,
            "scorer": values.get("scorer") or "ratio",
            "how": values.get("how") or "inner",
            "limit": 1 if limit is None else limit,
            # tuple, not list -- so codegen and execute pass the identical type (see merge.py).
            "suffixes": tuple(suffixes),
            "score_column": values.get("score_column") or "match_score",
        }

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        args = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('frame')} = ef.clean.fuzzy_join("
                f"{ctx.in_var('left')}, {ctx.in_var('right')}, "
                f"left_on={args['left_on']!r}, right_on={args['right_on']!r}, "
                f"threshold={args['threshold']!r}, scorer={args['scorer']!r}, "
                f"how={args['how']!r}, limit={args['limit']!r}, "
                f"suffixes={args['suffixes']!r}, score_column={args['score_column']!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        args = self._args(node)
        return {
            "frame": fuzzy_join(
                inputs["left"],
                inputs["right"],
                left_on=args["left_on"],
                right_on=args["right_on"],
                threshold=args["threshold"],
                scorer=args["scorer"],
                how=args["how"],
                limit=args["limit"],
                suffixes=args["suffixes"],
                score_column=args["score_column"],
            )
        }
