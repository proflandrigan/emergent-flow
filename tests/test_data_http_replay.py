from __future__ import annotations

from pathlib import Path

import pytest

from emergentflow.data.http.protocol import (
    FixtureMissError,
    HttpClient,
    HttpRequest,
    HttpResponse,
)
from emergentflow.data.http.replay import ReplayHttpClient, write_http_fixture


def test_write_and_replay_round_trip(tmp_path: Path) -> None:
    request = HttpRequest(url="https://example.com/data", method="GET")
    response = HttpResponse(
        status=200,
        body='{"key": "value"}',
        headers=(("content-type", "application/json"), ("x-request-id", "abc123")),
        url="https://example.com/data",
        elapsed_ms=45.2,
    )

    write_http_fixture(tmp_path, request, response)
    client = ReplayHttpClient(tmp_path)
    replayed = client.fetch(request)

    assert replayed.status == 200
    assert replayed.body == '{"key": "value"}'
    assert replayed.headers == (("content-type", "application/json"), ("x-request-id", "abc123"))
    assert replayed.url == "https://example.com/data"
    assert replayed.elapsed_ms == 45.2


def test_replayed_headers_are_tuples(tmp_path: Path) -> None:
    request = HttpRequest(url="https://example.com/tuples")
    response = HttpResponse(
        status=200,
        body="ok",
        headers=(("a", "1"), ("b", "2")),
    )

    write_http_fixture(tmp_path, request, response)
    client = ReplayHttpClient(tmp_path)
    replayed = client.fetch(request)

    assert isinstance(replayed.headers, tuple)
    for h in replayed.headers:
        assert isinstance(h, tuple)
    # hashability check — should not raise
    hash(replayed)


def test_fixture_miss_raises(tmp_path: Path) -> None:
    request = HttpRequest(url="https://example.com/missing")
    client = ReplayHttpClient(tmp_path)

    with pytest.raises(FixtureMissError) as excinfo:
        client.fetch(request)

    msg = str(excinfo.value)
    assert request.content_hash() in msg
    assert "write_http_fixture" in msg


def test_non_2xx_replays_without_raising(tmp_path: Path) -> None:
    request = HttpRequest(url="https://example.com/not-found")
    response = HttpResponse(status=404, body="Not Found", url="https://example.com/not-found")

    write_http_fixture(tmp_path, request, response)
    client = ReplayHttpClient(tmp_path)
    replayed = client.fetch(request)

    assert replayed.status == 404
    assert replayed.ok is False


def test_write_creates_missing_directory(tmp_path: Path) -> None:
    nested = tmp_path / "a" / "b" / "c"
    request = HttpRequest(url="https://example.com/nested")
    response = HttpResponse(status=200, body="ok")

    written = write_http_fixture(nested, request, response)

    assert written.exists()
    assert written.parent == nested


def test_replay_client_satisfies_protocol(tmp_path: Path) -> None:
    assert isinstance(ReplayHttpClient(tmp_path), HttpClient)


def test_different_requests_get_different_fixtures(tmp_path: Path) -> None:
    req_a = HttpRequest(url="https://example.com/a")
    req_b = HttpRequest(url="https://example.com/b")
    resp_a = HttpResponse(status=200, body="response a")
    resp_b = HttpResponse(status=200, body="response b")

    write_http_fixture(tmp_path, req_a, resp_a)
    write_http_fixture(tmp_path, req_b, resp_b)

    client = ReplayHttpClient(tmp_path)
    assert client.fetch(req_a).body == "response a"
    assert client.fetch(req_b).body == "response b"
