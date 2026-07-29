"""Tests for ``ef.data.load_google_sheet`` and the ``data.load_google_sheet`` node.

Wrapper tests drive a stub client; node tests exercise codegen (golden) and
execute (equivalence) through the full compiler/executor under a replay client.
"""

from __future__ import annotations

import ast
import subprocess
import sys

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from emergentflow.clients import Clients
from emergentflow.codegen.compiler import compile_to_code
from emergentflow.codegen.executor import execute
from emergentflow.data.errors import DataLoadError, SchemaContractError
from emergentflow.data.http.fetch import MissingHttpClientError
from emergentflow.data.http.protocol import HttpRequest, HttpResponse
from emergentflow.data.http.replay import ReplayHttpClient, write_http_fixture
from emergentflow.data.http.sheets import SHEETS_CSV_URL, load_google_sheet
from emergentflow.ir import Graph
from emergentflow.nodes import get as get_node_definition
from emergentflow.nodes.examples.load_google_sheet import LoadGoogleSheet

# ---------------------------------------------------------------------------
# Stub client
# ---------------------------------------------------------------------------


class _StubHttpClient:
    """A stub HttpClient that returns canned responses and records requests."""

    def __init__(self, responses: list[HttpResponse] | None = None):
        self.responses = list(responses or [])
        self.requests: list[HttpRequest] = []

    def fetch(self, request: HttpRequest) -> HttpResponse:
        self.requests.append(request)
        if self.responses:
            return self.responses.pop(0)
        return HttpResponse(status=200, body="a,b\n1,2\n3,4")


def _ok(body: str) -> HttpResponse:
    return HttpResponse(status=200, body=body)


def _stub(*responses: HttpResponse) -> _StubHttpClient:
    return _StubHttpClient(list(responses))


# ---------------------------------------------------------------------------
# Wrapper tests
# ---------------------------------------------------------------------------


def test_missing_client_raises() -> None:
    with pytest.raises(MissingHttpClientError):
        load_google_sheet(spreadsheet_id="abc123", client=None)


def test_empty_spreadsheet_id_raises() -> None:
    with pytest.raises(ValueError):
        load_google_sheet(spreadsheet_id="", client=_stub())


def test_returns_frame_from_csv() -> None:
    client = _stub(_ok("a,b\n1,2\n3,4"))
    result = load_google_sheet(spreadsheet_id="abc123", client=client)
    expected = pd.DataFrame({"a": [1, 3], "b": [2, 4]})
    assert_frame_equal(result, expected)


def test_sheet_goes_in_params_not_url() -> None:
    client = _stub(_ok("x\n1"))
    load_google_sheet(spreadsheet_id="abc123", client=client, sheet="Sales")
    assert len(client.requests) == 1
    req = client.requests[0]
    assert ("sheet", "Sales") in req.params
    assert "Sales" not in req.url


def test_no_sheet_omits_param() -> None:
    client = _stub(_ok("x\n1"))
    load_google_sheet(spreadsheet_id="abc123", client=client)
    assert len(client.requests) == 1
    assert client.requests[0].params == ()


def test_header_row() -> None:
    csv_body = "junk,header\n1,2\n3,4"
    client = _stub(_ok(csv_body))
    result = load_google_sheet(spreadsheet_id="abc123", client=client, header_row=1)
    expected = pd.DataFrame({"1": [3], "2": [4]})
    assert_frame_equal(result, expected)


def test_non_2xx_raises_data_load_error() -> None:
    resp = HttpResponse(status=404, body="Not Found")
    client = _stub(resp)
    with pytest.raises(DataLoadError) as exc:
        load_google_sheet(spreadsheet_id="abc123", client=client)
    assert "404" in str(exc.value)
    assert "abc123" in str(exc.value)


def test_unparseable_body_raises_data_load_error() -> None:
    client = _stub(_ok(""))
    with pytest.raises(DataLoadError) as exc:
        load_google_sheet(spreadsheet_id="abc123", client=client)
    assert "abc123" in str(exc.value)


def test_expect_columns_pass() -> None:
    client = _stub(_ok("a,b\n1,2\n3,4"))
    result = load_google_sheet(spreadsheet_id="abc123", client=client, expect_columns=["a", "b"])
    assert list(result.columns) == ["a", "b"]


def test_expect_columns_fail() -> None:
    client = _stub(_ok("a,b\n1,2\n3,4"))
    with pytest.raises(SchemaContractError):
        load_google_sheet(spreadsheet_id="abc123", client=client, expect_columns=["a", "c"])


def test_url_uses_spreadsheet_id() -> None:
    client = _stub(_ok("x\n1"))
    load_google_sheet(spreadsheet_id="xyz789", client=client)
    assert len(client.requests) == 1
    assert "xyz789" in client.requests[0].url
    assert "abc123" not in client.requests[0].url


# ---------------------------------------------------------------------------
# Node tests
# ---------------------------------------------------------------------------


def _build_graph() -> Graph:
    defn = LoadGoogleSheet()
    node = defn.instantiate(
        label="Test Sheet",
        spreadsheet_id="abc123",
    )
    return Graph(
        name="load_google_sheet_test",
        nodes={node.id: node},
        edges={},
    )


def test_golden_ast_parse() -> None:
    graph = _build_graph()
    code = compile_to_code(graph)
    ast.parse(code)


def test_golden_ruff_check() -> None:
    graph = _build_graph()
    code = compile_to_code(graph)
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--stdin-filename",
            "generated.py",
            "-",
        ],
        input=code,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"ruff check failed:\n{proc.stdout}\n{proc.stderr}"


def test_compiled_threads_http_client() -> None:
    graph = _build_graph()
    code = compile_to_code(graph)
    assert "client=http" in code
    assert "http = clients.http if clients is not None else None" in code


def test_equivalence(tmp_path) -> None:
    graph = _build_graph()
    node_id = list(graph.nodes.keys())[0]

    request = HttpRequest(
        url=SHEETS_CSV_URL.format(spreadsheet_id="abc123"),
        method="GET",
        headers=(),
        params=(),
        body=None,
        connection=None,
        timeout_s=None,
    )
    write_http_fixture(
        tmp_path,
        request,
        HttpResponse(
            status=200,
            body="a,b\n1,2\n3,4",
        ),
    )

    replay = ReplayHttpClient(tmp_path)

    exec_results = execute(graph, clients=Clients(http=replay))
    exec_frame = exec_results[node_id]["frame"]

    code = compile_to_code(graph)
    ns: dict = {}
    exec(code, ns)  # noqa: S102
    main_results = ns["main"](clients=Clients(http=replay))
    code_frame = next(iter(main_results.values()))

    expected = pd.DataFrame({"a": [1, 3], "b": [2, 4]})
    assert_frame_equal(exec_frame, expected)
    assert_frame_equal(code_frame, expected)


def test_node_is_registered() -> None:
    cls = get_node_definition("data.load_google_sheet")
    assert cls is LoadGoogleSheet
