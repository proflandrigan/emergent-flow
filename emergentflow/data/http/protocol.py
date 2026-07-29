"""
emergentflow.data.http.protocol
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The ``HttpClient`` seam types (Epic 16 Story 1, ADR 0017/0018 pattern):
the single injected boundary between the pure SDK core and any real or
replayed HTTP fetch.

``HttpRequest`` is a pure, JSON-native, hashable description of one fetch —
building it from node inputs is pure. It carries a connection-profile **name**
only, never a credential (same as ``QueryRequest``), so its content hash —
used to key replay fixtures — is safe to compute and commit.

``HttpResponse`` carries only materialized text and plain metadata: no live
socket, connection, or urllib handle is ever stored here, so the response
rides the ``@public_op`` inspectable contract and the ADR-0002 equivalence
gate compares it value-for-value.

This module mirrors ``emergentflow.data.warehouse.protocol`` deliberately:
the HTTP effect is the same shape of problem as the warehouse/LLM effect
(non-deterministic, credentialed, metered network I/O), so it reuses the
same seam pattern rather than inventing a new one.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from typing import Protocol, runtime_checkable


@dataclasses.dataclass(frozen=True)
class HttpRequest:
    """A pure, JSON-native description of one HTTP request.

    Attributes
    ----------
    url: the target URL.
    method: the HTTP method (``"GET"``, ``"POST"``, etc.).
    headers: header **names** and non-secret values only. A resolved
        credential is **never** stored here — the auth header is injected
        by the live client at call time from an env-var name, so the content
        hash is safe to commit as a fixture key.
    params: query-string parameters.
    body: the request body, if any.
    connection: the connection-profile **name** (e.g. ``"http_api_prod"``) —
        never a host, token, or credential. The effectful client resolves
        the profile to live credentials at ``fetch()`` time.
    timeout_s: optional timeout in seconds.
    """

    url: str
    method: str = "GET"
    headers: tuple[tuple[str, str], ...] = ()
    params: tuple[tuple[str, str], ...] = ()
    body: str | None = None
    connection: str | None = None
    timeout_s: float | None = None

    def content_hash(self) -> str:
        """Return a stable sha256 hex digest identifying this request's content.

        Used by ``ReplayHttpClient`` to key recorded fixtures. Built from a
        JSON-native, sorted-keys serialization of every field so the hash is
        stable across process runs and Python versions. Nothing secret is
        present to exclude — the connection is a profile *name* and headers
        carry only non-secret values.
        """
        payload = {
            "url": self.url,
            "method": self.method,
            "headers": [list(pair) for pair in self.headers],
            "params": [list(pair) for pair in self.params],
            "body": self.body,
            "connection": self.connection,
            "timeout_s": self.timeout_s,
        }
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclasses.dataclass(frozen=True)
class HttpResponse:
    """The inspectable result of one HTTP request (Epic 16 Story 1).

    Carries only the materialized response text and plain metadata. No live
    socket, connection, or urllib handle is ever stored here — only the
    materialized text and plain metadata, so the response rides the
    ``@public_op`` inspectable contract and the ADR-0002 equivalence gate
    compares it value-for-value.

    Attributes
    ----------
    status: the HTTP status code.
    body: the raw response text.
    headers: response header name/value pairs.
    url: the final URL after any redirect.
    elapsed_ms: wall-clock latency, if available.
    """

    status: int
    body: str
    headers: tuple[tuple[str, str], ...] = ()
    url: str = ""
    elapsed_ms: float | None = None

    @property
    def ok(self) -> bool:
        """Return True if the status code indicates success (2xx)."""
        return 200 <= self.status < 300


class FixtureMissError(LookupError):
    """Raised by ``ReplayHttpClient`` when a request hash has no fixture.

    Mirrors ``emergentflow.data.warehouse.protocol.FixtureMissError``. The
    message includes the request's ``content_hash()`` and a copy-pasteable
    ``write_http_fixture(...)`` hint so a developer hitting it in a test run
    knows exactly what to record.
    """


@runtime_checkable
class HttpClient(Protocol):
    """The injected HTTP seam every ``http_fetch`` node depends on (Epic 16).

    Mirrors ``emergentflow.data.warehouse.protocol.WarehouseClient``: any
    object exposing the ``fetch`` method satisfies the protocol structurally
    (no inheritance required). ``ReplayHttpClient`` (pure, tests + the gate)
    and the live adapter are the implementations that ship with this package.
    """

    def fetch(self, request: HttpRequest) -> HttpResponse:
        """Perform one HTTP request and return an inspectable ``HttpResponse``."""
        ...


__all__ = [
    "FixtureMissError",
    "HttpClient",
    "HttpRequest",
    "HttpResponse",
]
