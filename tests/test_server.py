"""Tests for the thin local server (ADR 0013, §A6).

Exercises the in-process service functions and the stdlib HTTP layer end to end:
build a real IR graph, round-trip it through serialize, and confirm
compile / validate / execute return JSON-safe payloads -- proving the
canvas -> IR -> code/execute loop that the bundled ``emergentflow serve`` exposes.
No torch, no network, no fixtures beyond the bundled sample CSV.
"""

from __future__ import annotations

import contextlib
import json
import pathlib
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator

import pytest

from emergentflow.ir import (
    Direction,
    Graph,
    Node,
    Paradigm,
    Param,
    Port,
    Position,
)
from emergentflow.ir.edge import Edge, PortRef
from emergentflow.ir.schema import ir_json_schema
from emergentflow.ir.serialize import serialize_graph
from emergentflow.server import (
    compile_graph,
    execute_graph,
    execute_node,
    get_catalog,
    get_schema,
    make_server,
    validate_graph,
)

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


def _fanout_graph(path: str | None = None) -> dict:
    """A fan-out functional graph: load_csv -> {impute_b, impute_c} (frame -> frame)."""
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
    impute_b = Node(
        id="n-impute-b",
        type="clean.impute_missing",
        label="Impute Missing B",
        paradigm=Paradigm.FUNCTIONAL,
        params=[Param(name="strategy", type_token="str", value="mean")],
        ports=[
            Port(id="p-impb-in", name="frame", direction=Direction.IN, data_type="DataFrame"),
            Port(id="p-impb-out", name="frame", direction=Direction.OUT, data_type="DataFrame"),
        ],
        position=Position(x=1.0, y=0.0),
    )
    impute_c = Node(
        id="n-impute-c",
        type="clean.impute_missing",
        label="Impute Missing C",
        paradigm=Paradigm.FUNCTIONAL,
        params=[Param(name="strategy", type_token="str", value="mean")],
        ports=[
            Port(id="p-impc-in", name="frame", direction=Direction.IN, data_type="DataFrame"),
            Port(id="p-impc-out", name="frame", direction=Direction.OUT, data_type="DataFrame"),
        ],
        position=Position(x=1.0, y=1.0),
    )
    edge_b = Edge(
        id="e-load-impute-b",
        source=PortRef(node_id="n-load", port_id="p-load-frame"),
        target=PortRef(node_id="n-impute-b", port_id="p-impb-in"),
    )
    edge_c = Edge(
        id="e-load-impute-c",
        source=PortRef(node_id="n-load", port_id="p-load-frame"),
        target=PortRef(node_id="n-impute-c", port_id="p-impc-in"),
    )
    graph = Graph(
        paradigm=Paradigm.FUNCTIONAL,
        name="server-test-fanout",
        nodes={load.id: load, impute_b.id: impute_b, impute_c.id: impute_c},
        edges={edge_b.id: edge_b, edge_c.id: edge_c},
    )
    return json.loads(serialize_graph(graph))


# ---------------------------------------------------------------------------
# Service layer (no HTTP)
# ---------------------------------------------------------------------------


def test_compile_graph_returns_runnable_code() -> None:
    out = compile_graph(_load_csv_graph())
    assert "import emergentflow as ef" in out["code"]
    assert "load_csv" in out["code"]


def test_validate_graph_returns_json_native_diagnostics() -> None:
    out = validate_graph(_load_csv_graph())
    assert "diagnostics" in out
    json.dumps(out)  # JSON-native: encodes without a custom encoder


def test_execute_graph_runs_in_process_and_is_json_safe() -> None:
    out = execute_graph(_load_csv_graph())
    assert "n-load" in out["results"]
    json.dumps(out)  # DataFrame result must be coerced to JSON-safe data
    assert out["payload_version"] == 2
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
    assert out["payload_version"] == 2
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


