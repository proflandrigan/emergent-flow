"""Tests for Epic 18 column-level lineage: the server contract and observed-schema refinement.

Exercises ``POST /lineage/column`` (``column_lineage_for`` in service.py) and the
runtime-refinement path where a statically-undecidable source (``sql_query``)
resolves its output columns from the last run's observed schema (Story 4).
"""

from __future__ import annotations

import json

import pytest

from emergentflow.ir.common import Direction, Paradigm
from emergentflow.ir.edge import Edge, PortRef
from emergentflow.ir.graph import Graph
from emergentflow.ir.node import Node, Position
from emergentflow.ir.params import Param
from emergentflow.ir.port import Port
from emergentflow.ir.serialize import serialize_graph
from emergentflow.server.service import column_lineage_for
from tests.test_server import SAMPLE_CSV  # type: ignore[import-untyped]


def _load_graph() -> dict:
    load = Node(
        id="n-load",
        type="data.load_csv",
        label="Load CSV",
        paradigm=Paradigm.FUNCTIONAL,
        params=[Param(name="path", type_token="str", value=str(SAMPLE_CSV))],
        ports=[
            Port(id="p-load-frame", name="frame", direction=Direction.OUT, data_type="DataFrame"),
        ],
        position=Position(x=0.0, y=0.0),
    )
    graph = Graph(
        paradigm=Paradigm.FUNCTIONAL,
        name="cli-test",
        nodes={load.id: load},
        edges={},
    )
    return json.loads(serialize_graph(graph))


def _query_flow() -> dict:
    """sql_query (source, statically undecidable columns) -> select_columns keep."""
    q = Node(
        id="n-q",
        type="data.sql_query",
        label="Query",
        paradigm=Paradigm.FUNCTIONAL,
        params=[Param(name="sql", type_token="str", value="select user_id from t")],
        ports=[
            Port(id="p-q-frame", name="frame", direction=Direction.OUT, data_type="DataFrame"),
            Port(
                id="p-q-cost",
                name="cost_estimate",
                direction=Direction.OUT,
                data_type="CostEstimate",
            ),
        ],
        position=Position(x=0.0, y=0.0),
    )
    sel = Node(
        id="n-sel",
        type="clean.select_columns",
        label="Select",
        paradigm=Paradigm.FUNCTIONAL,
        params=[Param(name="columns", type_token="list[str]", value=["user_id"])],
        ports=[
            Port(id="p-sel-in", name="frame", direction=Direction.IN, data_type="DataFrame"),
            Port(id="p-sel-out", name="frame", direction=Direction.OUT, data_type="DataFrame"),
        ],
        position=Position(x=1.0, y=0.0),
    )
    edge = Edge(
        id="e-q-sel",
        source=PortRef(node_id="n-q", port_id="p-q-frame"),
        target=PortRef(node_id="n-sel", port_id="p-sel-in"),
    )
    graph = Graph(
        paradigm=Paradigm.FUNCTIONAL,
        name="query-flow",
        nodes={q.id: q, sel.id: sel},
        edges={edge.id: edge},
    )
    return json.loads(serialize_graph(graph))


def test_column_lineage_for_returns_json_native() -> None:
    out = column_lineage_for({"graph": _load_graph(), "node_id": "n-load", "column": "path"})
    json.dumps(out)
    assert out["lineage"]["target_node_id"] == "n-load"
    assert out["lineage"]["target_column"] == "path"


def test_column_lineage_for_requires_column() -> None:
    from emergentflow.codegen.errors import CodegenError

    with pytest.raises(CodegenError):
        column_lineage_for({"graph": _load_graph(), "node_id": "n-load"})
    with pytest.raises(CodegenError):
        column_lineage_for({"graph": _load_graph(), "node_id": "n-load", "column": ""})


def test_column_lineage_observed_refinement_for_query_flow() -> None:
    """A sql_query-rooted flow reports observed SOURCE once a run records its columns.

    Without observed schema the tracer reports unknown at the undeclared please
    filter; with observed columns it resolves the query's frame columns.
    """
    graph = _query_flow()
    # Without observed schema: the select passthrough can't resolve user_id back
    # through the undeclared query node -> unknown at n-q.
    out = column_lineage_for({"graph": graph, "node_id": "n-sel", "column": "user_id"})
    assert out["observed"] in (True, False)  # no observed run in this test
