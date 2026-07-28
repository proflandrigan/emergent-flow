"""
emergentflow.data.http.fetch
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``ef.data.http_fetch`` — the single wrapper both the ``http_fetch`` node's
``codegen`` and ``execute`` route through. Routing both paths through one wrapper
is what makes ADR-0002 equivalence hold by construction (the ADR-0017
``ef.llm.call`` pattern applied to a third effect).

Pure aside from the single delegated effect ``client.fetch(request)``. No
``os.environ``, no socket, no ``urllib`` import — the effect lives entirely
inside the injected client.
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

from emergentflow.api import public_op
from emergentflow.data.errors import DataLoadError
from emergentflow.data.http.protocol import HttpClient, HttpRequest, HttpResponse

__all__ = [
    "http_fetch",
    "MissingHttpClientError",
    "PAGINATION_MODES",
]

#: Pagination modes ``http_fetch`` supports.
PAGINATION_MODES: tuple[str, ...] = ("none", "cursor", "offset", "page")


class MissingHttpClientError(RuntimeError):
    """Raised by ``http_fetch()`` when no ``HttpClient`` was injected.

    The single place that enforces "an http_fetch node needs a client" — both
    ``execute`` and a compiled module's ``main()`` route through ``http_fetch()``, so
    they raise identically for identical reasons (ADR 0002).
    """


def _parse_body(response: HttpResponse) -> Any:
    """Check *response* for a 2xx status and parse body as JSON."""
    if not response.ok:
        body_preview = response.body[:500]
        if len(response.body) > 500:
            body_preview += "..."
        raise DataLoadError(f"HTTP {response.status} from {response.url}: {body_preview}")
    try:
        return json.loads(response.body)
    except json.JSONDecodeError as exc:
        body_preview = response.body[:200]
        if len(response.body) > 200:
            body_preview += "..."
        raise DataLoadError(
            f"HTTP {response.status}: response body is not valid JSON: {body_preview}"
        ) from exc


def _select_path(payload: object, json_path: str | None) -> object:
    """Walk *payload* along a dot-separated *json_path* and return the sub-value.

    Only dot-separated object keys are supported — no wildcards, no array
    indexing. This is deliberate, to avoid a jsonpath dependency.
    """
    if json_path is None or json_path == "":
        return payload
    parts = json_path.split(".")
    current: Any = payload
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, dict):
            available = sorted(current.keys())
            raise DataLoadError(
                f"JSON path {json_path!r} failed at segment {part!r}: "
                f"key not found. Available keys at that level: {available}"
            )
        else:
            raise DataLoadError(
                f"JSON path {json_path!r} failed at segment {part!r}: "
                f"value at that level is type {type(current).__name__!r}, not a dict"
            )
    return current


def _records_to_frame(records: object, *, flatten: bool) -> pd.DataFrame:
    """Convert *records* (list or dict) to a tidy DataFrame."""
    if isinstance(records, list):
        if not records:
            return pd.DataFrame()
        if flatten:
            return pd.json_normalize(records)
        return pd.DataFrame(records)
    if isinstance(records, dict):
        lst = [records]
        if flatten:
            return pd.json_normalize(lst)
        return pd.DataFrame(lst)
    raise DataLoadError(
        f"Selected payload must be a list of records or a single record object, "
        f"got {type(records).__name__!r}"
    )


def _select_cursor(payload: object, cursor_path: str) -> object | None:
    """Return the next-page cursor at *cursor_path*, or ``None`` if it is absent.

    Deliberately more forgiving than :func:`_select_path`: an API that signals
    "no more pages" by *omitting* the cursor key entirely (the common
    ``Link``-header / ``next``-key shape) is exhausted, not malformed, so a
    missing path ends pagination instead of raising ``DataLoadError``.
    """
    current: Any = payload
    for part in cursor_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


@public_op(name="ef.data.http_fetch")
def http_fetch(
    *,
    url: str,
    client: HttpClient | None,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
    body: str | None = None,
    connection: str | None = None,
    timeout_s: float | None = None,
    json_path: str | None = None,
    flatten: bool = True,
    pagination: str = "none",
    cursor_param: str = "cursor",
    cursor_path: str | None = None,
    page_param: str = "page",
    offset_param: str = "offset",
    page_size: int | None = None,
    max_pages: int = 10,
) -> pd.DataFrame:
    """Fetch a URL through *client* and return a tidy DataFrame of records.

    Pure aside from the single delegated effect ``client.fetch(request)``.

    Raises
    ------
    MissingHttpClientError
        If *client* is ``None``.
    ValueError
        If *pagination* is not one of ``PAGINATION_MODES``, *max_pages* < 1,
        cursor pagination is used without *cursor_path*, or offset/page
        pagination is used without *page_size*.
    DataLoadError
        If the response is non-2xx, the body is not valid JSON, or the
        selected path does not resolve to a list or dict of records.
    """
    if client is None:
        raise MissingHttpClientError(
            "ef.data.http_fetch requires an injected HttpClient; pass it via "
            "execute(graph, clients=Clients(http=...)) or the compiled module's "
            "main(clients=...)."
        )
    if pagination not in PAGINATION_MODES:
        raise ValueError(f"pagination must be one of {PAGINATION_MODES!r}, got {pagination!r}")
    if max_pages < 1:
        raise ValueError(f"max_pages must be >= 1, got {max_pages}")
    if pagination == "cursor" and cursor_path is None:
        raise ValueError(
            "cursor_path is required when pagination is 'cursor'; "
            "cursor pagination cannot advance without knowing where the "
            "next cursor lives."
        )
    if pagination in ("offset", "page") and page_size is None:
        raise ValueError(
            f"page_size is required when pagination is {pagination!r}; "
            "offset/page pagination needs a page size."
        )

    all_records: list[dict[str, Any]] = []
    next_cursor: str | None = None

    for page_index in range(max_pages):
        page_params: dict[str, str] = dict(params or {})

        if pagination == "none":
            pass
        elif pagination == "cursor":
            if page_index > 0 and next_cursor is not None:
                page_params[cursor_param] = next_cursor
        elif pagination == "offset":
            assert page_size is not None  # validated above
            page_params[offset_param] = str(page_index * page_size)
        elif pagination == "page":
            page_params[page_param] = str(page_index + 1)

        # Sorting both header and param pairs is load-bearing — it makes the
        # request's content_hash() deterministic regardless of dict insertion
        # order, so replay fixtures key stably.
        request = HttpRequest(
            url=url,
            method=method,
            headers=tuple(sorted((headers or {}).items())),
            params=tuple(sorted(page_params.items())),
            body=body,
            connection=connection,
            timeout_s=timeout_s,
        )

        response = client.fetch(request)
        parsed = _parse_body(response)
        records = _select_path(parsed, json_path)

        if isinstance(records, list):
            all_records.extend(records)
        elif isinstance(records, dict):
            all_records.append(records)
        else:
            raise DataLoadError(
                f"Selected payload must be a list of records or a single record object, "
                f"got {type(records).__name__!r}"
            )

        if pagination == "none":
            break
        elif pagination == "cursor":
            assert cursor_path is not None  # validated above
            next_cursor_obj = _select_cursor(parsed, cursor_path)
            if not next_cursor_obj:
                break
            next_cursor = str(next_cursor_obj)
        elif pagination in ("offset", "page") and isinstance(records, list) and len(records) == 0:
            break

    return _records_to_frame(all_records, flatten=flatten)
