"""Last-output-per-node store for explicit partial runs (issue #105).

Distinct from ``ExecutionCache``: the content-hash cache governs *implicit*
reuse during a normal run (is this output reproducible from params?), while
this store captures the last successful output of every node regardless of
cacheability, read *only* when the user explicitly asks for a partial run
(``run_only`` / ``run_from``). Keeping the two stores separate means full-run
semantics stay byte-identical while explicit partial runs can reuse a
``load_csv`` frame whose source was never cacheable.

Like ``ExecutionCache``: pickled output dicts, a ``.meta.json`` sidecar, LRU
eviction by mtime, and a process-wide singleton so the store survives across
HTTP requests. Unlike it: keys are node ids (unique across graphs — freshly
minted UUIDs in ``NodeDefinition.instantiate``), not content hashes, so there
is exactly one entry per node id at any time — a ``put`` overwrites the
previous output for that node. Staleness is the user's call: a partial run
that reuses a stored ``load_csv`` frame after the CSV changed is the requested
behaviour, not a silent bug.
"""

# Artifacts are pickled for the same reason ExecutionCache uses pickle: sklearn
# models (and most node outputs) have no native safetensors serializer, so pickle
# is the one format that covers the whole node catalog. Same trust model as
# ExecutionCache (ADR 0013 §A6) — acceptable for the local, trusted-code app,
# NOT safe for a future hosted sandbox running untrusted graphs.

from __future__ import annotations

import hashlib
import json
import os
import pickle
import re
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from emergentflow import __version__

DEFAULT_ARTIFACT_DIRNAME = ".ef-artifacts"
DEFAULT_ARTIFACT_MAX_MB = 500.0

_SAFE_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def _safe_key(node_id: str) -> str:
    """Map a node id to a filename-safe key.

    Node ids come from client-supplied graph JSON and are otherwise unconstrained, so an id
    containing ``/`` or ``..`` must never reach the filesystem path. Ordinary ids (UUIDs,
    slugs) pass through unchanged; anything else is replaced by a stable digest.
    """
    if _SAFE_KEY_RE.match(node_id):
        return node_id
    return "h-" + hashlib.sha256(node_id.encode("utf-8")).hexdigest()[:40]


