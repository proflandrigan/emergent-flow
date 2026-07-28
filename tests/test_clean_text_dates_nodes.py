"""
Tests for the ``clean.clean_text`` / ``clean.parse_dates`` reference nodes (Epic 16, Story 8).

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
from emergentflow.nodes.examples import CleanText, LoadSample, ParseDates


def _out_port(node, name):
    return next(p for p in node.ports if p.direction == Direction.OUT and p.name == name)


def _in_port(node, name):
    return next(p for p in node.ports if p.direction == Direction.IN and p.name == name)


def _run_codegen(definition, node, scope):
    frag = definition.preview(node)
    exec(frag.render(), scope)  # noqa: S102
    return scope


def _text_df() -> pd.DataFrame:
    return pd.DataFrame(
        {"name": ["  Alice  ", "BOB", "carol dee"], "code": ["id-123", "id-4", "id-56"]}
    )


def _date_df() -> pd.DataFrame:
    return pd.DataFrame({"when": ["2024-01-15", "2024-06-30", "2023-12-01"], "n": [1, 2, 3]})


_TEXT_OPS = [{"op": "trim"}, {"op": "lower"}]


# ---------------------------------------------------------------------------
# 1. Node metadata
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "defn_cls,expected_type",
    [
        (CleanText, "clean.clean_text"),
        (ParseDates, "clean.parse_dates"),
    ],
)
def test_text_date_node_metadata(defn_cls, expected_type):
    defn = defn_cls()
    assert defn.type == expected_type
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


def test_clean_text_execute():
    defn = CleanText()
    node = defn.instantiate(columns=["name"], operations=_TEXT_OPS)

    result = defn.execute(node, inputs={"frame": _text_df()})
    out = result["frame"]
    assert list(out["name"]) == ["alice", "bob", "carol dee"]


def test_clean_text_execute_with_suffix():
    defn = CleanText()
    node = defn.instantiate(columns=["name"], operations=_TEXT_OPS, suffix="_clean")

    result = defn.execute(node, inputs={"frame": _text_df()})
    out = result["frame"]
    assert "name" in out.columns
    assert "name_clean" in out.columns


def test_parse_dates_execute():
    defn = ParseDates()
    node = defn.instantiate(columns=["when"], components=["year"])

    result = defn.execute(node, inputs={"frame": _date_df()})
    out = result["frame"]
    assert list(out["when_year"]) == [2024, 2024, 2023]
    assert pd.api.types.is_datetime64_any_dtype(out["when"])


# ---------------------------------------------------------------------------
# 3. ADR-0002 equivalence
# ---------------------------------------------------------------------------


@pytest.mark.equivalence
def test_clean_text_equivalence():
    defn = CleanText()
    node = defn.instantiate(columns=["name"], operations=_TEXT_OPS)

    executed = defn.execute(node, inputs={"frame": _text_df()})
    scope = _run_codegen(defn, node, {"frame": _text_df()})

    pd.testing.assert_frame_equal(executed["frame"], scope["frame"])


@pytest.mark.equivalence
def test_parse_dates_equivalence():
    defn = ParseDates()
    node = defn.instantiate(columns=["when"], components=["year"])

    executed = defn.execute(node, inputs={"frame": _date_df()})
    scope = _run_codegen(defn, node, {"frame": _date_df()})

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


_TEXT_DATE_CASES = [
    (CleanText, {"columns": ["species"], "operations": _TEXT_OPS}),
    (ParseDates, {"columns": ["species"]}),
]


@pytest.mark.parametrize("defn_cls,params", _TEXT_DATE_CASES)
def test_text_date_codegen_is_parseable(defn_cls, params):
    graph = _build_single_input_graph(defn_cls, **params)
    code = compile_to_code(graph)
    ast.parse(code)


@pytest.mark.parametrize("defn_cls,params", _TEXT_DATE_CASES)
def test_text_date_codegen_is_ruff_clean(defn_cls, params):
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
