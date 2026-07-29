"""Tests for the ``data.load_excel`` node (Epic 16 Story 3).

Golden: the compiled code passes ``ast.parse`` and ``ruff check``, and carries
all expected keywords.
Equivalence: ``execute(graph)`` matches the compile path over a real workbook
(no client — this node is not ``requires_client``).
"""

from __future__ import annotations

import ast
import subprocess
import sys

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from emergentflow.codegen.compiler import compile_to_code
from emergentflow.codegen.executor import execute
from emergentflow.ir import Graph
from emergentflow.nodes import get as get_node_definition
from emergentflow.nodes.examples.load_excel import LoadExcel

pytest.importorskip("openpyxl")


def _build_graph(**params) -> Graph:
    defn = LoadExcel()
    node = defn.instantiate(**params)
    return Graph(name="load_excel_test", nodes={node.id: node}, edges={})


def _assert_golden(graph: Graph) -> str:
    code = compile_to_code(graph)
    ast.parse(code)
    proc = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--stdin-filename", "generated.py", "-"],
        input=code,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"ruff check failed:\n{proc.stdout}\n{proc.stderr}"
    return code


def _assert_equivalence(graph: Graph, expected: pd.DataFrame) -> None:
    node_id = list(graph.nodes.keys())[0]
    exec_results = execute(graph)
    exec_frame = exec_results[node_id]["frame"]

    code = compile_to_code(graph)
    ns: dict = {}
    exec(code, ns)  # noqa: S102
    main_results = ns["main"]()
    code_frame = next(iter(main_results.values()))

    assert_frame_equal(exec_frame, expected)
    assert_frame_equal(code_frame, expected)


# ---------------------------------------------------------------------------
# Golden tests
# ---------------------------------------------------------------------------


def test_load_excel_golden_ast_parse() -> None:
    graph = _build_graph(path="data/*.xlsx")
    _assert_golden(graph)


def test_load_excel_golden_ruff_check() -> None:
    graph = _build_graph(path="data/*.xlsx")
    _assert_golden(graph)


def test_compiled_call_has_all_keywords() -> None:
    graph = _build_graph(path="data/*.xlsx")
    code = compile_to_code(graph)
    assert "sheet=" in code
    assert "header_row=" in code
    assert "usecols=" in code
    assert "source_file=" in code
    assert "connection=" in code


# ---------------------------------------------------------------------------
# Sheet string coercion
# ---------------------------------------------------------------------------


def test_sheet_index_emits_int() -> None:
    graph = _build_graph(path="test.xlsx", sheet="1")
    code = compile_to_code(graph)
    assert "sheet=1" in code


def test_sheet_name_emits_str() -> None:
    graph = _build_graph(path="test.xlsx", sheet="Sales")
    code = compile_to_code(graph)
    assert 'sheet="Sales"' in code


# ---------------------------------------------------------------------------
# Equivalence tests
# ---------------------------------------------------------------------------


def test_load_excel_equivalence(tmp_path) -> None:
    df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    path = tmp_path / "test.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Sheet1")

    graph = _build_graph(path=str(path))
    _assert_equivalence(graph, df)


def test_sheet_index_equivalence(tmp_path) -> None:
    df1 = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    df2 = pd.DataFrame({"c": [3, 4], "d": ["p", "q"]})
    path = tmp_path / "multi.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df1.to_excel(writer, index=False, sheet_name="Sheet1")
        df2.to_excel(writer, index=False, sheet_name="Data")

    graph = _build_graph(path=str(path), sheet="1")
    _assert_equivalence(graph, df2)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_node_is_registered() -> None:
    cls = get_node_definition("data.load_excel")
    assert cls is LoadExcel