def test_execute_graph_run_to_executes_only_subgraph() -> None:
    out = execute_graph({"graph": _fanout_graph(), "run_to": "n-impute-b"})
    assert set(out["statuses"]) == {"n-load", "n-impute-b"}
    assert "n-impute-c" not in out["results"]
    assert "n-impute-c" not in out["statuses"]
    assert out["statuses"]["n-impute-b"]["status"] == "ok"


def test_execute_graph_bare_body_still_runs_whole_graph() -> None:
    out = execute_graph(_fanout_graph())  # no envelope
    assert set(out["statuses"]) == {"n-load", "n-impute-b", "n-impute-c"}


def test_execute_graph_run_to_unknown_target_raises() -> None:
    with pytest.raises(Exception):  # noqa: B017,PT011
        execute_graph({"graph": _fanout_graph(), "run_to": "n-nope"})


def test_execute_node_runs_single_source_node() -> None:
    # n-load is a source node (no IN ports): runs with inputs={} by default.
    out = execute_node({"graph": _load_csv_graph(), "run_node": "n-load"})
    assert out["statuses"]["n-load"]["status"] == "ok"
    assert out["results"]["n-load"]["frame"]["kind"] == "table"
    assert out["payload_version"] == 2
    json.dumps(out)  # JSON-native


def test_execute_node_runtime_error_is_per_node_status() -> None:
    out = execute_node({"graph": _load_csv_graph(path="/no/such/file.csv"), "run_node": "n-load"})
    assert out["statuses"]["n-load"]["status"] == "error"
    assert "n-load" not in out["results"]


def test_execute_node_missing_run_node_raises() -> None:
    with pytest.raises(Exception):  # noqa: B017,PT011
        execute_node({"graph": _load_csv_graph()})


def test_execute_node_unknown_node_raises() -> None:
    with pytest.raises(Exception):  # noqa: B017,PT011
        execute_node({"graph": _load_csv_graph(), "run_node": "n-nope"})


def test_execute_node_rejects_non_dict_inputs_even_when_falsy() -> None:
    # `inputs: []` is falsy but not a dict; it must surface the envelope-validation
    # error rather than being silently defaulted to {} and masked.
    with pytest.raises(Exception):  # noqa: B017,PT011
        execute_node({"graph": _load_csv_graph(), "run_node": "n-load", "inputs": []})


def test_execute_node_rejects_declarative_node() -> None:
    # A DECLARATIVE node's execute() returns the bare layer object for the whole-graph
    # declarative executor to compose, not a computed result -- running it standalone
    # must raise rather than silently "succeed" with that meaningless object.
    graph = _load_csv_graph()
    graph["nodes"]["n-load"]["paradigm"] = "declarative"
    with pytest.raises(Exception):  # noqa: B017,PT011
        execute_node({"graph": graph, "run_node": "n-load"})


def test_get_schema_returns_ir_schema() -> None:
    out = get_schema()
    assert out == ir_json_schema()
    assert isinstance(out, dict)
    assert out  # non-empty
    assert "properties" in out or "$defs" in out


def test_get_catalog_lists_registered_nodes() -> None:
    nodes = get_catalog()["nodes"]
    assert nodes  # non-empty
    for spec in nodes:
        assert {"type", "family", "label", "ports", "params"} <= set(spec)
    assert "data.load_csv" in {spec["type"] for spec in nodes}


# ---------------------------------------------------------------------------
# HTTP layer (stdlib server on an ephemeral port)
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def _running(httpd) -> Iterator[str]:
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join()


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
        assert b"Emergent Flow" in resp.read()


def test_static_index_served_when_present(tmp_path, monkeypatch) -> None:
    import emergentflow.server.app as app_mod

    static_dir = tmp_path / "_static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html><body>BUNDLED CANVAS</body></html>")
    monkeypatch.setattr(app_mod, "_STATIC_DIR", static_dir.resolve())
    with (
        _running(make_server("127.0.0.1", 0)) as base,
        urllib.request.urlopen(base + "/") as resp,  # noqa: S310
    ):
        assert resp.status == 200
        assert b"BUNDLED CANVAS" in resp.read()


