"""On-disk DAG execution cache (durable, content-hash-keyed).

This is the durable on-disk DAG execution cache (as opposed to
``reports.py``'s ephemeral process-local HTML store). Each cache entry is a
node's raw ``execute()`` output dict, pickled, keyed by a content hash the
caller computes from the node's params + its upstream nodes' hashes (hash
computation itself lives in ``service.py``, a later task -- this module just
stores/retrieves/evicts by whatever hash string it's given).
"""

# Artifacts are pickled (not safetensors) even for objects that could use it
# (e.g. a future torch tensor) -- sklearn models have no native safetensors
# serializer, so pickle is the one format that covers the whole current node
# catalog. This is acceptable for the local, trusted-code app (ADR 0013 §A6,
# the same trust model Jupyter uses) but is NOT safe for a future hosted
# sandbox running untrusted graphs, which will need a different serialization
# strategy.

from __future__ import annotations

import json
import os
import pickle
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from emergentflow import __version__

DEFAULT_CACHE_DIRNAME = ".ef-cache"
DEFAULT_CACHE_MAX_MB = 500.0


class ExecutionCache:
    """On-disk, content-hash-keyed store for node execution outputs.

    Each entry is two files under ``root``: ``<hash>.pkl`` (the pickled outputs
    dict) and ``<hash>.meta.json`` (a sidecar with ``node_id``, ``label``,
    ``sdk_version``, and ``timestamp``). Eviction is LRU by file mtime, run after
    every ``put()`` (not just at startup) so the cache stays under ``max_mb``
    continuously during a long-running server session. A cache hit (``get``)
    also refreshes the entry's mtime, so a frequently-reused artifact is
    protected from eviction even if it was written long ago -- true
    least-recently-*used*, not least-recently-*written*.
    """

    def __init__(self, root: Path | None = None, max_mb: float = DEFAULT_CACHE_MAX_MB) -> None:
        if root is None:
            root = Path(tempfile.mkdtemp(prefix="ef-cache-"))
        root.mkdir(parents=True, exist_ok=True)
        self._root = root
        self._max_mb = max_mb
        self._lock = threading.Lock()

    @property
    def root(self) -> Path:
        """The directory backing this cache (test/inspection hook)."""
        return self._root

    def _pkl_path(self, cache_hash: str) -> Path:
        return self._root / f"{cache_hash}.pkl"

    def _meta_path(self, cache_hash: str) -> Path:
        return self._root / f"{cache_hash}.meta.json"

    def get(self, cache_hash: str) -> dict[str, Any] | None:
        """Return the cached outputs dict for ``cache_hash``, or None on a miss.

        A hit refreshes the entry's mtime (LRU recency) so it survives future
        evictions longer. Any read/unpickle failure (corrupt file, e.g. from
        a concurrent eviction) is treated as a miss rather than raised --
        a cache read must never crash a graph run. Takes ``self._lock`` for
        the whole read (not just the unpickle) so it can't race a concurrent
        ``put()``'s eviction pass unlinking this same file between the read
        and the recency-refreshing ``os.utime`` calls below.
        """
        pkl_path = self._pkl_path(cache_hash)
        with self._lock:
            if not pkl_path.is_file():
                return None
            try:
                with pkl_path.open("rb") as f:
                    outputs = pickle.load(f)
            except Exception:
                return None
            now = time.time()
            os.utime(pkl_path, (now, now))
            meta_path = self._meta_path(cache_hash)
            if meta_path.is_file():
                os.utime(meta_path, (now, now))
        return outputs

    def put(self, cache_hash: str, outputs: dict[str, Any], *, node_id: str, label: str) -> None:
        """Store ``outputs`` under ``cache_hash``, with a ``.meta.json`` sidecar.

        Idempotent by hash (a re-put of the same hash overwrites in place).
        Runs LRU eviction to ``max_mb`` afterward, unconditionally.
        """
        with self._lock:
            pkl_path = self._pkl_path(cache_hash)
            with pkl_path.open("wb") as f:
                pickle.dump(outputs, f)
            meta_path = self._meta_path(cache_hash)
            meta_path.write_text(
                json.dumps(
                    {
                        "node_id": node_id,
                        "label": label,
                        "sdk_version": __version__,
                        "timestamp": time.time(),
                    }
                ),
                encoding="utf-8",
            )
            self._evict_to_cap()

    def clear(self) -> None:
        """Remove every cache file (both ``.pkl`` and ``.meta.json``) under ``root``."""
        with self._lock:
            for path in self._root.iterdir():
                if path.is_file():
                    path.unlink()

    def _evict_to_cap(self) -> None:
        """Delete oldest-by-mtime entries (pkl + its meta sidecar) until under ``max_bytes``.

        Must be called with ``self._lock`` already held (only ``put`` calls this).
        If a single entry's pickled size alone exceeds the cap, it is left in
        place once every other entry has been evicted -- eviction only removes
        entries, it never refuses a ``put``.
        """
        max_bytes = self._max_mb * 1024 * 1024
        pkl_paths = sorted(self._root.glob("*.pkl"), key=lambda p: p.stat().st_mtime)

        def total_bytes() -> int:
            return sum(p.stat().st_size for p in self._root.iterdir() if p.is_file())

        while len(pkl_paths) > 1 and total_bytes() > max_bytes:
            oldest = pkl_paths.pop(0)
            cache_hash = oldest.stem
            oldest.unlink(missing_ok=True)
            self._meta_path(cache_hash).unlink(missing_ok=True)


# A process-wide default cache so service.py's execute path and the
# POST /cache/clear route (app.py) share one cache without an import cycle.
# Unlike reports.py's ReportStore (always an anonymous temp dir),
# ExecutionCache's root and size cap are user-configurable (CLI ``--cache-dir``
# / ``--cache-max-mb``), so ``configure_cache`` must run BEFORE the first
# ``get_default_cache`` call -- i.e. before the server starts accepting
# requests. Calling it after the singleton already exists is a programming
# error (it would silently do nothing for in-flight/future requests that
# already resolved the old instance), so it raises rather than reconfiguring.
_default_cache: ExecutionCache | None = None
_default_cache_lock = threading.Lock()
_configured_root: Path | None = None
_configured_max_mb: float = DEFAULT_CACHE_MAX_MB


def configure_cache(root: Path, max_mb: float = DEFAULT_CACHE_MAX_MB) -> None:
    """Set the (root, max_mb) the default ExecutionCache singleton will use.

    Must be called before the first ``get_default_cache()`` call.
    """
    global _configured_root, _configured_max_mb
    if _default_cache is not None:
        raise RuntimeError(
            "configure_cache() called after the default ExecutionCache was already created"
        )
    _configured_root = root
    _configured_max_mb = max_mb


def get_default_cache() -> ExecutionCache:
    """Return the lazily-created process-wide default ExecutionCache.

    Double-checked locking for the same reason as reports.py's
    get_default_store: concurrent requests run on separate worker threads
    (app.py's run_in_executor dispatch), so a naive check-then-act lazy-init
    could race and produce two different cache instances.
    """
    global _default_cache
    if _default_cache is None:
        with _default_cache_lock:
            if _default_cache is None:
                root = (
                    _configured_root
                    if _configured_root is not None
                    else Path.cwd() / DEFAULT_CACHE_DIRNAME
                )
                _default_cache = ExecutionCache(root=root, max_mb=_configured_max_mb)
    return _default_cache
