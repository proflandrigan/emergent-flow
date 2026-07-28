"""Tests for emergentflow.data.http.fetch (Epic 16 Story 1)."""

from __future__ import annotations

import pandas as pd
import pytest

from emergentflow.data.errors import DataLoadError
from emergentflow.data.http.fetch import MissingHttpClientError, http_fetch
from emergentflow.data.http.protocol import HttpRequest, HttpResponse


class _StubHttpClient:
    """A stub HttpClient that returns canned responses from a list."""

    def __init__(self, responses: list[HttpResponse] | None = None):
        self.responses = list(responses or [])
        self.requests: list[HttpRequest] = []

    def fetch(self, request: HttpRequest) -> HttpResponse:
        self.requests.append(request)
        if self.responses:
            return self.responses.pop(0)
        return HttpResponse(status=200, body="[]")


def _ok(body: str, url: str = "http://example.com") -> HttpResponse:
    return HttpResponse(status=200, body=body, url=url)


def _stub(*responses: HttpResponse) -> _StubHttpClient:
    return _StubHttpClient(list(responses))


# --- Client injection ---------------------------------------------------------


def test_missing_client_raises() -> None:
    with pytest.raises(MissingHttpClientError):
        http_fetch(url="http://example.com", client=None)


# --- Basic fetch --------------------------------------------------------------


def test_simple_fetch_returns_frame() -> None:
    client = _stub(_ok('[{"a":1},{"a":2}]'))
    result = http_fetch(url="http://example.com", client=client)
    assert isinstance(result, pd.DataFrame)
    assert list(result.columns) == ["a"]
    assert result.shape == (2, 1)


def test_json_path_selects_nested_records() -> None:
    client = _stub(_ok('{"data":{"items":[{"a":1},{"a":2}]}}'))
    result = http_fetch(url="http://example.com", client=client, json_path="data.items")
    assert list(result.columns) == ["a"]
    assert result.shape == (2, 1)


def test_json_path_missing_key_raises() -> None:
    client = _stub(_ok('{"a":1}'))
    with pytest.raises(DataLoadError) as exc:
        http_fetch(url="http://example.com", client=client, json_path="data.items")
    assert "data.items" in str(exc.value)
    assert "a" in str(exc.value)


def test_flatten_expands_nested_objects() -> None:
    client = _stub(_ok('[{"a":{"b":1}}]'))
    flat = http_fetch(url="http://example.com", client=client, flatten=True)
    assert "a.b" in flat.columns
    assert "a" not in flat.columns

    client2 = _stub(_ok('[{"a":{"b":1}}]'))
    unflat = http_fetch(url="http://example.com", client=client2, flatten=False)
    assert "a" in unflat.columns
    assert "a.b" not in unflat.columns


def test_non_2xx_raises_data_load_error() -> None:
    resp = HttpResponse(status=404, body="Not Found", url="http://example.com/404")
    client = _stub(resp)
    with pytest.raises(DataLoadError) as exc:
        http_fetch(url="http://example.com/404", client=client)
    assert "404" in str(exc.value)


def test_invalid_json_raises_data_load_error() -> None:
    client = _stub(_ok("not valid json"))
    with pytest.raises(DataLoadError) as exc:
        http_fetch(url="http://example.com", client=client)
    assert "200" in str(exc.value)


def test_single_object_becomes_one_row() -> None:
    client = _stub(_ok('{"a":1,"b":2}'))
    result = http_fetch(url="http://example.com", client=client)
    assert isinstance(result, pd.DataFrame)
    assert result.shape == (1, 2)


def test_empty_list_returns_empty_frame() -> None:
    client = _stub(_ok("[]"))
    result = http_fetch(url="http://example.com", client=client)
    assert isinstance(result, pd.DataFrame)
    assert len(result) == 0


# --- Validation errors --------------------------------------------------------


def test_unsupported_pagination_mode_raises() -> None:
    client = _stub()
    with pytest.raises(ValueError, match="pagination"):
        http_fetch(url="http://example.com", client=client, pagination="invalid")


def test_max_pages_zero_raises() -> None:
    client = _stub()
    with pytest.raises(ValueError, match="max_pages"):
        http_fetch(url="http://example.com", client=client, max_pages=0)


def test_cursor_without_cursor_path_raises() -> None:
    client = _stub()
    with pytest.raises(ValueError, match="cursor_path"):
        http_fetch(url="http://example.com", client=client, pagination="cursor", cursor_path=None)


