"""Tests for the thin local server (ADR 0013, §A6).

Exercises the in-process service functions and the stdlib HTTP layer end to end:
build a real IR graph, round-trip it through serialize, and confirm
compile / validate / execute return JSON-safe payloads -- proving the
canvas -> IR -> code/execute loop that the bundled ``emergentflow serve`` exposes.
No torch, no network, no fixtures beyond the bundled sample CSV.
"""

from __future__ import annotations

import importlib
import json
import pathlib
import socket
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

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
from emergentflow.llm.env import MissingAPIKeyError
from emergentflow.server import (
    app,
    compile_graph,
    execute_graph,
    execute_node,
    get_catalog,
    get_schema,
    validate_graph,
)
from emergentflow.server import cache as cache_mod
from emergentflow.server.payload import PAYLOAD_CONTRACT_VERSION
from emergentflow.server.service import (
    _execute_functional_stream,
    _to_graph,
)


@pytest.fixture(autouse=True)
def _fresh_default_cache(tmp_path: pathlib.Path) -> Iterator[None]:
    """Isolate the on-disk execution cache per test so cached outputs from one
    test don't produce false cache hits in another."""
    from emergentflow.server.cache import ExecutionCache

    old = cache_mod._default_cache
    cache_mod._default_cache = ExecutionCache(root=tmp_path / ".ef-cache")
    yield
    cache_mod._default_cache = old


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


