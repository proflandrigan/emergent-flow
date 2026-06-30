"""Process-local store for large HTML report blobs (Epic 7 Story 3).

Some nodes (e.g. ``ef.report.profile``) emit multi-megabyte HTML reports. Rather
than inline that into every ``/execute`` payload (and every ``srcdoc`` the canvas
renders), the execute path registers the HTML here and hands the canvas a short
``report_hash``; the canvas fetches the full document from ``GET /reports/{hash}``.

This is deliberately ephemeral and process-local (a fresh temp dir per store,
cleaned up by the OS), in keeping with the trusted local-app model (ADR 0013 §A6).
It is NOT the durable on-disk DAG cache (roadmap Epic 7) -- it only de-bloats the
result payload for the current server process.
"""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

# Reports are keyed by the first 16 hex chars of the sha256 of the UTF-8 bytes.
# 64 bits of collision resistance is ample for a single process's report set and
# keeps URLs short. Hash length is fixed so the endpoint can validate the shape.
_HASH_LEN = 16


def _hash_html(html: str) -> str:
    """Return the report key: ``sha256(html.encode("utf-8")).hexdigest()[:16]``."""
    return hashlib.sha256(html.encode("utf-8")).hexdigest()[:_HASH_LEN]


class ReportStore:
    """Stores HTML report blobs on disk keyed by a content hash.

    Each instance owns a private temp directory; ``put`` writes ``<hash>.html``
    and returns the hash, ``get`` reads it back (or ``None`` if unknown). Writing
    the same HTML twice is idempotent (same hash, same file). Not thread-isolated
    state beyond the filesystem -- concurrent writes of identical content are safe
    because the path is content-addressed.
    """

    def __init__(self, root: Path | None = None) -> None:
        if root is None:
            root = Path(tempfile.mkdtemp(prefix="ef-reports-"))
        root.mkdir(parents=True, exist_ok=True)
        self._root = root

    @property
    def root(self) -> Path:
        """The directory backing this store (test/inspection hook)."""
        return self._root

    def _path_for(self, report_hash: str) -> Path:
        return self._root / f"{report_hash}.html"

    def put(self, html: str) -> str:
        """Store *html* and return its ``report_hash``. Idempotent by content."""
        report_hash = _hash_html(html)
        self._path_for(report_hash).write_text(html, encoding="utf-8")
        return report_hash

    def get(self, report_hash: str) -> str | None:
        """Return the stored HTML for *report_hash*, or ``None`` if not present.

        Validates the key shape (16 lowercase hex chars) before touching the
        filesystem so a malformed/path-traversal key can never resolve to a file.
        """
        if len(report_hash) != _HASH_LEN or any(c not in "0123456789abcdef" for c in report_hash):
            return None
        path = self._path_for(report_hash)
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8")


# A process-wide default store so the execute path (service.py) and the
# GET /reports/{hash} route (app.py) share one set of report files without an
# import cycle (both import this accessor, neither imports the other).
_default_store: ReportStore | None = None


def get_default_store() -> ReportStore:
    """Return the lazily-created process-wide default :class:`ReportStore`."""
    global _default_store
    if _default_store is None:
        _default_store = ReportStore()
    return _default_store
