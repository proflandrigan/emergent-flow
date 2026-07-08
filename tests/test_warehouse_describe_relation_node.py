"""Tests for the ``data.describe_relation`` node (Epic 13 Story 7).

Golden: the compiled code for a representative describe_relation graph passes
``ast.parse`` and ``ruff check`` (importable, clean).

Equivalence: ``execute(graph)`` produces the same DataFrame as the recorded
fixture the compiled code's ``client.describe_relation`` call would replay.
"""

from __future__ import annotations

import ast
import subprocess
import sys

import pandas as pd
from pandas.testing import assert_frame_equal

from emergentflow.clients import Clients
from emergentflow.codegen.compiler import compile_to_code
from emergentflow.codegen.executor import execute
from emergentflow.data.warehouse.replay import ReplayWarehouseClient, write_describe_fixture
from emergentflow.ir import Graph
from emergentflow.nodes.examples.describe_relation import DescribeRelation


def _build_describe_relation_graph() -> Graph:
    """Build a minimal graph with one ``data.describe_relation`` node."""
    defn = DescribeRelation()
    node = defn.instantiate(
        label="Describe Sales",
        connection="test_duckdb",
        relation="sales",
    )
    return Graph(
        name="describe_relation_test",
        nodes={node.id: node},
        edges={},
    )


def _make_fixture(fixtures_dir) -> pd.DataFrame:
    """Create a replay fixture for the test graph's describe_relation call."""
    df = pd.DataFrame(
        {
            "database": [float("nan"), float("nan")],
            "schema": [float("nan"), float("nan")],
            "table": ["sales", "sales"],
            "column": ["id", "revenue"],
            "data_type": ["int64", "float64"],
            "nullable": [False, True],
        }
    )
    write_describe_fixture(fixtures_dir, "test_duckdb", "sales", df)
    return df


# ---- Golden tests ----


def test_describe_relation_golden_ast_parse() -> None:
    """Compiled code for a describe_relation graph is valid Python (ast.parse succeeds)."""
    graph = _build_describe_relation_graph()
    code = compile_to_code(graph)
    ast.parse(code)


def test_describe_relation_golden_ruff_check() -> None:
    """Compiled code for a describe_relation graph passes ruff check (importable, clean)."""
    graph = _build_describe_relation_graph()
    code = compile_to_code(graph)
    proc = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--stdin-filename", "generated.py", "-"],
        input=code,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"ruff check failed:\n{proc.stdout}\n{proc.stderr}"


def test_describe_relation_compiled_references_warehouse() -> None:
    """Compiled code threads ``warehouse`` from the clients bundle, not ``client``."""
    graph = _build_describe_relation_graph()
    code = compile_to_code(graph)
    assert "client=warehouse" in code
    assert "def main(*, clients:" in code
    assert "ef.data.describe_relation(" in code


# ---- Equivalence test ----


def test_describe_relation_equivalence(tmp_path) -> None:
    """execute(graph) returns the DataFrame recorded for this describe_relation call."""
    graph = _build_describe_relation_graph()
    expected_df = _make_fixture(tmp_path)
    replay = ReplayWarehouseClient(tmp_path)

    exec_results = execute(graph, clients=Clients(warehouse=replay))
    node_id = list(graph.nodes.keys())[0]
    exec_df = exec_results[node_id]["frame"]

    assert_frame_equal(exec_df, expected_df)
