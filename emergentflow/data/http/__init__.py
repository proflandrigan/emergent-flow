"""
emergentflow.data.http
~~~~~~~~~~~~~~~~~~~~~~~
The HTTP/REST ingestion seam (Epic 16 Story 1, ADR 0017/0018 pattern).

An ``http_fetch`` node is ``requires_client``: it never calls the network inline.
This package holds the pure seam types (``protocol``), the offline replay client,
and the live adapter, mirroring ``emergentflow.data.warehouse``.
"""

from __future__ import annotations

from emergentflow.data.http.protocol import (
    FixtureMissError,
    HttpClient,
    HttpRequest,
    HttpResponse,
)

__all__ = [
    "FixtureMissError",
    "HttpClient",
    "HttpRequest",
    "HttpResponse",
]
