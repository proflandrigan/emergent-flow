"""Tests for the `source_file`/`connection` params on the three loader nodes.

Epic 16 Story 2's node half: the glob/multi-file and remote-URI capabilities added
to `ef.data.load_csv`/`load_parquet`/`load_json` (Tasks 08 and 09) are now surfaced
on the corresponding nodes so the canvas can drive them.

Golden: the compiled code passes `ast.parse` and `ruff check`, and the emitted call
carries `source_file=`/`connection=` keywords.
Equivalence: `execute(graph)` matches the compile path over a glob graph, under no
client (these nodes are not `requires_client`).
"""

from __future__ import annotations

import ast
import subprocess
import sys

import pandas as pd
from pandas.testing import assert_frame_equal

from emergentflow.codegen.compiler import compile_to_code
from emergentflow.codegen.executor import execute
from emergentflow.ir import Graph
from emergentflow.nodes.examples.load_csv import LoadCsv
from emergentflow.nodes.examples.load_json import LoadJson
from emergentflow.nodes.examples.load_parquet import LoadParquet


def _build_graph(defn, **params) -> Graph:
    node = defn.instantiate(**params)
    return Graph(name="loader_glob_test", nodes={node.id: node}, edges={})


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
# data.load_csv
# ---------------------------------------------------------------------------


def test_load_csv_golden_and_keywords() -> None:
    graph = _build_graph(LoadCsv(), path="data/*.csv")
    code = _assert_golden(graph)
    assert "source_file=" in code
    assert "connection=" in code


def test_load_csv_glob_equivalence(tmp_path) -> None:
    (tmp_path / "a.csv").write_text("a,b\n1,x\n")
    (tmp_path / "b.csv").write_text("a,b\n2,y\n")

    graph = _build_graph(LoadCsv(), path=str(tmp_path / "*.csv"), source_file=True)

    expected = pd.DataFrame(
        {
            "a": [1, 2],
            "b": ["x", "y"],
            "source_file": [str(tmp_path / "a.csv"), str(tmp_path / "b.csv")],
        }
    )
    _assert_equivalence(graph, expected)


# ---------------------------------------------------------------------------
# data.load_parquet
# ---------------------------------------------------------------------------


def test_load_parquet_golden_and_keywords() -> None:
    graph = _build_graph(LoadParquet(), path="data/*.parquet")
    code = _assert_golden(graph)
    assert "source_file=" in code
    assert "connection=" in code


def test_load_parquet_glob_equivalence(tmp_path) -> None:
    pd.DataFrame({"a": [1], "b": ["x"]}).to_parquet(tmp_path / "a.parquet")
    pd.DataFrame({"a": [2], "b": ["y"]}).to_parquet(tmp_path / "b.parquet")

    graph = _build_graph(LoadParquet(), path=str(tmp_path / "*.parquet"), source_file=True)

    expected = pd.DataFrame(
        {
            "a": [1, 2],
            "b": ["x", "y"],
            "source_file": [str(tmp_path / "a.parquet"), str(tmp_path / "b.parquet")],
        }
    )
    _assert_equivalence(graph, expected)


# ---------------------------------------------------------------------------
# data.load_json
# ---------------------------------------------------------------------------


def test_load_json_golden_and_keywords() -> None:
    graph = _build_graph(LoadJson(), path="data/*.json")
    code = _assert_golden(graph)
    assert "source_file=" in code
    assert "connection=" in code


def test_load_json_glob_equivalence(tmp_path) -> None:
    pd.DataFrame({"a": [1], "b": ["x"]}).to_json(tmp_path / "a.json", orient="records")
    pd.DataFrame({"a": [2], "b": ["y"]}).to_json(tmp_path / "b.json", orient="records")

    graph = _build_graph(
        LoadJson(), path=str(tmp_path / "*.json"), orient="records", source_file=True
    )

    expected = pd.DataFrame(
        {
            "a": [1, 2],
            "b": ["x", "y"],
            "source_file": [str(tmp_path / "a.json"), str(tmp_path / "b.json")],
        }
    )
    _assert_equivalence(graph, expected)


# ---------------------------------------------------------------------------
# version bump guard
# ---------------------------------------------------------------------------


def test_loader_node_versions_bumped() -> None:
    assert LoadCsv.version > 2
    assert LoadParquet.version > 2
    assert LoadJson.version > 2