def test_static_asset_served_with_content_type(tmp_path, monkeypatch) -> None:
    import emergentflow.server.app as app_mod

    static_dir = tmp_path / "_static"
    (static_dir / "assets").mkdir(parents=True)
    (static_dir / "assets" / "app.js").write_text("console.log('hi');")
    monkeypatch.setattr(app_mod, "_STATIC_DIR", static_dir.resolve())
    with (
        _running(make_server("127.0.0.1", 0)) as base,
        urllib.request.urlopen(base + "/assets/app.js") as resp,  # noqa: S310
    ):
        assert resp.status == 200
        assert "javascript" in resp.headers["Content-Type"]
        assert b"console.log" in resp.read()


def test_demo_page_when_static_absent(tmp_path, monkeypatch) -> None:
    import emergentflow.server.app as app_mod

    monkeypatch.setattr(app_mod, "_STATIC_DIR", (tmp_path / "_static").resolve())
    with (
        _running(make_server("127.0.0.1", 0)) as base,
        urllib.request.urlopen(base + "/") as resp,  # noqa: S310
    ):
        assert resp.status == 200
        assert b"Emergent Flow" in resp.read()


def test_static_file_blocks_directory_traversal(tmp_path, monkeypatch) -> None:
    import emergentflow.server.app as app_mod

    static_dir = tmp_path / "_static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("ok")
    (tmp_path / "secret.txt").write_text("SECRET")
    monkeypatch.setattr(app_mod, "_STATIC_DIR", static_dir.resolve())
    # A traversal path must not resolve to a file outside _static/.
    assert app_mod._static_file("/../secret.txt") is None
    assert app_mod._static_file("/nope.js") is None
    assert app_mod._static_file("/index.html") is not None


def test_open_browser_invokes_webbrowser(monkeypatch) -> None:
    import emergentflow.server.app as app_mod

    opened: list[str] = []
    monkeypatch.setattr(app_mod.webbrowser, "open", lambda url, *a, **k: opened.append(url))
    app_mod._open_browser("http://127.0.0.1:8765")
    assert opened == ["http://127.0.0.1:8765"]


def test_open_browser_swallows_errors(monkeypatch) -> None:
    import emergentflow.server.app as app_mod

    def boom(url, *a, **k):
        raise RuntimeError("no browser on this host")

    monkeypatch.setattr(app_mod.webbrowser, "open", boom)
    app_mod._open_browser("http://127.0.0.1:8765")  # must NOT raise


def test_http_compile_and_execute(base_url: str) -> None:
    status, body = _post(base_url, "/compile", _load_csv_graph())
    assert status == 200
    assert "import emergentflow as ef" in body["code"]

    status, body = _post(base_url, "/execute", _load_csv_graph())
    assert status == 200
    assert "n-load" in body["results"]
    assert body["payload_version"] == 2
    assert body["results"]["n-load"]["frame"]["kind"] == "table"


def test_http_execute_node(base_url: str) -> None:
    status, body = _post(
        base_url, "/execute_node", {"graph": _load_csv_graph(), "run_node": "n-load"}
    )
    assert status == 200
    assert body["statuses"]["n-load"]["status"] == "ok"
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


def test_http_get_schema(base_url: str) -> None:
    with urllib.request.urlopen(base_url + "/schema") as resp:  # noqa: S310
        assert resp.status == 200
        assert json.loads(resp.read()) == get_schema()


def test_http_get_catalog(base_url: str) -> None:
    with urllib.request.urlopen(base_url + "/catalog") as resp:  # noqa: S310
        assert resp.status == 200
        body = json.loads(resp.read())
        assert "data.load_csv" in {spec["type"] for spec in body["nodes"]}
