"""On-disk store for user-authored flow graphs (durable, slug-keyed).

Distinct from ``ExecutionCache`` and ``ArtifactStore``: those hold derived,
disposable outputs (safe to evict, safe to lose). A flow is the user's
authored graph itself -- precious, never evicted, never pickled. Each entry
is a single human-readable JSON file, ``<slug>.ef.json``, under ``root``,
holding the raw graph dict exactly as the canvas sent it. This module never
imports ``emergentflow.ir`` or any IR model -- it stores and returns opaque
JSON dicts, the same boundary the server's other stores keep.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_FLOW_DIRNAME = ".ef-flows"


class UnknownFlowError(KeyError):
    """Raised when a flow slug is not found in the store."""


class FlowAlreadyExistsError(ValueError):
    """Raised when a rename target slug already exists."""


def slugify(name: str) -> str:
    """Convert a flow name to a filesystem-safe slug.

    Lowercased, non-alphanumeric runs collapsed to a single hyphen, leading/
    trailing hyphens stripped. Falls back to ``"untitled"`` when that leaves
    nothing (e.g. an empty or all-punctuation name).
    """
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "untitled"


class FlowStore:
    """On-disk, slug-keyed store for user-authored flow graphs.

    Each entry is one file under ``root``: ``<slug>.ef.json``, the raw graph
    dict serialized with ``indent=2`` for human readability (these files are
    meant to be diff-friendly and hand-editable). Unlike ``ExecutionCache``/
    ``ArtifactStore`` there is no eviction -- flows are precious user data,
    not cached intermediates -- and no size cap.
    """

    def __init__(self, root: Path) -> None:
        root.mkdir(parents=True, exist_ok=True)
        self._root = root
        self._lock = threading.Lock()

    @property
    def root(self) -> Path:
        """The directory backing this store (test/inspection hook)."""
        return self._root

    def _path(self, slug: str) -> Path:
        return self._root / f"{slug}.ef.json"

    def list(self) -> list[dict[str, Any]]:
        """Return ``[{"slug", "name", "updated_at"}, ...]`` sorted newest-first.

        ``updated_at`` is the file's mtime as an ISO 8601 string. ``name`` is
        read from the graph JSON's ``"name"`` field, falling back to the slug
        when absent. A file that fails to parse as JSON (corrupt, mid-write
        from another process, etc.) is skipped rather than raised -- listing
        must never crash on one bad entry.
        """
        entries: list[dict[str, Any]] = []
        with self._lock:
            paths = list(self._root.glob("*.ef.json"))
        for path in paths:
            slug = path.name[: -len(".ef.json")]
            try:
                graph = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            name = graph.get("name", slug) if isinstance(graph, dict) else slug
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            updated_at = datetime.fromtimestamp(mtime, tz=UTC).isoformat()
            entries.append({"slug": slug, "name": name, "updated_at": updated_at})
        entries.sort(key=lambda entry: entry["updated_at"], reverse=True)
        return entries

    def get(self, slug: str) -> dict[str, Any]:
        """Return the full graph JSON for ``slug``. Raise ``UnknownFlowError`` if missing."""
        path = self._path(slug)
        with self._lock:
            if not path.is_file():
                raise UnknownFlowError(slug)
            return json.loads(path.read_text(encoding="utf-8"))

    def save(self, slug: str, graph: dict[str, Any]) -> dict[str, str]:
        """Write ``graph`` to ``<slug>.ef.json``. Idempotent -- overwrites if it exists.

        Writes atomically: serialized to a temp file in the same directory,
        then ``os.replace`` into place, so a crash mid-write never leaves a
        truncated flow file behind.
        """
        path = self._path(slug)
        with self._lock:
            fd, tmp_name = tempfile.mkstemp(
                dir=self._root, prefix=f".{slug}-", suffix=".ef.json.tmp"
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(json.dumps(graph, indent=2))
                os.replace(tmp_name, path)
            except BaseException:
                Path(tmp_name).unlink(missing_ok=True)
                raise
        return {"slug": slug, "status": "ok"}

    def delete(self, slug: str) -> None:
        """Delete ``<slug>.ef.json``. Raise ``UnknownFlowError`` if missing."""
        path = self._path(slug)
        with self._lock:
            if not path.is_file():
                raise UnknownFlowError(slug)
            path.unlink()

    def rename(self, old_slug: str, new_slug: str) -> dict[str, str]:
        """Rename a flow's file from ``old_slug`` to ``new_slug``.

        Raise ``UnknownFlowError`` if ``old_slug`` doesn't exist, or
        ``FlowAlreadyExistsError`` if ``new_slug`` already does.
        """
        old_path = self._path(old_slug)
        new_path = self._path(new_slug)
        with self._lock:
            if not old_path.is_file():
                raise UnknownFlowError(old_slug)
            if new_path.is_file():
                raise FlowAlreadyExistsError(new_slug)
            os.replace(old_path, new_path)
        return {"slug": new_slug, "status": "ok"}


# A process-wide default store, mirroring cache.py's/artifacts.py's singleton
# pattern so the store survives across HTTP requests. ``configure_flows`` must
# run BEFORE the first ``get_default_flows()`` call (i.e. before the server
# starts accepting requests); calling it after the singleton exists is a
# programming error (same guard as ``configure_cache``/``configure_artifacts``).
_default_flows: FlowStore | None = None
_default_flows_lock = threading.Lock()
_configured_flows_root: Path | None = None


def configure_flows(root: Path) -> None:
    """Set the root directory the default FlowStore singleton will use.

    Must be called before the first ``get_default_flows()`` call.
    """
    global _configured_flows_root
    if _default_flows is not None:
        raise RuntimeError(
            "configure_flows() called after the default FlowStore was already created"
        )
    _configured_flows_root = root


def get_default_flows() -> FlowStore:
    """Return the lazily-created process-wide default FlowStore."""
    global _default_flows
    if _default_flows is None:
        with _default_flows_lock:
            if _default_flows is None:
                root = (
                    _configured_flows_root
                    if _configured_flows_root is not None
                    else Path.cwd() / DEFAULT_FLOW_DIRNAME
                )
                _default_flows = FlowStore(root=root)
    return _default_flows
