"""Tests for ``emergentflow.data.http.protocol`` (Epic 16 Story 1).

Covers content-hash stability, dataclass frozen/hashable contract, the ``ok``
property, and the runtime-checkable Protocol structural check.
"""

from __future__ import annotations

import dataclasses
import re

import pytest

from emergentflow.data.http.protocol import (
    HttpClient,
    HttpRequest,
    HttpResponse,
)


class _StubHttpClient:
    """Minimal stub that implements the ``HttpClient`` protocol structurally."""

    def fetch(self, request: HttpRequest) -> HttpResponse:
        return HttpResponse(status=200, body="ok")


def test_content_hash_is_stable() -> None:
    a = HttpRequest(url="https://example.com/api", method="POST", body='{"key": "val"}')
    b = HttpRequest(url="https://example.com/api", method="POST", body='{"key": "val"}')
    assert a.content_hash() == b.content_hash()


def test_content_hash_differs_on_url() -> None:
    a = HttpRequest(url="https://example.com/a")
    b = HttpRequest(url="https://example.com/b")
    assert a.content_hash() != b.content_hash()


def test_content_hash_differs_on_header_order() -> None:
    a = HttpRequest(url="https://example.com/api", headers=(("a", "1"), ("b", "2")))
    b = HttpRequest(url="https://example.com/api", headers=(("b", "2"), ("a", "1")))
    assert a.content_hash() != b.content_hash()


def test_content_hash_is_hex_sha256() -> None:
    req = HttpRequest(url="https://example.com/api")
    digest = req.content_hash()
    assert re.fullmatch(r"[0-9a-f]{64}", digest) is not None, digest


def test_http_request_is_frozen() -> None:
    req = HttpRequest(url="https://example.com/api")
    with pytest.raises(dataclasses.FrozenInstanceError):
        req.url = "https://other.com"  # type: ignore[misc]


def test_http_request_is_hashable() -> None:
    req = HttpRequest(url="https://example.com/api")
    hash(req)  # does not raise


def test_response_ok() -> None:
    assert HttpResponse(status=200, body="").ok is True
    assert HttpResponse(status=299, body="").ok is True
    assert HttpResponse(status=199, body="").ok is False
    assert HttpResponse(status=300, body="").ok is False
    assert HttpResponse(status=404, body="").ok is False
    assert HttpResponse(status=500, body="").ok is False


def test_replay_client_satisfies_protocol() -> None:
    stub = _StubHttpClient()
    assert isinstance(stub, HttpClient)