class ArtifactStore:
    """On-disk, node-id-keyed store for the last successful output of each node.

    Each entry is two files under ``root``: ``<node_id>.pkl`` (the pickled
    outputs dict) and ``<node_id>.meta.json`` (a sidecar with ``node_id``,
    ``label``, ``sdk_version``, ``timestamp``, and a per-put ``revision``). Eviction is LRU by file
    mtime, run after every ``put()`` so the store stays under ``max_mb``
    continuously during a long-running server session. A read (``get``) also
    refreshes the entry's mtime, so a frequently-reused artifact is protected
    from eviction — true least-recently-*used*, not least-recently-*written*.
    """

    def __init__(self, root: Path | None = None, max_mb: float = DEFAULT_ARTIFACT_MAX_MB) -> None:
        if root is None:
            root = Path(tempfile.mkdtemp(prefix="ef-artifacts-"))
        root.mkdir(parents=True, exist_ok=True)
        self._root = root
        self._max_mb = max_mb
        self._lock = threading.Lock()
        self._last_revision = 0

    @property
    def root(self) -> Path:
        """The directory backing this store (test/inspection hook)."""
        return self._root

    def _pkl_path(self, node_id: str) -> Path:
        return self._root / f"{_safe_key(node_id)}.pkl"

    def _meta_path(self, node_id: str) -> Path:
        return self._root / f"{_safe_key(node_id)}.meta.json"

    def get(self, node_id: str) -> dict[str, Any] | None:
        """Return the stored outputs dict for *node_id*, or ``None`` on a miss.

        A hit refreshes the entry's mtime (LRU recency). Any read/unpickle
        failure is treated as a miss rather than raised — a store read must
        never crash a graph run. Takes ``self._lock`` for the whole read so it
        can't race a concurrent ``put()``'s eviction pass.
        """
        hit = self.get_with_revision(node_id)
        return None if hit is None else hit[0]

    def get_with_revision(self, node_id: str) -> tuple[dict[str, Any], str | None] | None:
        """Return ``(outputs, revision)`` for *node_id*, or ``None`` on a miss.

        The unpickle and the revision read happen under one lock hold, so the
        pair is always consistent with a single ``put``. ``revision`` is ``None``
        only for a legacy entry written before revisions existed.
        """
        pkl_path = self._pkl_path(node_id)
        with self._lock:
            if not pkl_path.is_file():
                return None
            try:
                with pkl_path.open("rb") as f:
                    outputs = pickle.load(f)
            except Exception:
                return None
            revision = self._read_revision(node_id)
            now = time.time()
            os.utime(pkl_path, (now, now))
            meta_path = self._meta_path(node_id)
            if meta_path.is_file():
                os.utime(meta_path, (now, now))
        return outputs, revision

    def get_meta(self, node_id: str) -> dict[str, Any] | None:
        """Return the ``.meta.json`` sidecar for *node_id* without unpickling.

        ``None`` on a miss (no pickle, or an unreadable sidecar). Does not
        refresh LRU recency: peeking at metadata is not a use of the output.
        """
        with self._lock:
            if not self._pkl_path(node_id).is_file():
                return None
            return self._read_meta(node_id)

    def _read_meta(self, node_id: str) -> dict[str, Any] | None:
        try:
            meta = json.loads(self._meta_path(node_id).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return meta if isinstance(meta, dict) else None

    def _read_revision(self, node_id: str) -> str | None:
        meta = self._read_meta(node_id)
        revision = meta.get("revision") if meta else None
        return revision if isinstance(revision, str) else None

    def put(self, node_id: str, outputs: dict[str, Any], *, label: str = "") -> str:
        """Store *outputs* for *node_id*, with a ``.meta.json`` sidecar.

        Idempotent by node id (a re-put overwrites in place). Returns a fresh
        revision id (also written to the sidecar) that changes on every put, so
        a caller can later detect that the stored output was replaced or evicted.
        Both files are written via tmp + ``os.replace``. Runs LRU eviction to
        ``max_mb`` afterward, unconditionally.
        """
        with self._lock:
            revision = self._next_revision()
            pkl_path = self._pkl_path(node_id)
            pkl_tmp = pkl_path.with_name(pkl_path.name + ".tmp")
            meta_path = self._meta_path(node_id)
            meta_tmp = meta_path.with_name(meta_path.name + ".tmp")
            try:
                with pkl_tmp.open("wb") as f:
                    pickle.dump(outputs, f)
                meta_tmp.write_text(
                    json.dumps(
                        {
                            "node_id": node_id,
                            "label": label,
                            "sdk_version": __version__,
                            "timestamp": time.time(),
                            "revision": revision,
                        }
                    ),
                    encoding="utf-8",
                )
                os.replace(pkl_tmp, pkl_path)
                os.replace(meta_tmp, meta_path)
            finally:
                pkl_tmp.unlink(missing_ok=True)
                meta_tmp.unlink(missing_ok=True)
            self._evict_to_cap()
        return revision

    def _next_revision(self) -> str:
        """A revision id strictly greater than every earlier one from this store.

        Must be called with ``self._lock`` held. ``time_ns`` alone can repeat on
        a coarse clock, so bump past the previous value when it does.
        """
        value = max(time.time_ns(), self._last_revision + 1)
        self._last_revision = value
        return f"{value:x}"

    def clear(self) -> None:
        """Remove every store file (both ``.pkl`` and ``.meta.json``) under ``root``."""
        with self._lock:
            for path in self._root.iterdir():
                if path.is_file():
                    path.unlink()

    def _evict_to_cap(self) -> None:
        """Delete oldest-by-mtime entries until under ``max_bytes``.

        Must be called with ``self._lock`` already held (only ``put`` calls this).
        If a single entry's size alone exceeds the cap, it is left in place
        once every other entry has been evicted.
        """
        max_bytes = self._max_mb * 1024 * 1024
        pkl_paths = sorted(self._root.glob("*.pkl"), key=lambda p: p.stat().st_mtime)

        def total_bytes() -> int:
            return sum(p.stat().st_size for p in self._root.iterdir() if p.is_file())

        while len(pkl_paths) > 1 and total_bytes() > max_bytes:
            oldest = pkl_paths.pop(0)
            node_id = oldest.stem
            oldest.unlink(missing_ok=True)
            self._meta_path(node_id).unlink(missing_ok=True)


# A process-wide default store, mirroring ``cache.py``'s singleton pattern so
# the store survives across HTTP requests. ``configure_artifacts`` must run
# BEFORE the first ``get_default_artifacts`` call (i.e. before the server starts
# accepting requests); calling it after the singleton exists is a programming
# error (same guard as ``configure_cache``).
_default_artifacts: ArtifactStore | None = None
_default_artifacts_lock = threading.Lock()
_configured_artifacts_root: Path | None = None
_configured_artifacts_max_mb: float = DEFAULT_ARTIFACT_MAX_MB


def configure_artifacts(root: Path, max_mb: float = DEFAULT_ARTIFACT_MAX_MB) -> None:
    """Set the (root, max_mb) the default ArtifactStore singleton will use.

    Must be called before the first ``get_default_artifacts()`` call.
    """
    global _configured_artifacts_root, _configured_artifacts_max_mb
    if _default_artifacts is not None:
        raise RuntimeError(
            "configure_artifacts() called after the default ArtifactStore was already created"
        )
    _configured_artifacts_root = root
    _configured_artifacts_max_mb = max_mb


def get_default_artifacts() -> ArtifactStore:
    """Return the lazily-created process-wide default ArtifactStore."""
    global _default_artifacts
    if _default_artifacts is None:
        with _default_artifacts_lock:
            if _default_artifacts is None:
                root = (
                    _configured_artifacts_root
                    if _configured_artifacts_root is not None
                    else Path.cwd() / DEFAULT_ARTIFACT_DIRNAME
                )
                _default_artifacts = ArtifactStore(root=root, max_mb=_configured_artifacts_max_mb)
    return _default_artifacts
