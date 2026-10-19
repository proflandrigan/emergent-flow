"""ADR-0002: a cleared ``by`` field ("") on clean.detect_outliers means unset on BOTH paths."""

from __future__ import annotations

import pandas as pd

import emergentflow as ef
import emergentflow.nodes  # noqa: F401  (registers nodes)
from emergentflow.codegen.context import CodegenContext
from emergentflow.ir.node import Node
from emergentflow.ir.params import Param
from emergentflow.nodes.registry import registry

DF = pd.DataFrame({"a": [1.0, 2, 3, 4, 100, 6, 7, 8, 9, 10], "g": [1, 1, 2, 2, 3, 3, 4, 4, 5, 5]})


def test_detect_outliers_empty_string_by_matches_unset() -> None:
    defn = registry.get("clean.detect_outliers")()
    node = Node(
        type="clean.detect_outliers",
        params=[Param(name="columns", type_token="any", value=["a"])]
        + [Param(name="by", type_token="any", value="")],
    )
    executed = defn.execute(node, {"frame": DF})["frame"]
    ctx = CodegenContext(in_vars={"frame": "in_frame"}, out_vars={"frame": "out_frame"})
    scope: dict[str, object] = {"ef": ef, "in_frame": DF}
    exec(defn.codegen(node, ctx).body, scope)  # noqa: S102 -- test-only, our own emitted code
    pd.testing.assert_frame_equal(executed, scope["out_frame"])  # type: ignore[arg-type]
