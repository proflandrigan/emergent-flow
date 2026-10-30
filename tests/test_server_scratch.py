"""``POST /scratch/run`` (issue #178 task 2): ad-hoc transforms over a stored node output."""

from __future__ import annotations

import threading

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from emergentflow.codegen.executor import execute
from emergentflow.ir import Direction, Edge, Graph, PortRef
from emergentflow.nodes.examples import CustomCode, LoadCsv
from emergentflow.script import CaptureResult, run_transform_capture
from emergentflow.server import artifacts as artifacts_mod
from emergentflow.server import scratch as scratch_mod
from emergentflow.server.app import configure_session_auth, create_app
from emergentflow.server.artifacts import ArtifactStore
from tests.test_codegen_equivalence import assert_equivalent

LOOPBACK_URL = "http://127.0.0.1:8765"
GROUPBY = "def transform(value):\n    return value.groupby('g', as_index=False)['x'].sum()"


@pytest.fixture
def store(monkeypatch, tmp_path) -> ArtifactStore:
    s = ArtifactStore(root=tmp_path)
    monkeypatch.setattr(artifacts_mod, "_default_artifacts", s)
    return s


@pytest.fixture
def client(store) -> TestClient:
    # TestClient's default peer is "testclient" and Host "testserver"; scratch runs need a
    # loopback peer AND a loopback Host (DNS-rebinding guard), so say both.
    return TestClient(create_app(), base_url=LOOPBACK_URL, client=("127.0.0.1", 50000))


def _frame() -> pd.DataFrame:
    return pd.DataFrame({"g": ["a", "a", "b"], "x": [1, 2, 10]})


