"""Tests for the thin local server (ADR 0013, §A6).

Exercises the in-process service functions and the stdlib HTTP layer end to end:
build a real IR graph, round-trip it through serialize, and confirm
compile / validate / execute return JSON-safe payloads -- proving the
canvas -> IR -> code/execute loop that the bundled ``colonymind serve`` exposes.
No torch, no network, no fixtures beyond the bundled sample CSV.
"""

from __future__ import annotations

import json
import pathlib
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator

import pytest

from colonymind.ir import (
    Direction,
    Graph,
    Node,
    Paradigm,
    Param,
    Port,
    Position,
)
from colonymind.ir.edge import Edge, PortRef
from colonymind.ir.serialize import serialize_graph
from colonymind.server import compile_graph, execute_graph, make_server, validate_graph

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
        name="server-test",
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
        name="server-test-chain",
        nodes={load.id: load, impute.id: impute},
        edges={edge.id: edge},
    )
    return json.loads(serialize_graph(graph))


# ---------------------------------------------------------------------------
# Service layer (no HTTP)
# ---------------------------------------------------------------------------


def test_compile_graph_returns_runnable_code() -> None:
    out = compile_graph(_load_csv_graph())
    assert "import colonymind as cm" in out["code"]
    assert "load_csv" in out["code"]


def test_validate_graph_returns_json_native_diagnostics() -> None:
    out = validate_graph(_load_csv_graph())
    assert "diagnostics" in out
    json.dumps(out)  # JSON-native: encodes without a custom encoder


def test_execute_graph_runs_in_process_and_is_json_safe() -> None:
    out = execute_graph(_load_csv_graph())
    assert "n-load" in out["results"]
    json.dumps(out)  # DataFrame result must be coerced to JSON-safe data
    assert out["payload_version"] == 1
    frame = out["results"]["n-load"]["frame"]
    assert frame["kind"] == "table"
    # the table payload carries the Story 3 contract fields
    assert set(frame) >= {"columns", "dtypes", "shape", "head", "truncated"}
    assert frame["shape"][1] == len(frame["columns"]) == len(frame["dtypes"])
    assert isinstance(frame["head"], list)
    assert frame["truncated"] is False  # sample.csv has 30 rows (< 50)


def test_execute_graph_reports_per_node_status_ok() -> None:
    out = execute_graph(_chain_graph())
    assert out["statuses"]["n-load"]["status"] == "ok"
    assert out["statuses"]["n-impute"]["status"] == "ok"
    assert "n-load" in out["results"]
    assert "n-impute" in out["results"]
    json.dumps(out)  # results + statuses must be JSON-native
    assert out["payload_version"] == 1
    assert out["results"]["n-load"]["frame"]["kind"] == "table"
    assert out["results"]["n-impute"]["frame"]["kind"] == "table"


def test_execute_graph_reports_error_and_skipped() -> None:
    out = execute_graph(_chain_graph(path="/no/such/file.csv"))
    assert out["statuses"]["n-load"]["status"] == "error"
    assert "FileNotFoundError" in out["statuses"]["n-load"]["error"]
    assert out["statuses"]["n-impute"]["status"] == "skipped"
    # A node that errored or was skipped produces no results.
    assert "n-load" not in out["results"]
    assert "n-impute" not in out["results"]
    json.dumps(out)


def test_execute_graph_rejects_unconnected_input_graph() -> None:
    # A graph-LEVEL problem (impute's required IN port has no upstream) must RAISE,
    # not come back as a per-node status -- the whole graph cannot run.
    impute_only = _chain_graph()
    impute_only["edges"] = {}  # drop the load->impute edge
    impute_only["nodes"] = {k: v for k, v in impute_only["nodes"].items() if k == "n-impute"}
    with pytest.raises(Exception):  # noqa: B017,PT011 - any graph-level rejection -> 422
        execute_graph(impute_only)


# ---------------------------------------------------------------------------
# HTTP layer (stdlib server on an ephemeral port)
# ---------------------------------------------------------------------------


@pytest.fixture
def base_url() -> Iterator[str]:
    httpd = make_server("127.0.0.1", 0)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join()


def _post(base: str, path: str, payload: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        base + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:  # noqa: S310 - localhost test client
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_healthz(base_url: str) -> None:
    with urllib.request.urlopen(base_url + "/healthz") as resp:  # noqa: S310
        assert resp.status == 200
        assert json.loads(resp.read()) == {"status": "ok"}


def test_index_page_served(base_url: str) -> None:
    with urllib.request.urlopen(base_url + "/") as resp:  # noqa: S310
        assert resp.status == 200
        assert b"Colony Mind" in resp.read()


def test_http_compile_and_execute(base_url: str) -> None:
    status, body = _post(base_url, "/compile", _load_csv_graph())
    assert status == 200
    assert "import colonymind as cm" in body["code"]

    status, body = _post(base_url, "/execute", _load_csv_graph())
    assert status == 200
    assert "n-load" in body["results"]
    assert body["payload_version"] == 1
    assert body["results"]["n-load"]["frame"]["kind"] == "table"


def test_http_execute_node_error_reports_per_node_status(base_url: str) -> None:
    # A node-runtime failure (bad CSV path) is reported per-node at HTTP 200 so the
    # canvas can colour just that node red -- the server never crashes.
    status, body = _post(base_url, "/execute", _load_csv_graph(path="/no/such/file.csv"))
    assert status == 200
    assert body["statuses"]["n-load"]["status"] == "error"
    assert "n-load" not in body["results"]


def test_http_execute_unconnected_input_is_422(base_url: str) -> None:
    payload = _chain_graph()
    payload["edges"] = {}
    payload["nodes"] = {k: v for k, v in payload["nodes"].items() if k == "n-impute"}
    status, body = _post(base_url, "/execute", payload)
    assert status == 422
    assert "error" in body


def test_http_unknown_route_is_404(base_url: str) -> None:
    status, body = _post(base_url, "/nope", {})
    assert status == 404
    assert "error" in body
