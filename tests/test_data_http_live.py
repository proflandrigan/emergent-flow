from __future__ import annotations

import http.client
import io
import urllib.error
import urllib.request

import pytest

from emergentflow.data.http.live import (
    MissingAuthEnvError,
    UnsupportedUrlSchemeError,
    UrllibHttpClient,
)
from emergentflow.data.http.protocol import HttpClient, HttpRequest


class FakeResponse:
    """Minimal stand-in for ``http.client.HTTPResponse``.

    Exposes the attributes ``fetch()`` reads: ``status``, ``read()``,
    ``headers``, ``geturl()``, and context-manager protocol.
    """

    def __init__(
        self,
        status: int = 200,
        body: bytes = b"ok",
        headers: http.client.HTTPMessage | None = None,
        url: str = "https://example.com/data",
    ) -> None:
        self.status = status
        self._body = body
        self._url = url
        self.headers = headers or http.client.HTTPMessage()

    def read(self) -> bytes:
        return self._body

    def geturl(self) -> str:
        return self._url

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        pass


def test_fetch_returns_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "emergentflow.data.http.live.urllib.request.urlopen",
        lambda req, timeout=None: FakeResponse(
            status=200,
            body=b'{"result": "ok"}',
            url="https://example.com/data",
        ),
    )
    client = UrllibHttpClient()
    response = client.fetch(HttpRequest(url="https://example.com/data"))
    assert response.status == 200
    assert response.body == '{"result": "ok"}'
    assert response.elapsed_ms is not None


def test_params_are_appended_to_url(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[urllib.request.Request] = []

    def fake_urlopen(req: urllib.request.Request, timeout: float | None = None) -> FakeResponse:
        captured.append(req)
        return FakeResponse()

    monkeypatch.setattr("emergentflow.data.http.live.urllib.request.urlopen", fake_urlopen)
    client = UrllibHttpClient()
    client.fetch(
        HttpRequest(
            url="https://example.com/search",
            params=(("q", "hello"), ("page", "1")),
        )
    )
    assert len(captured) == 1
    full_url = captured[0].get_full_url()
    assert "q=hello" in full_url
    assert "page=1" in full_url


def test_params_appended_with_ampersand_when_url_has_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[urllib.request.Request] = []

    def fake_urlopen(req: urllib.request.Request, timeout: float | None = None) -> FakeResponse:
        captured.append(req)
        return FakeResponse()

    monkeypatch.setattr("emergentflow.data.http.live.urllib.request.urlopen", fake_urlopen)
    client = UrllibHttpClient()
    client.fetch(
        HttpRequest(
            url="https://example.com/search?x=1",
            params=(("q", "hello"),),
        )
    )
    full_url = captured[0].get_full_url()
    assert "?x=1&q=hello" in full_url
    assert "??" not in full_url


def test_auth_header_injected_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_TOKEN", "s3cret")
    captured: list[urllib.request.Request] = []

    def fake_urlopen(req: urllib.request.Request, timeout: float | None = None) -> FakeResponse:
        captured.append(req)
        return FakeResponse()

    monkeypatch.setattr("emergentflow.data.http.live.urllib.request.urlopen", fake_urlopen)
    client = UrllibHttpClient(auth_env="MY_TOKEN")
    client.fetch(HttpRequest(url="https://example.com/data"))
    headers = dict(captured[0].headers)
    assert headers.get("Authorization") == "Bearer s3cret"


def test_auth_header_without_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_KEY", "raw-value")
    captured: list[urllib.request.Request] = []

    def fake_urlopen(req: urllib.request.Request, timeout: float | None = None) -> FakeResponse:
        captured.append(req)
        return FakeResponse()

    monkeypatch.setattr("emergentflow.data.http.live.urllib.request.urlopen", fake_urlopen)
    client = UrllibHttpClient(auth_env="API_KEY", auth_header="X-API-Key", auth_scheme="")
    client.fetch(HttpRequest(url="https://example.com/data"))
    headers = dict(captured[0].headers)
    assert headers.get("X-api-key") == "raw-value"


def test_missing_auth_env_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MY_TOKEN", raising=False)

    def fake_urlopen(req: urllib.request.Request, timeout: float | None = None) -> FakeResponse:
        raise RuntimeError("should not be called")

    monkeypatch.setattr("emergentflow.data.http.live.urllib.request.urlopen", fake_urlopen)
    client = UrllibHttpClient(auth_env="MY_TOKEN")
    with pytest.raises(MissingAuthEnvError) as excinfo:
        client.fetch(HttpRequest(url="https://example.com/data"))
    msg = str(excinfo.value)
    assert "MY_TOKEN" in msg
    assert "s3cret" not in msg


def test_no_auth_env_sends_no_auth_header(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[urllib.request.Request] = []

    def fake_urlopen(req: urllib.request.Request, timeout: float | None = None) -> FakeResponse:
        captured.append(req)
        return FakeResponse()

    monkeypatch.setattr("emergentflow.data.http.live.urllib.request.urlopen", fake_urlopen)
    client = UrllibHttpClient()
    client.fetch(HttpRequest(url="https://example.com/data"))
    assert captured[0].get_header("Authorization") is None


def test_file_scheme_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    call_count: list[int] = []

    def fake_urlopen(req: urllib.request.Request, timeout: float | None = None) -> FakeResponse:
        call_count.append(1)
        return FakeResponse()

    monkeypatch.setattr("emergentflow.data.http.live.urllib.request.urlopen", fake_urlopen)
    client = UrllibHttpClient()
    with pytest.raises(UnsupportedUrlSchemeError):
        client.fetch(HttpRequest(url="file:///etc/passwd"))
    assert len(call_count) == 0


def test_ftp_scheme_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    call_count: list[int] = []

    def fake_urlopen(req: urllib.request.Request, timeout: float | None = None) -> FakeResponse:
        call_count.append(1)
        return FakeResponse()

    monkeypatch.setattr("emergentflow.data.http.live.urllib.request.urlopen", fake_urlopen)
    client = UrllibHttpClient()
    with pytest.raises(UnsupportedUrlSchemeError):
        client.fetch(HttpRequest(url="ftp://files.example.com/data"))
    assert len(call_count) == 0


def test_http_error_becomes_response_not_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hdrs = http.client.HTTPMessage()
    hdrs.add_header("Content-Type", "text/plain")

    def fake_urlopen(req: urllib.request.Request, timeout: float | None = None) -> FakeResponse:
        fp = io.BytesIO(b"Not Found")
        raise urllib.error.HTTPError("https://example.com/404", 404, "Not Found", hdrs, fp)

    monkeypatch.setattr("emergentflow.data.http.live.urllib.request.urlopen", fake_urlopen)
    client = UrllibHttpClient()
    response = client.fetch(HttpRequest(url="https://example.com/404"))
    assert response.status == 404
    assert response.ok is False
    assert "Not Found" in response.body


def test_client_satisfies_protocol() -> None:
    assert isinstance(UrllibHttpClient(), HttpClient)


def test_response_headers_are_tuples(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_headers = http.client.HTTPMessage()
    fake_headers.add_header("Content-Type", "application/json")

    monkeypatch.setattr(
        "emergentflow.data.http.live.urllib.request.urlopen",
        lambda req, timeout=None: FakeResponse(
            status=200,
            body=b"{}",
            headers=fake_headers,
            url="https://example.com/data",
        ),
    )
    client = UrllibHttpClient()
    response = client.fetch(HttpRequest(url="https://example.com/data"))
    assert isinstance(response.headers, tuple)
    for h in response.headers:
        assert isinstance(h, tuple)
    hash(response)