def _run(client: TestClient, store: ArtifactStore, code: str, **over) -> dict:
    rev = store.put("n1", {"frame": _frame()}, label="L")
    body = {"node_id": "n1", "port": "frame", "revision": rev, "code": code, **over}
    r = client.post("/scratch/run", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_groupby_on_stored_frame(client, store) -> None:
    out = _run(client, store, GROUPBY)
    assert out["status"] == "ok"
    assert out["result"]["kind"] == "table"
    assert [r["x"] for r in out["result"]["head"]] == [3, 10]
    assert out["elapsed_ms"] >= 0


def test_syntax_error_is_status_error_not_500(client, store) -> None:
    out = _run(client, store, "def transform(value:\n    return value")
    assert out["status"] == "error"
    assert out["error"]["type"] == "CustomCodeError"
    assert out["error"]["line"] == 1


def test_runtime_error_reports_type_and_line(client, store) -> None:
    out = _run(client, store, "def transform(value):\n    y = 1\n    return value['nope']")
    assert out["status"] == "error"
    assert out["error"]["type"] == "KeyError"
    assert out["error"]["line"] == 3
    assert "Traceback" in out["error"]["traceback"]


def test_missing_transform_is_error(client, store) -> None:
    assert _run(client, store, "x = 1")["status"] == "error"


def test_stdout_and_stderr_are_captured(client, store) -> None:
    code = (
        "import sys\ndef transform(value):\n"
        "    print('hi')\n    print('e', file=sys.stderr)\n    return 1"
    )
    out = _run(client, store, code)
    assert (out["status"], out["stdout"], out["stderr"]) == ("ok", "hi\n", "e\n")
    assert out["result"] == {"kind": "scalar", "value": 1}


def test_non_serialisable_result_degrades_to_repr(client, store) -> None:
    out = _run(client, store, "def transform(value):\n    return object()")
    assert out["status"] == "ok"
    assert out["result"]["kind"] == "unsupported"


def test_expired_when_nothing_stored(client, store) -> None:
    r = client.post(
        "/scratch/run", json={"node_id": "gone", "port": "frame", "revision": "1", "code": GROUPBY}
    )
    assert r.status_code == 200
    assert r.json()["status"] == "expired"


def test_revision_mismatch_never_rebinds(client, store) -> None:
    old = store.put("n1", {"frame": _frame()})
    new = store.put("n1", {"frame": _frame()})
    r = client.post(
        "/scratch/run", json={"node_id": "n1", "port": "frame", "revision": old, "code": GROUPBY}
    )
    body = r.json()
    assert (r.status_code, body["status"]) == (200, "revision_mismatch")
    assert body["current_revision"] == new
    assert "result" not in body


def test_stored_frame_is_not_mutated(client, store) -> None:
    code = (
        "def transform(value):\n    value['x'] = 0\n"
        "    value.drop(columns=['g'], inplace=True)\n    return value"
    )
    assert _run(client, store, code)["status"] == "ok"
    stored, _ = store.get_with_revision("n1")  # type: ignore[misc]
    pd.testing.assert_frame_equal(stored["frame"], _frame())


def test_malformed_request_is_422(client, store) -> None:
    assert client.post("/scratch/run", json={"node_id": "n1"}).status_code == 422


# -- access control ---------------------------------------------------------------------


def test_non_loopback_client_is_refused(store) -> None:
    store.put("n1", {"frame": _frame()})
    remote = TestClient(create_app(), client=("203.0.113.9", 50000))
    r = remote.post(
        "/scratch/run", json={"node_id": "n1", "port": "frame", "revision": "x", "code": "x"}
    )
    assert r.status_code == 403
    assert "error" in r.json()


def test_non_loopback_client_with_token_is_allowed(store) -> None:
    configure_session_auth(required=True, token="secret")
    try:
        remote = TestClient(create_app(), client=("203.0.113.9", 50000))
        body = {"node_id": "nope", "port": "frame", "revision": "x", "code": "x"}
        assert remote.post("/scratch/run", json=body).status_code == 403
        bad = remote.post("/scratch/run", json=body, headers={"Authorization": "Bearer wrong"})
        assert bad.status_code == 403
        ok = remote.post("/scratch/run", json=body, headers={"Authorization": "Bearer secret"})
        assert (ok.status_code, ok.json()["status"]) == (200, "expired")
    finally:
        configure_session_auth(required=False)


def test_cross_origin_and_forwarded_loopback_requests_are_refused(client, store) -> None:
    body = {"node_id": "n1", "port": "frame", "revision": "x", "code": "x"}
    cross = client.post("/scratch/run", json=body, headers={"Origin": "http://evil.example"})
    assert cross.status_code == 403
    fwd = client.post("/scratch/run", json=body, headers={"X-Forwarded-For": "203.0.113.9"})
    assert fwd.status_code == 403
    same = client.post("/scratch/run", json=body, headers={"Origin": LOOPBACK_URL})
    assert same.status_code == 200
    null = client.post("/scratch/run", json=body, headers={"Origin": "null"})
    assert null.status_code == 403


@pytest.mark.parametrize(
    "headers",
    [
        # DNS rebinding: attacker.example resolves to 127.0.0.1, so the page is same-origin.
        {"Host": "attacker.example:8765", "Origin": "http://attacker.example:8765"},
        {"Host": "attacker.example:8765"},  # no Origin (e.g. a simple request)
        {"Origin": "http://attacker.example:8765"},  # loopback Host, foreign Origin
        {"Origin": "http://localhost:9999"},  # loopback Origin but not this Host
        {"Sec-Fetch-Site": "cross-site"},
    ],
)
def test_dns_rebinding_and_cross_site_loopback_requests_are_refused(client, store, headers) -> None:
    body = {"node_id": "n1", "port": "frame", "revision": "x", "code": "x"}
    assert client.post("/scratch/run", json=body, headers=headers).status_code == 403


@pytest.mark.parametrize("host", ["localhost:8765", "127.0.0.1:8765", "[::1]:8765", "LOCALHOST"])
def test_loopback_host_names_are_allowed(client, store, host) -> None:
    body = {"node_id": "gone", "port": "frame", "revision": "x", "code": "x"}
    headers = {"Host": host, "Origin": f"http://{host}", "Sec-Fetch-Site": "same-origin"}
    r = client.post("/scratch/run", json=body, headers=headers)
    assert (r.status_code, r.json()["status"]) == (200, "expired")


def test_foreign_host_with_token_is_allowed(store) -> None:
    configure_session_auth(required=True, token="secret")
    try:
        c = TestClient(create_app(), base_url="http://box.lan:8765", client=("203.0.113.9", 1))
        body = {"node_id": "gone", "port": "frame", "revision": "x", "code": "x"}
        ok = c.post("/scratch/run", json=body, headers={"Authorization": "Bearer secret"})
        assert ok.status_code == 200
    finally:
        configure_session_auth(required=False)


# -- user-code edge cases ---------------------------------------------------------------


@pytest.mark.parametrize("stmt", ["raise SystemExit(1)", "exit()", "import sys; sys.exit('bye')"])
def test_system_exit_is_an_error_not_a_timeout(client, store, monkeypatch, stmt) -> None:
    monkeypatch.setattr(scratch_mod, "SCRATCH_TIMEOUT_S", 5.0)
    out = _run(client, store, f"def transform(value):\n    {stmt}")
    assert out["status"] == "error"
    assert out["error"]["type"] == "SystemExit"
    assert out["elapsed_ms"] < 5000


def test_print_to_sys_stdout_is_captured() -> None:
    code = "import sys\ndef transform(value):\n    print('hi', file=sys.stdout)\n    return 1"
    assert run_transform_capture(code, None).stdout == "hi\n"


def test_runaway_workers_are_capped_and_reported_busy(monkeypatch) -> None:
    release = threading.Event()

    def stuck(code: str, value: object) -> CaptureResult:
        release.wait(10)  # bounded, so a failing test can never hang the suite
        return CaptureResult(1, "", "", None)

    monkeypatch.setattr(scratch_mod, "run_transform_capture", stuck)
    monkeypatch.setattr(scratch_mod, "_run_slots", threading.BoundedSemaphore(2))
    started = threading.active_count()
    try:
        for _ in range(2):
            timed_out = scratch_mod._run_with_timeout("x", None, 0.05)
            assert timed_out.error is not None and timed_out.error.type == "TimeoutError"
        busy = scratch_mod._run_with_timeout("x", None, 0.05)
        assert busy.error is not None and busy.error.type == "ScratchBusy"
        assert threading.active_count() <= started + 2  # no third thread was spawned
    finally:
        release.set()
    # once the abandoned workers finish, their slots free up again
    for _ in range(100):
        if scratch_mod._run_slots.acquire(blocking=False):
            scratch_mod._run_slots.release()
            break
        threading.Event().wait(0.02)
    assert scratch_mod._run_with_timeout("x", None, 1.0).value == 1


# -- promotability ----------------------------------------------------------------------


def test_promotable_def_transform(client, store) -> None:
    out = _run(client, store, GROUPBY)
    assert (out["promotable"], out["promotable_reason"]) == (True, None)


@pytest.mark.parametrize(
    "code",
    [
        "transform = lambda v: v",
        "def transform(value, scale=2):\n    return value",
        "x = 1",
        "def transform(value:\n    return value",
    ],
)
def test_unpromotable_code_is_flagged_and_matches_custom_code_validation(
    client, store, code
) -> None:
    out = _run(client, store, code)
    assert out["promotable"] is False
    assert isinstance(out["promotable_reason"], str) and out["promotable_reason"]
    node = CustomCode().instantiate(code=code)
    assert CustomCode().validate_node(node)  # the node built from it would not validate


# -- promoted code is equivalent via scratch, execute() and codegen ------------------------


@pytest.mark.equivalence
def test_promoted_code_is_equivalent_across_scratch_execute_and_codegen(tmp_path) -> None:
    csv = tmp_path / "d.csv"
    _frame().to_csv(csv, index=False)
    load = LoadCsv().instantiate(path=str(csv))
    custom = CustomCode().instantiate(code=GROUPBY)
    src_port = next(p for p in load.ports if p.direction is Direction.OUT)
    dst_port = next(p for p in custom.ports if p.direction is Direction.IN)
    edge = Edge(
        source=PortRef(node_id=load.id, port_id=src_port.id),
        target=PortRef(node_id=custom.id, port_id=dst_port.id),
    )
    graph = Graph(nodes={load.id: load, custom.id: custom}, edges={edge.id: edge})

    assert_equivalent(graph, cwd=tmp_path)  # execute() == compiled code

    executed = execute(graph)
    source_frame = executed[load.id][src_port.name]
    scratch = run_transform_capture(GROUPBY, source_frame.copy())
    assert scratch.error is None
    out_name = next(p.name for p in custom.ports if p.direction is Direction.OUT)
    pd.testing.assert_frame_equal(scratch.value, executed[custom.id][out_name])
