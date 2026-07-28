"""
Tests for the ``clean.concat`` / ``clean.deduplicate`` / ``clean.sort`` reference nodes
(Epic 16, Story 7).

Covers:
1. Node instantiation and metadata
2. The ``frames`` IN port's MANY cardinality (the variadic-archetype regression guard)
3. Execute produces correct output
4. ADR-0002 equivalence: execute output matches codegen output
5. Codegen is parseable and ruff-clean
"""

from __future__ import annotations

import ast
import subprocess
import sys

import pandas as pd
import pytest

from emergentflow.codegen.compiler import compile_to_code
from emergentflow.ir.common import Cardinality, Direction
from emergentflow.ir.edge import Edge, PortRef
from emergentflow.ir.graph import Graph
from emergentflow.nodes.examples import Concat, Deduplicate, LoadSample, Sort


def _out_port(node, name):
    return next(p for p in node.ports if p.direction == Direction.OUT and p.name == name)


def _in_port(node, name):
    return next(p for p in node.ports if p.direction == Direction.IN and p.name == name)


def _run_codegen(definition, node, scope):
    frag = definition.preview(node)
    exec(frag.render(), scope)  # noqa: S102
    return scope


def _a() -> pd.DataFrame:
    return pd.DataFrame({"id": [1, 2], "value": [10.0, 20.0]})


def _b() -> pd.DataFrame:
    return pd.DataFrame({"id": [3, 4], "value": [30.0, 40.0]})


def _dupes() -> pd.DataFrame:
    return pd.DataFrame(
        {"id": [1, 1, 2, 2, 3], "grp": ["a", "a", "b", "b", "c"], "n": [1, 2, 3, 4, 5]}
    )


# ---------------------------------------------------------------------------
# 1. Node metadata
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "defn_cls,expected_type",
    [
        (Concat, "clean.concat"),
        (Deduplicate, "clean.deduplicate"),
        (Sort, "clean.sort"),
    ],
)
def test_combine_node_metadata(defn_cls, expected_type):
    defn = defn_cls()
    assert defn.type == expected_type
    assert defn.family == "clean"
    assert defn.version == 1


def test_concat_port_is_many_cardinality():
    defn = Concat()
    frames_port = _in_port(defn, "frames")
    assert frames_port.cardinality == Cardinality.MANY


# ---------------------------------------------------------------------------
# 2. Execute
# ---------------------------------------------------------------------------


def test_concat_execute():
    defn = Concat()
    node = defn.instantiate(source_column="src")

    result = defn.execute(node, inputs={"frames": [_a(), _b()]})
    out = result["frame"]
    assert len(out) == 4
    assert "src" in out.columns


def test_deduplicate_execute():
    defn = Deduplicate()
    node = defn.instantiate(subset=["id"])

    result = defn.execute(node, inputs={"frame": _dupes()})
    out = result["frame"]
    assert len(out) == 3


def test_sort_execute():
    defn = Sort()
    node = defn.instantiate(by=["n"], ascending=[False])

    result = defn.execute(node, inputs={"frame": _dupes()})
    out = result["frame"]
    assert list(out["n"]) == sorted(out["n"], reverse=True)


# ---------------------------------------------------------------------------
# 3. ADR-0002 equivalence
# ---------------------------------------------------------------------------


@pytest.mark.equivalence
def test_concat_equivalence():
    defn = Concat()
    node = defn.instantiate(source_column="src")

    executed = defn.execute(node, inputs={"frames": [_a(), _b()]})
    scope = _run_codegen(defn, node, {"frames": [_a(), _b()]})

    pd.testing.assert_frame_equal(executed["frame"], scope["frame"])


@pytest.mark.equivalence
def test_deduplicate_equivalence():
    defn = Deduplicate()
    node = defn.instantiate(subset=["id"])

    executed = defn.execute(node, inputs={"frame": _dupes()})
    scope = _run_codegen(defn, node, {"frame": _dupes()})

    pd.testing.assert_frame_equal(executed["frame"], scope["frame"])


@pytest.mark.equivalence
def test_sort_equivalence():
    defn = Sort()
    node = defn.instantiate(by=["n"], ascending=[False])

    executed = defn.execute(node, inputs={"frame": _dupes()})
    scope = _run_codegen(defn, node, {"frame": _dupes()})

    pd.testing.assert_frame_equal(executed["frame"], scope["frame"])


# ---------------------------------------------------------------------------
# 4. Codegen quality
# ---------------------------------------------------------------------------


def _build_single_input_graph(defn_cls, **params):
    load = LoadSample().instantiate(name="iris", label="Load Sample")
    node = defn_cls().instantiate(label=defn_cls.label, **params)
    edge = Edge(
        source=PortRef(node_id=load.id, port_id=_out_port(load, "frame").id),
        target=PortRef(node_id=node.id, port_id=_in_port(node, "frame").id),
    )
    return Graph(
        nodes={load.id: load, node.id: node},
        edges={edge.id: edge},
    )


_COMBINE_CASES = [
    (Deduplicate, {"subset": ["sepal_length"]}),
    (Sort, {"by": ["sepal_length"]}),
]


@pytest.mark.parametrize("defn_cls,params", _COMBINE_CASES)
def test_deduplicate_and_sort_codegen_is_parseable(defn_cls, params):
    graph = _build_single_input_graph(defn_cls, **params)
    code = compile_to_code(graph)
    ast.parse(code)


@pytest.mark.parametrize("defn_cls,params", _COMBINE_CASES)
def test_deduplicate_and_sort_codegen_is_ruff_clean(defn_cls, params):
    graph = _build_single_input_graph(defn_cls, **params)
    code = compile_to_code(graph)
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "-"],
        input=code,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_concat_codegen_is_parseable():
    load_a = LoadSample().instantiate(name="iris", label="Load A")
    load_b = LoadSample().instantiate(name="iris", label="Load B")
    concat_node = Concat().instantiate(label=Concat.label)

    edge_a = Edge(
        source=PortRef(node_id=load_a.id, port_id=_out_port(load_a, "frame").id),
        target=PortRef(node_id=concat_node.id, port_id=_in_port(concat_node, "frames").id),
    )
    edge_b = Edge(
        source=PortRef(node_id=load_b.id, port_id=_out_port(load_b, "frame").id),
        target=PortRef(node_id=concat_node.id, port_id=_in_port(concat_node, "frames").id),
    )
    graph = Graph(
        nodes={load_a.id: load_a, load_b.id: load_b, concat_node.id: concat_node},
        edges={edge_a.id: edge_a, edge_b.id: edge_b},
    )

    code = compile_to_code(graph)
    ast.parse(code)
    assert "[" in code.split("ef.clean.concat(")[1].split(")")[0]