def test_offset_without_page_size_raises() -> None:
    client = _stub()
    with pytest.raises(ValueError, match="page_size"):
        http_fetch(url="http://example.com", client=client, pagination="offset", page_size=None)


# --- Pagination ---------------------------------------------------------------


def test_cursor_pagination_follows_cursor() -> None:
    client = _stub(
        _ok('{"items":[{"a":1}],"next":"abc"}'),
        _ok('{"items":[{"a":2}],"next":null}'),
    )
    result = http_fetch(
        url="http://example.com",
        client=client,
        json_path="items",
        pagination="cursor",
        cursor_path="next",
        max_pages=10,
    )
    assert len(result) == 2
    assert len(client.requests) == 2
    assert ("cursor", "abc") in client.requests[1].params


def test_cursor_pagination_stops_when_cursor_key_omitted() -> None:
    """A final page that OMITS the cursor key is exhausted, not malformed.

    Many APIs signal "no more pages" by dropping the ``next`` key entirely
    rather than sending ``null``; that must end pagination, not raise.
    """
    client = _stub(
        _ok('{"items":[{"a":1}],"next":"abc"}'),
        _ok('{"items":[{"a":2}]}'),
    )
    result = http_fetch(
        url="http://example.com",
        client=client,
        json_path="items",
        pagination="cursor",
        cursor_path="next",
        max_pages=10,
    )
    assert len(result) == 2
    assert len(client.requests) == 2


def test_cursor_pagination_respects_max_pages() -> None:
    client = _stub(
        _ok('{"items":[{"a":1}],"next":"x"}'),
        _ok('{"items":[{"a":2}],"next":"y"}'),
        _ok('{"items":[{"a":3}],"next":"z"}'),
    )
    result = http_fetch(
        url="http://example.com",
        client=client,
        json_path="items",
        pagination="cursor",
        cursor_path="next",
        max_pages=3,
    )
    assert len(client.requests) == 3
    assert len(result) == 3


def test_cursor_pagination_continues_on_falsy_but_present_cursor() -> None:
    """A cursor value of ``0`` (or ``""``) is a real, present cursor -- not "missing".

    Only an *absent* key or an explicit ``null`` means "no more pages" (see
    ``_select_cursor``'s docstring). A falsy-but-present value like the integer
    ``0`` must NOT be treated the same as "missing" and end pagination early.
    """
    client = _stub(
        _ok('{"items":[{"a":1}],"next_cursor":0}'),
        _ok('{"items":[{"a":2}],"next_cursor":null}'),
    )
    result = http_fetch(
        url="http://example.com",
        client=client,
        json_path="items",
        pagination="cursor",
        cursor_path="next_cursor",
        max_pages=10,
    )
    assert len(client.requests) == 2
    assert len(result) == 2
    assert ("cursor", "0") in client.requests[1].params


def test_page_pagination_stops_on_empty_page() -> None:
    client = _stub(
        _ok('[{"a":1}]'),
        _ok('[{"a":2}]'),
        _ok("[]"),
    )
    result = http_fetch(
        url="http://example.com",
        client=client,
        pagination="page",
        page_size=10,
        max_pages=5,
    )
    assert len(result) == 2
    assert len(client.requests) == 3


def test_offset_pagination_advances_offset() -> None:
    client = _stub(
        _ok('[{"a":1}]'),
        _ok('[{"a":2}]'),
        _ok("[]"),
    )
    result = http_fetch(
        url="http://example.com",
        client=client,
        pagination="offset",
        page_size=10,
        max_pages=5,
    )
    assert len(result) == 2
    assert len(client.requests) >= 2
    assert ("offset", "10") in client.requests[1].params


# --- Sorted params / headers --------------------------------------------------


def test_request_params_are_sorted() -> None:
    client = _stub(_ok("[]"))
    http_fetch(url="http://example.com", client=client, params={"b": "2", "a": "1"})
    assert len(client.requests) == 1
    assert client.requests[0].params == (("a", "1"), ("b", "2"))


def test_headers_are_sorted_and_tupled() -> None:
    client = _stub(_ok("[]"))
    http_fetch(url="http://example.com", client=client, headers={"b": "2", "a": "1"})
    assert len(client.requests) == 1
    assert client.requests[0].headers == (("a", "1"), ("b", "2"))
