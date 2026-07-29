"""
Tests for the ``clean.sample_rows`` / ``clean.fuzzy_join`` reference nodes (Epic 16, Story 9).

Covers:
1. Node instantiation and metadata
2. Execute produces correct output
3. ADR-0002 equivalence: execute output matches codegen output
4. Codegen is parseable and ruff-clean
"""

from __future__ import annotations

import ast
import subprocess
import sys

import pandas as pd
import pytest

from emergentflow.codegen.compiler import compile_to_code
from emergentflow.ir.common import Direction
from emergentflow.ir.edge import Edge, PortRef
from emergentflow.ir.graph import Graph
from emergentflow.nodes.examples import FuzzyJoin, LoadSample, SampleRows


def _out_port(node, name):
    return next(p for p in node.ports if p.direction == Direction.OUT and p.name == name)


def _in_port(node, name):
    return next(p for p in node.ports if p.direction == Direction.IN and p.name == name)


def _run_codegen(definition, node, scope):
    frag = definition.preview(node)
    exec(frag.render(), scope)  # noqa: S102
    return scope


def _df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "id": list(range(12)),
            "grp": ["a"] * 6 + ["b"] * 6,
            "value": [float(i) for i in range(12)],
        }
    )


def _left() -> pd.DataFrame:
    return pd.DataFrame({"name": ["Apple Inc", "Microsft Corp"], "lid": [1, 2]})


def _right() -> pd.DataFrame:
    return pd.DataFrame({"company": ["Apple Inc.", "Microsoft Corp"], "rid": [10, 20]})


# ---------------------------------------------------------------------------
# SampleRows
# ---------------------------------------------------------------------------


def test_sample_rows_node_metadata():
    defn = SampleRows()
    assert defn.type == "clean.sample_rows"
    assert defn.family == "clean"
    assert defn.version == 1
    in_ports = [p for p in defn.ports if p.direction == Direction.IN]
    out_ports = [p for p in defn.ports if p.direction == Direction.OUT]
    assert len(in_ports) == 1
    assert len(out_ports) == 1
    assert in_ports[0].name == "frame"
    assert out_ports[0].name == "frame"


def test_sample_rows_execute():
    defn = SampleRows()
    node = defn.instantiate(mode="random", n=4, seed=3)

    result = defn.execute(node, inputs={"frame": _df()})
    out = result["frame"]
    assert len(out) == 4


def test_sample_rows_default_seed_is_zero():
    defn = SampleRows()
    node = defn.instantiate(mode="random", n=4)

    assert defn._args(node)["seed"] == 0


@pytest.mark.equivalence
def test_sample_rows_equivalence():
    defn = SampleRows()
    node = defn.instantiate(mode="random", n=4, seed=3)

    executed = defn.execute(node, inputs={"frame": _df()})
    scope = _run_codegen(defn, node, {"frame": _df()})

    pd.testing.assert_frame_equal(executed["frame"], scope["frame"])


def test_sample_rows_stratified_execute():
    defn = SampleRows()
    node = defn.instantiate(mode="stratified", by=["grp"], n=2)

    result = defn.execute(node, inputs={"frame": _df()})
    out = result["frame"]
    assert len(out) == 4


def _build_sample_rows_graph():
    load = LoadSample().instantiate(name="iris", label="Load Sample")
    node = SampleRows().instantiate(label=SampleRows.label, mode="random", n=4, seed=3)
    edge = Edge(
        source=PortRef(node_id=load.id, port_id=_out_port(load, "frame").id),
        target=PortRef(node_id=node.id, port_id=_in_port(node, "frame").id),
    )
    return Graph(
        nodes={load.id: load, node.id: node},
        edges={edge.id: edge},
    )


def test_sample_rows_codegen_is_parseable():
    graph = _build_sample_rows_graph()
    code = compile_to_code(graph)
    ast.parse(code)


def test_sample_rows_codegen_is_ruff_clean():
    graph = _build_sample_rows_graph()
    code = compile_to_code(graph)
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "-"],
        input=code,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# FuzzyJoin
# ---------------------------------------------------------------------------


def test_fuzzy_join_node_metadata():
    defn = FuzzyJoin()
    assert defn.type == "clean.fuzzy_join"
    assert defn.family == "clean"
    assert defn.version == 1
    in_ports = [p for p in defn.ports if p.direction == Direction.IN]
    out_ports = [p for p in defn.ports if p.direction == Direction.OUT]
    assert len(in_ports) == 2
    assert {p.name for p in in_ports} == {"left", "right"}
    assert len(out_ports) == 1
    assert out_ports[0].name == "frame"


def test_fuzzy_join_args_coerces_suffixes_to_tuple():
    defn = FuzzyJoin()
    node = defn.instantiate(left_on="name", right_on="company")

    assert isinstance(defn._args(node)["suffixes"], tuple)


def test_fuzzy_join_execute():
    pytest.importorskip("rapidfuzz")
    defn = FuzzyJoin()
    node = defn.instantiate(left_on="name", right_on="company", threshold=80)

    result = defn.execute(node, inputs={"left": _left(), "right": _right()})
    out = result["frame"]
    assert "match_score" in out.columns


@pytest.mark.equivalence
def test_fuzzy_join_equivalence():
    pytest.importorskip("rapidfuzz")
    defn = FuzzyJoin()
    node = defn.instantiate(left_on="name", right_on="company", threshold=80)

    executed = defn.execute(node, inputs={"left": _left(), "right": _right()})
    scope = _run_codegen(defn, node, {"left": _left(), "right": _right()})

    pd.testing.assert_frame_equal(executed["frame"], scope["frame"])


def _build_fuzzy_join_graph():
    load_a = LoadSample().instantiate(name="iris", label="Load A")
    load_b = LoadSample().instantiate(name="iris", label="Load B")
    node = FuzzyJoin().instantiate(label=FuzzyJoin.label, left_on="name", right_on="company")
    edge_left = Edge(
        source=PortRef(node_id=load_a.id, port_id=_out_port(load_a, "frame").id),
        target=PortRef(node_id=node.id, port_id=_in_port(node, "left").id),
    )
    edge_right = Edge(
        source=PortRef(node_id=load_b.id, port_id=_out_port(load_b, "frame").id),
        target=PortRef(node_id=node.id, port_id=_in_port(node, "right").id),
    )
    return Graph(
        nodes={load_a.id: load_a, load_b.id: load_b, node.id: node},
        edges={edge_left.id: edge_left, edge_right.id: edge_right},
    )


def test_fuzzy_join_codegen_is_parseable():
    graph = _build_fuzzy_join_graph()
    code = compile_to_code(graph)
    ast.parse(code)


def test_fuzzy_join_codegen_is_ruff_clean():
    graph = _build_fuzzy_join_graph()
    code = compile_to_code(graph)
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "-"],
        input=code,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
