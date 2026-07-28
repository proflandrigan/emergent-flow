"""Tests for the ``data.http_fetch`` node (Epic 16 Story 1).

Golden: the compiled code passes ``ast.parse`` and ``ruff check``.
Equivalence: ``execute(graph)`` matches the compile path under a replay client.
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
from emergentflow.data.http.protocol import HttpRequest, HttpResponse
from emergentflow.data.http.replay import ReplayHttpClient, write_http_fixture
from emergentflow.ir import Graph
from emergentflow.nodes import get as get_node_definition
from emergentflow.nodes.examples.http_fetch import HttpFetch


def _build_graph() -> Graph:
    defn = HttpFetch()
    node = defn.instantiate(
        label="Users",
        url="https://api.example.com/users",
        json_path="data",
        pagination="none",
    )
    return Graph(
        name="http_fetch_test",
        nodes={node.id: node},
        edges={},
    )


def test_http_fetch_golden_ast_parse() -> None:
    graph = _build_graph()
    code = compile_to_code(graph)
    ast.parse(code)


def test_http_fetch_golden_ruff_check() -> None:
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


def test_http_fetch_equivalence(tmp_path) -> None:
    graph = _build_graph()
    node_id = list(graph.nodes.keys())[0]

    request = HttpRequest(
        url="https://api.example.com/users",
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
            body='{"data":[{"id":1,"name":"a"},{"id":2,"name":"b"}]}',
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

    expected = pd.DataFrame({"id": [1, 2], "name": ["a", "b"]})
    assert_frame_equal(exec_frame, expected)
    assert_frame_equal(code_frame, expected)


def test_execute_without_client_raises() -> None:
    graph = _build_graph()
    from emergentflow.data.http.fetch import MissingHttpClientError

    with pytest.raises(MissingHttpClientError):
        execute(graph)


def test_node_is_registered() -> None:
    cls = get_node_definition("data.http_fetch")
    assert cls is HttpFetch
