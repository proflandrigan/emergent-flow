"""ADR-0002: a cleared canvas field ("") must behave like unset on BOTH codegen and execute."""

from __future__ import annotations

from typing import Any

import pandas as pd
import pytest

import emergentflow as ef
import emergentflow.nodes  # noqa: F401  (registers nodes)
from emergentflow.codegen.context import CodegenContext
from emergentflow.ir.node import Node
from emergentflow.ir.params import Param
from emergentflow.nodes.registry import registry

DF = pd.DataFrame(
    {"a": [1.0, 2, 3, 4, 100, 6, 7, 8, 9, 10], "g": [1, 1, 2, 2, 3, 3, 4, 4, 5, 5], "t": range(10)}
)


def _both(type_: str, params: dict[str, Any]) -> tuple[str, str]:
    defn = registry.get(type_)()
    node = Node(
        type=type_, params=[Param(name=k, type_token="any", value=v) for k, v in params.items()]
    )
    ctx = CodegenContext(
        in_vars={"frame": "in_frame"},
        out_vars={p.name: f"out_{p.name}" for p in defn.ports if p.direction.value == "out"},
    )

    def outcome(fn: Any) -> str:
        try:
            fn()
        except Exception as exc:
            return f"{type(exc).__name__}: {exc}"
        return "ok"

    exec_res = outcome(lambda: defn.execute(node, {"frame": DF}))
    body = defn.codegen(node, ctx).body
    gen_res = outcome(lambda: exec(body, {"ef": ef, "in_frame": DF}))
    return exec_res, gen_res


@pytest.mark.parametrize(
    ("type_", "params"),
    [
        ("stats.outlier_summary", {"by": ""}),
        ("ml.train_test_split", {"strategy": "stratified", "stratify_col": ""}),
        ("ml.train_test_split", {"strategy": "grouped", "group_col": ""}),
        ("ml.train_test_split", {"strategy": "temporal", "time_col": ""}),
    ],
)
def test_empty_string_same_outcome(type_: str, params: dict[str, Any]) -> None:
    exec_res, gen_res = _both(type_, params)
    assert exec_res == gen_res


def test_save_frame_empty_partition_by_same_outcome(tmp_path: Any) -> None:
    exec_res, gen_res = _both(
        "data.save_frame", {"path": str(tmp_path / "x.parquet"), "partition_by": ""}
    )
    assert exec_res == gen_res == "ok"
