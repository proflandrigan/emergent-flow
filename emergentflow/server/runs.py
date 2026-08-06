"""Append-only on-disk store for execution runs (per-run directories, LRU eviction).

Each run is stored as a directory ``.ef-runs/<run_id>/`` containing three JSON
files: ``run.json`` (metadata), ``graph.json`` (the graph snapshot), and
``payloads.json`` (scalar node outputs, size-capped at 100KB per entry). Runs
are never modified after creation -- this is an append-only log. Oldest entries
are evicted after each ``save()`` to stay under the configured ``keep`` cap.

This module never imports ``emergentflow.ir`` or any IR model -- it stores and
returns opaque JSON dicts, the same boundary the server's other stores keep.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_RUNS_DIRNAME = ".ef-runs"
DEFAULT_RUNS_KEEP = 50

# Every run_id this store will accept must match the format produced by
# _generate_run_id(): ``YYYY-MM-DDTHH-MM-SSZ-<short_hash>``. This is the sole
# choke point that keeps a run_id from ever containing a path separator or a
# ".." component -- without this check a value like ``"../../tmp/evil"`` would
# resolve outside ``root``.
_RUN_ID_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z-[a-f0-9]+$")

_PAYLOAD_SIZE_CAP = 100 * 1024  # 100 KB


def _generate_run_id() -> str:
    """Generate a timestamp-based run id: ``2026-07-30T14-02-11Z-<short_hash>``."""
    now = datetime.now(tz=UTC)
    ts = now.strftime("%Y-%m-%dT%H-%M-%SZ")
    # Short hash from time + random for disambiguation
    raw = f"{time.time()}{os.urandom(4).hex()}"
    short_hash = hashlib.sha256(raw.encode()).hexdigest()[:4]
    return f"{ts}-{short_hash}"


class UnknownRunError(KeyError):
    """Raised when a run_id is not found in the store."""


class InvalidRunIdError(ValueError):
    """Raised when a run_id doesn't match the expected format.

    This is a security boundary, not just input hygiene: every store method
    resolves a run_id to a filesystem path, so an unvalidated run_id containing
    ``/`` or ``..`` could otherwise be used to read, write, or delete files
    outside ``root``.
    """


class RunStore:
    """Append-only, on-disk store for execution runs.

    Each entry is a directory ``.ef-runs/<run_id>/`` containing ``run.json``,
    ``graph.json``, and ``payloads.json``. Entries are never modified after
    creation. Oldest entries are evicted after each ``save()`` to stay under
    the configured ``keep`` cap.
    """

    def __init__(self, root: Path, keep: int = DEFAULT_RUNS_KEEP) -> None:
        root.mkdir(parents=True, exist_ok=True)
        self._root = root
        self._lock = threading.Lock()
        self._keep = keep

    @property
    def root(self) -> Path:
        """The directory backing this store (test/inspection hook)."""
        return self._root

    @property
    def keep(self) -> int:
        """Maximum number of runs to retain (test/inspection hook)."""
        return self._keep

    def _run_dir(self, run_id: str) -> Path:
        if not _RUN_ID_RE.match(run_id):
            raise InvalidRunIdError(f"invalid run_id: {run_id!r}")
        return self._root / run_id

    def _read_run_json(self, run_dir: Path) -> dict[str, Any] | None:
        """Read and return ``run.json`` from *run_dir*, or ``None`` on failure."""
        path = run_dir / "run.json"
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def list(self) -> list[dict[str, Any]]:
        """Return entries sorted newest-first.

        Each entry contains ``run_id``, ``timestamp``, ``duration_ms``,
        ``node_count``, ``tag``, and ``graph_name``. A directory that fails to
        parse as a valid run (corrupt, mid-write, etc.) is skipped rather than
        raised -- listing must never crash on one bad entry.
        """
        entries: list[dict[str, Any]] = []
        with self._lock:
            run_dirs = sorted(self._root.iterdir())
        for run_dir in run_dirs:
            if not run_dir.is_dir():
                continue
            run_id = run_dir.name
            if not _RUN_ID_RE.match(run_id):
                continue
            data = self._read_run_json(run_dir)
            if data is None:
                continue
            entries.append(
                {
                    "run_id": run_id,
                    "timestamp": data.get("started_at"),
                    "duration_ms": data.get("duration_ms"),
                    "node_count": data.get("node_count"),
                    "tag": data.get("tag"),
                    "graph_name": data.get("graph_name"),
                }
            )
        entries.sort(key=lambda e: e.get("timestamp") or 0.0, reverse=True)
        return entries

    def get(self, run_id: str) -> dict[str, Any]:
        """Return the full ``run.json`` dict for *run_id*. Raise ``UnknownRunError`` if missing."""
        path = self._run_dir(run_id) / "run.json"
        with self._lock:
            if not path.is_file():
                raise UnknownRunError(run_id)
            return json.loads(path.read_text(encoding="utf-8"))

    def get_graph(self, run_id: str) -> dict[str, Any]:
        """Return the ``graph.json`` dict for *run_id*. Raise ``UnknownRunError`` if missing."""
        path = self._run_dir(run_id) / "graph.json"
        with self._lock:
            if not path.is_file():
                raise UnknownRunError(run_id)
            return json.loads(path.read_text(encoding="utf-8"))

    def get_payloads(self, run_id: str) -> dict[str, Any]:
        """Return the ``payloads.json`` dict for *run_id*. Raise ``UnknownRunError`` if missing.

        ``get`` returns only the metadata in ``run.json``; the node output payloads live in a
        separate ``payloads.json`` file, so the collaboration tools that read run results must
        use this method rather than ``...get(run_id).get("payloads", {})``.
        """
        path = self._run_dir(run_id) / "payloads.json"
        with self._lock:
            if not path.is_file():
                raise UnknownRunError(run_id)
            return json.loads(path.read_text(encoding="utf-8"))

    def save(
        self,
        run_data: dict[str, Any],
        graph_data: dict[str, Any],
        payloads_data: dict[str, Any],
    ) -> str:
        """Write a run entry atomically.

        Accepts a pre-built ``run.json`` dict, a ``graph.json`` dict, and a
        ``payloads.json`` dict. Generates a ``run_id`` automatically, stores
        all three files under ``.ef-runs/<run_id>/``, then evicts oldest
        entries until the store is under the ``keep`` cap.

        Returns the generated ``run_id``.
        """
        run_id = _generate_run_id()
        run_dir = self._run_dir(run_id)
        run_data["run_id"] = run_id

        with self._lock:
            run_dir.mkdir(parents=True, exist_ok=True)
            try:
                # Write run.json atomically
                self._write_json_atomic(run_dir, "run.json", run_data)
                # Write graph.json atomically
                self._write_json_atomic(run_dir, "graph.json", graph_data)
                # Write payloads.json atomically (with size cap)
                self._write_payloads(run_dir, payloads_data)
            except BaseException:
                shutil.rmtree(run_dir, ignore_errors=True)
                raise

            # Evict oldest entries until under keep
            self._evict()

        return run_id

    def delete(self, run_id: str) -> None:
        """Delete the run directory for *run_id*. Raise ``UnknownRunError`` if missing."""
        run_dir = self._run_dir(run_id)
        with self._lock:
            if not run_dir.is_dir():
                raise UnknownRunError(run_id)
            shutil.rmtree(run_dir)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _write_json_atomic(self, directory: Path, filename: str, data: dict[str, Any]) -> None:
        """Write *data* as JSON to *directory*/*filename* atomically."""
        fd, tmp_name = tempfile.mkstemp(dir=directory, prefix=f".{filename}-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(json.dumps(data, indent=2))
            os.replace(tmp_name, directory / filename)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise

    def _write_payloads(self, directory: Path, payloads: dict[str, Any]) -> None:
        """Write *payloads* to ``payloads.json``, capping each entry at 100KB."""
        capped: dict[str, Any] = {}
        for node_id, ports in payloads.items():
            capped_ports: dict[str, Any] = {}
            for port_name, value in ports.items():
                serialized = json.dumps(value)
                if len(serialized.encode("utf-8")) > _PAYLOAD_SIZE_CAP:
                    capped_ports[port_name] = {
                        "kind": "truncated",
                        "reason": "payload exceeded 100KB",
                    }
                else:
                    capped_ports[port_name] = value
            capped[node_id] = capped_ports

        fd, tmp_name = tempfile.mkstemp(dir=directory, prefix=".payloads-", suffix=".json.tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(json.dumps(capped, indent=2))
            os.replace(tmp_name, directory / "payloads.json")
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise

    def _evict(self) -> None:
        """Delete oldest run directories until the number of entries is <= ``keep``.

        Must be called with ``self._lock`` held.
        """
        dirs: list[tuple[float, Path]] = []
        for child in self._root.iterdir():
            if child.is_dir() and _RUN_ID_RE.match(child.name):
                try:
                    mtime = child.stat().st_mtime
                except OSError:
                    continue
                dirs.append((mtime, child))

        # Sort by mtime (oldest first)
        dirs.sort(key=lambda pair: pair[0])

        while len(dirs) > self._keep:
            _, oldest_dir = dirs.pop(0)
            shutil.rmtree(oldest_dir, ignore_errors=True)


# ------------------------------------------------------------------
# Process-wide singleton, mirroring the pattern in flows.py / cache.py
# / artifacts.py so the store survives across HTTP requests.
# ``configure_runs`` must run BEFORE the first ``get_default_runs()``
# call (i.e. before the server starts accepting requests); calling it
# after the singleton exists is a programming error.
# ------------------------------------------------------------------
_default_runs: RunStore | None = None
_default_runs_lock = threading.Lock()
_configured_runs_root: Path | None = None
_configured_runs_keep: int = DEFAULT_RUNS_KEEP


def configure_runs(root: Path, keep: int = DEFAULT_RUNS_KEEP) -> None:
    """Set the root directory and keep count for the default RunStore singleton.

    Must be called before the first ``get_default_runs()`` call.
    """
    global _configured_runs_root, _configured_runs_keep
    if _default_runs is not None:
        raise RuntimeError("configure_runs() called after the default RunStore was already created")
    _configured_runs_root = root
    _configured_runs_keep = keep


def get_default_runs() -> RunStore:
    """Return the lazily-created process-wide default RunStore."""
    global _default_runs
    if _default_runs is None:
        with _default_runs_lock:
            if _default_runs is None:
                root = (
                    _configured_runs_root
                    if _configured_runs_root is not None
                    else Path.cwd() / DEFAULT_RUNS_DIRNAME
                )
                _default_runs = RunStore(root=root, keep=_configured_runs_keep)
    return _default_runs
