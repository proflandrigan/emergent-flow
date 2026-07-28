"""
emergentflow.data.http.replay
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``ReplayHttpClient`` — the pure ``HttpClient`` implementation used by tests and
the ADR-0002 equivalence harness. Replays a recorded ``HttpResponse`` keyed by
the requesting ``HttpRequest.content_hash()``; never touches the network.

Fixtures are content-addressed JSON files, one per recorded response, named
``<content_hash>.json``. ``write_http_fixture`` is the companion writer used to
seed fixtures from a live or hand-built ``HttpResponse``.

Mirrors ``emergentflow.data.warehouse.replay`` deliberately — the HTTP effect
reuses the same seam pattern rather than inventing a new one.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from emergentflow.data.http.protocol import (
    FixtureMissError,
    HttpRequest,
    HttpResponse,
)

__all__ = [
    "ReplayHttpClient",
    "write_http_fixture",
]


def _fixture_path(fixtures_dir: Path, content_hash: str) -> Path:
    return fixtures_dir / f"{content_hash}.json"


def _response_to_dict(response: HttpResponse) -> dict:
    return {
        "status": response.status,
        "body": response.body,
        "headers": [list(pair) for pair in response.headers],
        "url": response.url,
        "elapsed_ms": response.elapsed_ms,
    }


def _response_from_dict(payload: dict) -> HttpResponse:
    # Convert headers back to tuple-of-tuples so the frozen dataclass stays
    # hashable — JSON has no tuple type, so this conversion is load-bearing.
    headers: tuple[tuple[str, str], ...] = tuple((h[0], h[1]) for h in payload["headers"])
    return HttpResponse(
        status=payload["status"],
        body=payload["body"],
        headers=headers,
        url=payload["url"],
        elapsed_ms=payload["elapsed_ms"],
    )


def write_http_fixture(
    fixtures_dir: str | os.PathLike[str],
    request: HttpRequest,
    response: HttpResponse,
) -> Path:
    """Write *response* as a content-addressed fixture for *request*.

    Creates *fixtures_dir* if it does not exist. The fixture file is named
    ``<request.content_hash()>.json``. Returns the path written. This is the
    seeding path used by tests and any future ``--record`` tooling that captures
    a live ``HttpResponse``.
    """
    dir_path = Path(fixtures_dir)
    dir_path.mkdir(parents=True, exist_ok=True)
    path = _fixture_path(dir_path, request.content_hash())
    path.write_text(json.dumps(_response_to_dict(response), indent=2, sort_keys=True) + "\n")
    return path


class ReplayHttpClient:
    """A pure ``HttpClient`` that replays recorded ``HttpResponse``s from disk.

    Structurally satisfies ``emergentflow.data.http.protocol.HttpClient``.
    Constructs no live connection.

    Parameters
    ----------
    fixtures_dir:
        Directory containing ``<content_hash>.json`` fixture files. The caller (a
        test, the equivalence harness) chooses this path; this class has no
        default so the library stays agnostic of where fixtures live.
    """

    def __init__(self, fixtures_dir: str | os.PathLike[str]) -> None:
        self.fixtures_dir = Path(fixtures_dir)

    def fetch(self, request: HttpRequest) -> HttpResponse:
        """Replay the fixture recorded for *request*.

        Does not raise on a non-2xx replayed status — a recorded 404 must replay
        faithfully as a 404 ``HttpResponse``; deciding what a non-2xx means is
        the caller's job, not the client's.

        Raises
        ------
        FixtureMissError
            If no fixture exists for ``request.content_hash()``. The message
            includes the hash and a copy-pasteable ``write_http_fixture(...)`` call.
        """
        content_hash = request.content_hash()
        path = _fixture_path(self.fixtures_dir, content_hash)
        if not path.exists():
            raise FixtureMissError(
                f"No recorded fixture for HTTP request hash {content_hash!r} "
                f"(looked in {self.fixtures_dir}). To record one:\n"
                f"    from emergentflow.data.http.replay import write_http_fixture\n"
                f"    write_http_fixture({str(self.fixtures_dir)!r}, request, response)  "
                f"# response is the HttpResponse you want this request to replay"
            )
        payload = json.loads(path.read_text())
        return _response_from_dict(payload)
