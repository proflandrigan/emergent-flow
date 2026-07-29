"""
Tests for the ``clean.derive_column`` reference node (Epic 16, Story 6).

Covers:
1. Node instantiation and metadata
2. Execute produces correct output for expression / case-when columns
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
from emergentflow.nodes.examples import DeriveColumn, LoadSample


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
            "revenue": [1500.0, 500.0, 50.0, 0.0],
            "cost": [500.0, 200.0, 20.0, 0.0],
        }
    )


_EXPR_SPEC = [{"name": "margin", "expr": "revenue - cost"}]
_CASE_SPEC = [
    {
        "name": "tier",
        "when": [
            {"if": "revenue > 1000", "then": "gold"},
            {"if": "revenue > 100", "then": "silver"},
        ],
        "else": "bronze",
    }
]


# ---------------------------------------------------------------------------
# 1. Node metadata
# ---------------------------------------------------------------------------


def test_derive_column_node_metadata():
    defn = DeriveColumn()
    assert defn.type == "clean.derive_column"
    assert defn.family == "clean"
    assert defn.version == 1

    in_ports = [p for p in defn.ports if p.direction == Direction.IN]
    out_ports = [p for p in defn.ports if p.direction == Direction.OUT]
    assert len(in_ports) == 1
    assert len(out_ports) == 1
    assert in_ports[0].name == "frame"
    assert out_ports[0].name == "frame"

    assert len(defn.params) == 1
    assert defn.params[0].name == "columns"


# ---------------------------------------------------------------------------
# 2. Execute
# ---------------------------------------------------------------------------


def test_derive_column_execute_expression():
    defn = DeriveColumn()
    node = defn.instantiate(columns=_EXPR_SPEC)

    result = defn.execute(node, inputs={"frame": _df()})
    assert "frame" in result
    out = result["frame"]
    assert list(out["margin"]) == [1000, 300, 30, 0]


def test_derive_column_execute_case_when():
    defn = DeriveColumn()
    node = defn.instantiate(columns=_CASE_SPEC)

    result = defn.execute(node, inputs={"frame": _df()})
    assert "frame" in result
    out = result["frame"]
    assert list(out["tier"]) == ["gold", "silver", "bronze", "bronze"]


# ---------------------------------------------------------------------------
# 3. ADR-0002 equivalence
# ---------------------------------------------------------------------------


@pytest.mark.equivalence
def test_derive_column_expression_equivalence():
    defn = DeriveColumn()
    node = defn.instantiate(columns=_EXPR_SPEC)

    executed = defn.execute(node, inputs={"frame": _df()})
    scope = _run_codegen(defn, node, {"frame": _df()})

    pd.testing.assert_frame_equal(executed["frame"], scope["frame"])


@pytest.mark.equivalence
def test_derive_column_case_when_equivalence():
    defn = DeriveColumn()
    node = defn.instantiate(columns=_CASE_SPEC)

    executed = defn.execute(node, inputs={"frame": _df()})
    scope = _run_codegen(defn, node, {"frame": _df()})

    pd.testing.assert_frame_equal(executed["frame"], scope["frame"])


# ---------------------------------------------------------------------------
# 4. Codegen quality
# ---------------------------------------------------------------------------


def _build_derive_graph(columns):
    load = LoadSample().instantiate(name="iris", label="Load Sample")
    derive_node = DeriveColumn().instantiate(label=DeriveColumn.label, columns=columns)
    edge = Edge(
        source=PortRef(node_id=load.id, port_id=_out_port(load, "frame").id),
        target=PortRef(node_id=derive_node.id, port_id=_in_port(derive_node, "frame").id),
    )
    return Graph(
        nodes={load.id: load, derive_node.id: derive_node},
        edges={edge.id: edge},
    )


_DERIVE_CASES = [_EXPR_SPEC, _CASE_SPEC]


@pytest.mark.parametrize("columns", _DERIVE_CASES)
def test_derive_column_codegen_is_parseable(columns):
    graph = _build_derive_graph(columns)
    code = compile_to_code(graph)
    ast.parse(code)


@pytest.mark.parametrize("columns", _DERIVE_CASES)
def test_derive_column_codegen_is_ruff_clean(columns):
    graph = _build_derive_graph(columns)
    code = compile_to_code(graph)
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "-"],
        input=code,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
