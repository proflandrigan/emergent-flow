"""
Tests for the ``clean.reshape`` reference node (Epic 16, Story 5).

Covers:
1. Node instantiation and metadata
2. Execute produces correct output for pivot / melt
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
from emergentflow.nodes.examples import LoadSample, Reshape


def _out_port(node, name):
    return next(p for p in node.ports if p.direction == Direction.OUT and p.name == name)


def _in_port(node, name):
    return next(p for p in node.ports if p.direction == Direction.IN and p.name == name)


def _run_codegen(definition, node, scope):
    frag = definition.preview(node)
    exec(frag.render(), scope)  # noqa: S102
    return scope


def _long_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": ["2024-01-01", "2024-01-01", "2024-01-02", "2024-01-02"],
            "metric": ["clicks", "views", "clicks", "views"],
            "amount": [3, 10, 5, 12],
        }
    )


def _wide_df() -> pd.DataFrame:
    return pd.DataFrame({"date": ["2024-01-01", "2024-01-02"], "clicks": [3, 5], "views": [10, 12]})


# ---------------------------------------------------------------------------
# 1. Node metadata
# ---------------------------------------------------------------------------


def test_reshape_node_metadata():
    defn = Reshape()
    assert defn.type == "clean.reshape"
    assert defn.family == "clean"
    assert defn.version == 1

    in_ports = [p for p in defn.ports if p.direction == Direction.IN]
    out_ports = [p for p in defn.ports if p.direction == Direction.OUT]
    assert len(in_ports) == 1
    assert len(out_ports) == 1
    assert in_ports[0].name == "frame"
    assert out_ports[0].name == "frame"


# ---------------------------------------------------------------------------
# 2. Execute
# ---------------------------------------------------------------------------


def test_reshape_pivot_execute():
    defn = Reshape()
    node = defn.instantiate(mode="pivot", index=["date"], columns=["metric"], values=["amount"])

    result = defn.execute(node, inputs={"frame": _long_df()})
    assert "frame" in result
    out = result["frame"]
    assert list(out.columns) == ["date", "amount_clicks", "amount_views"]
    assert all(isinstance(c, str) for c in out.columns)


def test_reshape_melt_execute():
    defn = Reshape()
    node = defn.instantiate(mode="melt", id_vars=["date"], value_vars=["clicks", "views"])

    result = defn.execute(node, inputs={"frame": _wide_df()})
    assert "frame" in result
    out = result["frame"]
    assert "variable" in out.columns
    assert "value" in out.columns


# ---------------------------------------------------------------------------
# 3. ADR-0002 equivalence
# ---------------------------------------------------------------------------


@pytest.mark.equivalence
def test_reshape_pivot_equivalence():
    defn = Reshape()
    node = defn.instantiate(mode="pivot", index=["date"], columns=["metric"], values=["amount"])

    executed = defn.execute(node, inputs={"frame": _long_df()})
    scope = _run_codegen(defn, node, {"frame": _long_df()})

    pd.testing.assert_frame_equal(executed["frame"], scope["frame"])


@pytest.mark.equivalence
def test_reshape_melt_equivalence():
    defn = Reshape()
    node = defn.instantiate(mode="melt", id_vars=["date"], value_vars=["clicks", "views"])

    executed = defn.execute(node, inputs={"frame": _wide_df()})
    scope = _run_codegen(defn, node, {"frame": _wide_df()})

    pd.testing.assert_frame_equal(executed["frame"], scope["frame"])


# ---------------------------------------------------------------------------
# 4. Codegen quality
# ---------------------------------------------------------------------------


def _build_reshape_graph(**params):
    load = LoadSample().instantiate(name="iris", label="Load Sample")
    reshape_node = Reshape().instantiate(label=Reshape.label, **params)
    edge = Edge(
        source=PortRef(node_id=load.id, port_id=_out_port(load, "frame").id),
        target=PortRef(node_id=reshape_node.id, port_id=_in_port(reshape_node, "frame").id),
    )
    return Graph(
        nodes={load.id: load, reshape_node.id: reshape_node},
        edges={edge.id: edge},
    )


_RESHAPE_CASES = [
    {"mode": "pivot", "index": ["date"], "columns": ["metric"], "values": ["amount"]},
    {"mode": "melt", "id_vars": ["date"], "value_vars": ["clicks", "views"]},
]


@pytest.mark.parametrize("params", _RESHAPE_CASES)
def test_reshape_codegen_is_parseable(params):
    graph = _build_reshape_graph(**params)
    code = compile_to_code(graph)
    ast.parse(code)


@pytest.mark.parametrize("params", _RESHAPE_CASES)
def test_reshape_codegen_is_ruff_clean(params):
    graph = _build_reshape_graph(**params)
    code = compile_to_code(graph)
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "-"],
        input=code,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