def _llm_call_graph(provider: str = "anthropic") -> dict:
    """A minimal one-node functional graph with an `llm.call` node (requires_client)."""
    node = Node(
        id="n-llm",
        type="llm.call",
        label="LLM Call",
        paradigm=Paradigm.FUNCTIONAL,
        params=[Param(name="provider", type_token="str", value=provider)],
        ports=[
            Port(
                id="p-llm-response",
                name="response",
                direction=Direction.OUT,
                data_type="LLMResponse",
            ),
        ],
        position=Position(x=0.0, y=0.0),
    )
    graph = Graph(
        paradigm=Paradigm.FUNCTIONAL,
        name="server-test-llm",
        nodes={node.id: node},
        edges={},
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


def test_execute_functional_stream_emits_start_then_ok_for_two_node_chain() -> None:
    events = list(_execute_functional_stream(_to_graph(_chain_graph())))
    assert len(events) == 4
    # n-load: start, ok
    assert events[0].phase == "start"
    assert events[0].node_id == "n-load"
    assert events[0].current == 1
    assert events[0].total == 2
    assert events[1].phase == "ok"
    assert events[1].node_id == "n-load"
    assert events[1].elapsed_ms is not None
    assert events[1].elapsed_ms >= 0
    assert events[1].results is not None
    # n-impute: start, ok
    assert events[2].phase == "start"
    assert events[2].node_id == "n-impute"
    assert events[2].current == 2
    assert events[2].total == 2
    assert events[3].phase == "ok"
    assert events[3].node_id == "n-impute"
    assert events[3].elapsed_ms is not None
    assert events[3].elapsed_ms >= 0
    assert events[3].results is not None


def test_execute_functional_stream_emits_skip_for_downstream_of_error() -> None:
    events = list(_execute_functional_stream(_to_graph(_chain_graph(path="/no/such/file.csv"))))
    # n-load yields start then error; n-impute yields skip.
    assert events[0].phase == "start"
    assert events[0].node_id == "n-load"
    assert events[1].phase == "error"
    assert events[1].node_id == "n-load"
    assert events[2].phase == "skip"
    assert events[2].node_id == "n-impute"


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


def test_execute_graph_preflight_rejects_missing_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    # A missing API key is a graph-LEVEL pre-flight failure (Epic 9 Story 9): it must raise
    # before any node runs, not surface deep inside GatewayClient.complete() -- and never as
    # a per-node "error" status.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(MissingAPIKeyError) as exc_info:
        execute_graph(_llm_call_graph())
    assert "ANTHROPIC_API_KEY" in str(exc_info.value)


def test_execute_node_preflight_rejects_missing_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(MissingAPIKeyError) as exc_info:
        execute_node({"graph": _llm_call_graph(), "run_node": "n-llm"})
    assert "ANTHROPIC_API_KEY" in str(exc_info.value)


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
# HTTP layer (FastAPI TestClient)
# ---------------------------------------------------------------------------


@pytest.fixture
def client() -> Iterator[TestClient]:
    """A FastAPI test client over the module-level ``app`` (no real socket)."""
    with TestClient(app) as test_client:
        yield test_client


def test_healthz(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_index_page_served(client: TestClient) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Emergent Flow" in resp.content


def test_static_index_served_when_present(tmp_path, monkeypatch, client: TestClient) -> None:
    app_mod = importlib.import_module("emergentflow.server.app")

    static_dir = tmp_path / "_static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html><body>BUNDLED CANVAS</body></html>")
    monkeypatch.setattr(app_mod, "_STATIC_DIR", static_dir.resolve())
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"BUNDLED CANVAS" in resp.content


def test_static_asset_served_with_content_type(tmp_path, monkeypatch, client: TestClient) -> None:
    app_mod = importlib.import_module("emergentflow.server.app")

    static_dir = tmp_path / "_static"
    (static_dir / "assets").mkdir(parents=True)
    (static_dir / "assets" / "app.js").write_text("console.log('hi');")
    monkeypatch.setattr(app_mod, "_STATIC_DIR", static_dir.resolve())
    resp = client.get("/assets/app.js")
    assert resp.status_code == 200
    assert "javascript" in resp.headers["content-type"]
    assert b"console.log" in resp.content


def test_demo_page_when_static_absent(tmp_path, monkeypatch, client: TestClient) -> None:
    app_mod = importlib.import_module("emergentflow.server.app")

    monkeypatch.setattr(app_mod, "_STATIC_DIR", (tmp_path / "_static").resolve())
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Emergent Flow" in resp.content


def test_static_file_blocks_directory_traversal(tmp_path, monkeypatch) -> None:
    app_mod = importlib.import_module("emergentflow.server.app")

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
    app_mod = importlib.import_module("emergentflow.server.app")

    opened: list[str] = []
    monkeypatch.setattr(app_mod.webbrowser, "open", lambda url, *a, **k: opened.append(url))
    app_mod._open_browser("http://127.0.0.1:8765")
    assert opened == ["http://127.0.0.1:8765"]


def test_open_browser_swallows_errors(monkeypatch) -> None:
    app_mod = importlib.import_module("emergentflow.server.app")

    def boom(url, *a, **k):
        raise RuntimeError("no browser on this host")

    monkeypatch.setattr(app_mod.webbrowser, "open", boom)
    app_mod._open_browser("http://127.0.0.1:8765")  # must NOT raise


def test_open_browser_when_ready_waits_for_listening_socket(monkeypatch) -> None:
    # Regression test: serve() used to open the browser before uvicorn.run() had
    # bound the socket, racing a slow startup. _open_browser_when_ready must only
    # fire once the port is actually accepting connections.
    app_mod = importlib.import_module("emergentflow.server.app")

    opened: list[str] = []
    monkeypatch.setattr(app_mod, "_open_browser", opened.append)

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.bind(("127.0.0.1", 0))
    server_sock.listen(1)
    port = server_sock.getsockname()[1]
    try:
        app_mod._open_browser_when_ready("127.0.0.1", port, "http://probe", timeout=2.0)
    finally:
        server_sock.close()
    assert opened == ["http://probe"]


def test_open_browser_when_ready_gives_up_after_timeout(monkeypatch) -> None:
    # Nothing is listening on this port; the poll must not hang forever -- it
    # opens the browser best-effort once its (short, test-only) timeout elapses.
    app_mod = importlib.import_module("emergentflow.server.app")

    opened: list[str] = []
    monkeypatch.setattr(app_mod, "_open_browser", opened.append)

    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    free_port = probe.getsockname()[1]
    probe.close()

    app_mod._open_browser_when_ready("127.0.0.1", free_port, "http://probe", timeout=0.3)
    assert opened == ["http://probe"]


def test_serve_configures_cache_before_starting_uvicorn(monkeypatch) -> None:
    app_mod = importlib.import_module("emergentflow.server.app")
    calls = {}

    def fake_configure_cache(root, max_mb):
        calls["root"] = root
        calls["max_mb"] = max_mb

    def fake_uvicorn_run(*args, **kwargs):
        calls["ran"] = True

    monkeypatch.setattr(app_mod, "configure_cache", fake_configure_cache)
    monkeypatch.setattr("uvicorn.run", fake_uvicorn_run)
    app_mod.serve(open_browser=False, cache_dir="/tmp/xyz", cache_max_mb=42.0)
    assert calls == {"root": pathlib.Path("/tmp/xyz"), "max_mb": 42.0, "ran": True}


def test_serve_defaults_cache_dir_to_cwd_ef_cache(monkeypatch, tmp_path) -> None:
    app_mod = importlib.import_module("emergentflow.server.app")
    calls = {}

    def fake_configure_cache(root, max_mb):
        calls["root"] = root
        calls["max_mb"] = max_mb

    def fake_uvicorn_run(*args, **kwargs):
        pass

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(app_mod, "configure_cache", fake_configure_cache)
    monkeypatch.setattr("uvicorn.run", fake_uvicorn_run)
    app_mod.serve(open_browser=False)
    assert calls["root"] == tmp_path / ".ef-cache"
    assert calls["max_mb"] == app_mod.DEFAULT_CACHE_MAX_MB


def test_http_compile_and_execute(client: TestClient) -> None:
    resp = client.post("/compile", json=_load_csv_graph())
    assert resp.status_code == 200
    assert "import emergentflow as ef" in resp.json()["code"]

    resp = client.post("/execute", json=_load_csv_graph())
    assert resp.status_code == 200
    body = resp.json()
    assert "n-load" in body["results"]
    assert body["payload_version"] == 2
    assert body["results"]["n-load"]["frame"]["kind"] == "table"


def test_http_execute_node(client: TestClient) -> None:
    resp = client.post("/execute_node", json={"graph": _load_csv_graph(), "run_node": "n-load"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["statuses"]["n-load"]["status"] == "ok"
    assert body["results"]["n-load"]["frame"]["kind"] == "table"


def test_http_execute_node_error_reports_per_node_status(client: TestClient) -> None:
    # A node-runtime failure (bad CSV path) is reported per-node at HTTP 200 so the
    # canvas can colour just that node red -- the server never crashes.
    resp = client.post("/execute", json=_load_csv_graph(path="/no/such/file.csv"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["statuses"]["n-load"]["status"] == "error"
    assert "n-load" not in body["results"]


def test_http_execute_unconnected_input_is_422(client: TestClient) -> None:
    payload = _chain_graph()
    payload["edges"] = {}
    payload["nodes"] = {k: v for k, v in payload["nodes"].items() if k == "n-impute"}
    resp = client.post("/execute", json=payload)
    assert resp.status_code == 422
    assert "error" in resp.json()


# ---------------------------------------------------------------------------
# SSE streaming (/execute/stream)
# ---------------------------------------------------------------------------


def _parse_sse_events(text: str) -> list[dict]:
    events = []
    for line in text.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: ") :]))
    return events


def test_http_execute_stream_two_node_graph(client: TestClient) -> None:
    resp = client.post("/execute/stream", json=_chain_graph())
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse_events(resp.text)
    types = [e["type"] for e in events]
    assert types == ["node_start", "node_ok", "node_start", "node_ok", "run_complete"]
    assert events[0]["node_id"] == "n-load"
    assert events[2]["node_id"] == "n-impute"
    assert "total_ms" in events[-1]
    assert all(e["payload_version"] == PAYLOAD_CONTRACT_VERSION for e in events)


def test_http_execute_stream_node_error_skips_downstream(client: TestClient) -> None:
    resp = client.post("/execute/stream", json=_chain_graph(path="/no/such/file.csv"))
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse_events(resp.text)
    types = [e["type"] for e in events]
    assert types == ["node_start", "node_error", "node_skip", "run_complete"]
    assert events[2]["node_id"] == "n-impute"


def test_http_execute_stream_run_to_prunes_subgraph(client: TestClient) -> None:
    resp = client.post("/execute/stream", json={"graph": _fanout_graph(), "run_to": "n-impute-b"})
    assert resp.status_code == 200
    events = _parse_sse_events(resp.text)
    all_ids = {e["node_id"] for e in events if "node_id" in e}
    assert "n-impute-c" not in all_ids
    assert "n-impute-b" in all_ids


def test_http_execute_stream_run_to_unknown_target_is_422(client: TestClient) -> None:
    resp = client.post("/execute/stream", json={"graph": _fanout_graph(), "run_to": "n-nope"})
    assert resp.status_code == 422
    assert "error" in resp.json()


def test_http_execute_stream_bad_json_is_400(client: TestClient) -> None:
    resp = client.post(
        "/execute/stream", content=b"{not json", headers={"Content-Type": "application/json"}
    )
    assert resp.status_code == 400
    assert resp.headers["content-type"] == "application/json"
    body = resp.json()
    assert "error" in body
    assert "invalid JSON body" in body["error"]


def test_http_execute_stream_unconnected_input_is_422(client: TestClient) -> None:
    payload = _chain_graph()
    payload["edges"] = {}
    payload["nodes"] = {k: v for k, v in payload["nodes"].items() if k == "n-impute"}
    resp = client.post("/execute/stream", json=payload)
    assert resp.status_code == 422
    assert "error" in resp.json()


def test_http_invalid_json_body_is_400(client: TestClient) -> None:
    resp = client.post("/compile", content="not json", headers={"Content-Type": "application/json"})
    assert resp.status_code == 400
    assert "error" in resp.json()


def test_http_unknown_route_is_404(client: TestClient) -> None:
    resp = client.post("/nope", json={})
    assert resp.status_code == 404
    assert "error" in resp.json()


def test_http_get_schema(client: TestClient) -> None:
    resp = client.get("/schema")
    assert resp.status_code == 200
    assert resp.json() == get_schema()


def test_http_get_catalog(client: TestClient) -> None:
    resp = client.get("/catalog")
    assert resp.status_code == 200
    body = resp.json()
    assert "data.load_csv" in {spec["type"] for spec in body["nodes"]}


def test_http_reports_round_trip(client: TestClient) -> None:
    from emergentflow.server.reports import get_default_store

    html = "<!DOCTYPE html><html><body>profile</body></html>"
    report_hash = get_default_store().put(html)
    resp = client.get(f"/reports/{report_hash}")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert resp.text == html


def test_http_reports_unknown_hash_is_404(client: TestClient) -> None:
    resp = client.get("/reports/deadbeefdeadbeef")
    assert resp.status_code == 404
    assert "error" in resp.json()


def test_http_cache_clear(client: TestClient) -> None:
    resp = client.post("/cache/clear")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def _sample_chain_graph() -> dict:
    """load_sample -> impute_missing: unlike load_csv, load_sample reads a bundled,
    immutable dataset (no external file content the cache key can't see), so it is
    actually cacheable -- used here instead of ``_chain_graph``'s load_csv to
    exercise the cache-clear behavior itself, not the load_csv staleness gap."""
    load = Node(
        id="n-load",
        type="data.load_sample",
        label="Load Sample",
        paradigm=Paradigm.FUNCTIONAL,
        params=[Param(name="name", type_token="str", value="iris")],
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
        name="server-test-sample-chain",
        nodes={load.id: load, impute.id: impute},
        edges={edge.id: edge},
    )
    return json.loads(serialize_graph(graph))


def test_http_cache_clear_empties_cache_used_by_execute(client: TestClient) -> None:
    graph = _sample_chain_graph()
    first = execute_graph(graph)
    assert first["statuses"]["n-load"]["status"] == "ok"
    second = execute_graph(graph)
    assert second["statuses"]["n-load"]["status"] == "cached"

    resp = client.post("/cache/clear")
    assert resp.status_code == 200

    third = execute_graph(graph)
    assert third["statuses"]["n-load"]["status"] == "ok"
