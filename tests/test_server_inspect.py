"""Tests for the /inspect server endpoint (issue #95: variable inspector).

Exercises the in-process inspect_graph service function and the HTTP route:
build a real IR graph, round-trip it, and confirm every step trace is
JSON-safe with correct variable bindings.
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from emergentflow.ir import Direction, Graph, Node, Paradigm, Param, Port, Position
from emergentflow.ir.edge import Edge, PortRef
from emergentflow.ir.serialize import serialize_graph
from emergentflow.server import app
from emergentflow.server.payload import PAYLOAD_CONTRACT_VERSION
from emergentflow.server.service import inspect_graph

SAMPLE_CSV = (
    pathlib.Path(__file__).resolve().parents[1] / "examples" / "vertical_slice" / "sample.csv"
)


def _load_csv_graph(path: str | None = None) -> dict:
    """A minimal one-node functional graph that loads the bundled sample CSV."""
    node = Node(
        id="n-load",
        type="data.load_csv",
        label="Load CSV",
        paradigm=Paradigm.FUNCTIONAL,
        params=[Param(name="path", type_token="str", value=path or str(SAMPLE_CSV))],
        ports=[
            Port(
                id="p-load-frame",
                name="frame",
                direction=Direction.OUT,
                data_type="DataFrame",
            ),
        ],
        position=Position(x=0.0, y=0.0),
    )
    graph = Graph(
        paradigm=Paradigm.FUNCTIONAL,
        name="server-inspect-test",
        nodes={node.id: node},
        edges={},
    )
    return json.loads(serialize_graph(graph))


def _chain_graph(path: str | None = None) -> dict:
    """A two-node functional chain: load_csv -> impute_missing (frame -> frame)."""
    load = Node(
        id="n-load",
        type="data.load_csv",
        label="Load CSV",
        paradigm=Paradigm.FUNCTIONAL,
        params=[Param(name="path", type_token="str", value=path or str(SAMPLE_CSV))],
        ports=[
            Port(id="p-load-frame", name="frame", direction=Direction.OUT, data_type="DataFrame"),
        ],
        position=Position(x=0.0, y=0.0),
    )
    impute = Node(
        id="n-impute",
        type="clean.impute_missing",
        label="Impute Missing",
        paradigm=Paradigm.FUNCTIONAL,
        params=[Param(name="strategy", type_token="str", value="mean")],
        ports=[
            Port(id="p-imp-in", name="frame", direction=Direction.IN, data_type="DataFrame"),
            Port(id="p-imp-out", name="frame", direction=Direction.OUT, data_type="DataFrame"),
        ],
        position=Position(x=1.0, y=0.0),
    )
    edge = Edge(
        id="e-load-impute",
        source=PortRef(node_id="n-load", port_id="p-load-frame"),
        target=PortRef(node_id="n-impute", port_id="p-imp-in"),
    )
    graph = Graph(
        paradigm=Paradigm.FUNCTIONAL,
        name="server-inspect-chain",
        nodes={load.id: load, impute.id: impute},
        edges={edge.id: edge},
    )
    return json.loads(serialize_graph(graph))


# ---------------------------------------------------------------------------
# Service layer (no HTTP)
# ---------------------------------------------------------------------------


def test_inspect_graph_single_node() -> None:
    out = inspect_graph(_load_csv_graph())
    assert out["payload_version"] == PAYLOAD_CONTRACT_VERSION
    assert len(out["steps"]) == 1
    step = out["steps"][0]
    assert step["node_id"] == "n-load"
    assert step["status"] == "ok"
    assert step["inputs"] == []
    assert len(step["outputs"]) == 1
    assert step["outputs"][0]["payload"]["kind"] == "table"
    json.dumps(out, separators=(",", ":"))


def test_inspect_graph_two_node_chain() -> None:
    out = inspect_graph(_chain_graph())
    assert len(out["steps"]) == 2
    assert out["steps"][0]["node_id"] == "n-load"
    assert out["steps"][1]["node_id"] == "n-impute"
    assert out["steps"][0]["status"] == "ok"
    assert out["steps"][1]["status"] == "ok"
    # The second step's single input var_name equals the first step's single output var_name
    load_output_var = out["steps"][0]["outputs"][0]["var_name"]
    impute_input_var = out["steps"][1]["inputs"][0]["var_name"]
    assert impute_input_var == load_output_var


def test_inspect_graph_rejects_unconnected_input() -> None:
    payload = _chain_graph()
    payload["edges"] = {}
    payload["nodes"] = {k: v for k, v in payload["nodes"].items() if k == "n-impute"}
    with pytest.raises(Exception):  # noqa: B017,PT011 - any graph-level rejection -> 422
        inspect_graph(payload)


# ---------------------------------------------------------------------------
# HTTP layer (FastAPI TestClient)
# ---------------------------------------------------------------------------


@pytest.fixture
def client() -> Iterator[TestClient]:
    """A FastAPI test client over the module-level ``app`` (no real socket)."""
    with TestClient(app) as test_client:
        yield test_client


def test_http_inspect_returns_steps(client: TestClient) -> None:
    resp = client.post("/inspect", json=_load_csv_graph())
    assert resp.status_code == 200
    body = resp.json()
    assert "steps" in body
    assert len(body["steps"]) == 1
    assert body["steps"][0]["node_id"] == "n-load"
    assert body["payload_version"] == PAYLOAD_CONTRACT_VERSION
