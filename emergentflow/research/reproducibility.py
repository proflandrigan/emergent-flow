"""
emergentflow.research.reproducibility
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reproducibility capture (Epic 16, Story 18).

``capture_run`` records a snapshot of what would need to be reproduced to re-run a graph
identically: per-node seeds, per-source-node content hashes, and resolved dependency versions.
It is pure over its inputs -- it walks the already-loaded ``Graph`` IR (no filesystem/network
access) and records whatever ``dependency_versions`` the caller supplies verbatim. Resolving
the *actual* installed package versions is an environment read and is quarantined to the edge
helper ``resolve_dependency_versions`` below: call that first, then pass its result into
``capture_run``.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Collection, Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from emergentflow.api import public_op
from emergentflow.ir.graph import Graph

__all__ = [
    "SEED_PARAM_NAMES",
    "ReproducibilityCapture",
    "SourceFingerprint",
    "capture_run",
    "default_dependency_packages",
    "fingerprint_data_sources",
    "fingerprint_source",
    "resolve_dependency_versions",
]

# Every stochastic op added in this epic captures its seed under one of these two param names
# (Story 9's sample_rows uses "seed"; Story 13's reduce_dimensions and the ml family's
# train_test_split use "random_state") -- no single uniform key exists across the epic's
# stochastic ops, so both are checked.
SEED_PARAM_NAMES = ("seed", "random_state")


def _content_hash(value: Any) -> str:
    """Stable sha256 hex digest of a JSON-native, sorted-keys serialization.

    The same scheme ``LLMRequest.content_hash()``/``HttpRequest.content_hash()`` use to key
    replay fixtures (``emergentflow.llm.protocol``, ``emergentflow.data.http.protocol``),
    reused here for provenance hashing of each source node's resolved parameters.
    """
    encoded = json.dumps(value, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass
class ReproducibilityCapture:
    """A reproducibility snapshot of one graph run.

    Attributes
    ----------
    seeds: node id -> the seed/random_state value captured from that node's params.
    content_hashes: node id -> a stable content hash of that source node's (type, params),
        for every node whose type looks like a data loader (``node.type`` starting with
        ``"data."``). This is a CONFIG hash, not a data fingerprint: the same path with
        different bytes hashes identically. See ``data_fingerprints`` for the bytes.
    dependency_versions: package name -> resolved version string, exactly as supplied by the
        caller (see ``resolve_dependency_versions``).
    params: resolved graph-level parameter values this run used; defaults to the graph's
        stored param values when not supplied.
    data_fingerprints: node id -> ``SourceFingerprint`` (as a dict) of the source that node read,
        as supplied by the caller (see ``fingerprint_data_sources``); empty if not supplied.
    """

    seeds: dict[str, int | float] = field(default_factory=dict)
    content_hashes: dict[str, str] = field(default_factory=dict)
    dependency_versions: dict[str, str] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)
    data_fingerprints: dict[str, dict[str, Any]] = field(default_factory=dict)


@public_op(name="ef.research.capture_run")
def capture_run(
    graph: Graph,
    *,
    dependency_versions: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    data_fingerprints: Mapping[str, SourceFingerprint | dict[str, Any]] | None = None,
) -> ReproducibilityCapture:
    """Capture a reproducibility snapshot of *graph*.

    Parameters
    ----------
    graph:
        The IR graph to snapshot.
    dependency_versions:
        Optional caller-supplied map of package name -> resolved version string (see
        :func:`resolve_dependency_versions`). Recorded verbatim; ``capture_run`` itself never
        reads the environment, keeping it pure and reproducible from its inputs alone.
    params:
        Optional resolved graph-level parameter values this run used (issue #116). When
        ``None``, records each graph-level param's stored value. Callers that ran with runtime
        overrides (``ef.execute(..., params=...)``, the CLI ``--param`` flag) should pass the
        RESOLVED values so the snapshot says what the run was actually given.
    data_fingerprints:
        Optional caller-supplied map of node id -> :class:`SourceFingerprint` (see
        :func:`fingerprint_data_sources`). Recorded verbatim as dicts; ``capture_run`` never
        reads the sources itself.

    Returns
    -------
    ReproducibilityCapture
        ``seeds`` collected from every node param named ``"seed"`` or ``"random_state"`` with a
        non-``None`` value; ``content_hashes`` collected from every node whose ``type`` starts
        with ``"data."``; ``dependency_versions`` as supplied (empty dict if not given);
        ``params`` as supplied (the graph's stored values if not given). Node iteration is in
        sorted node-id order for determinism.
    """
    seeds: dict[str, int | float] = {}
    content_hashes: dict[str, str] = {}

    for node_id in sorted(graph.nodes):
        node = graph.nodes[node_id]
        for param in node.params:
            if (
                param.name in SEED_PARAM_NAMES
                and isinstance(param.value, (int, float))
                and not isinstance(param.value, bool)
            ):
                seeds[node_id] = param.value

        if node.type.startswith("data."):
            params_snapshot = {p.name: p.value for p in node.params}
            content_hashes[node_id] = _content_hash({"type": node.type, "params": params_snapshot})

    if params is None:
        params = {name: param.value for name, param in graph.params.items()}

    return ReproducibilityCapture(
        seeds=seeds,
        content_hashes=content_hashes,
        dependency_versions=dict(dependency_versions or {}),
        params=dict(params),
        data_fingerprints={
            nid: asdict(fp) if isinstance(fp, SourceFingerprint) else dict(fp)
            for nid, fp in (data_fingerprints or {}).items()
        },
    )


def resolve_dependency_versions(packages: list[str]) -> dict[str, str]:
    """Impure edge helper: read installed package versions from the environment.

    Not decorated with ``@public_op`` and not called by ``capture_run`` itself -- call this
    first, then pass its result into ``capture_run(graph, dependency_versions=...)``. Packages
    not found installed are silently omitted (not an error) rather than raising, so a caller can
    pass a broad wishlist of package names without needing to know in advance which are
    actually installed in this environment.
    """
    import importlib.metadata

    versions: dict[str, str] = {}
    for package in packages:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            continue
    return versions


_HASH_CHUNK_BYTES = 1 << 20


@dataclass
class SourceFingerprint:
    """What a data source looked like when it was read, and when that was recorded.

    Attributes
    ----------
    uri: the path or object-store URI that was fingerprinted.
    kind: ``"file"`` (local bytes hashed), ``"object"`` (remote object; identified by
        ``etag``/``size``/``last_modified``, plus ``sha256`` when requested), or
        ``"unverifiable"`` (nothing identifying could be read; see ``reason``).
    sha256: hex digest of the source bytes, or ``None`` when not computed.
    size: size in bytes, or ``None`` when unknown.
    etag: the object store's version tag (S3 ETag etc.), or ``None``.
    last_modified: ISO-8601 UTC timestamp reported by the store, or ``None``.
    fingerprinted_at: ISO-8601 UTC timestamp of this fingerprint -- the "run date" to quote
        next to numbers derived from this source.
    reason: why the source is ``"unverifiable"``; ``None`` otherwise.
    """

    uri: str
    kind: str
    sha256: str | None = None
    size: int | None = None
    etag: str | None = None
    last_modified: str | None = None
    fingerprinted_at: str = ""
    reason: str | None = None

    def describe(self) -> str:
        """One-line citation, e.g. for a notebook summary: ``uri (id, size, date)``."""
        if self.kind == "unverifiable":
            ident = f"unverifiable: {self.reason}"
        else:
            parts = []
            if self.sha256:
                parts.append(f"sha256 {self.sha256[:12]}")
            if self.etag:
                parts.append(f"etag {self.etag}")
            if self.size is not None:
                parts.append(f"{self.size} bytes")
            ident = ", ".join(parts)
        return f"{self.uri} ({ident}; as of {self.fingerprinted_at})"


def _utc_iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        stamp = value if value.tzinfo else value.replace(tzinfo=UTC)
        return stamp.astimezone(UTC).isoformat(timespec="seconds")
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=UTC).isoformat(timespec="seconds")
    return str(value)


def _sha256_stream(handle: Any) -> str:
    digest = hashlib.sha256()
    for chunk in iter(lambda: handle.read(_HASH_CHUNK_BYTES), b""):
        digest.update(chunk)
    return digest.hexdigest()


class _RemoteTimeout(Exception):
    """A remote metadata read exceeded its timeout."""


def _call_with_timeout(fn: Any, timeout: float | None) -> Any:
    """Run *fn* and return its result, giving up after *timeout* seconds (``None``: no limit).

    The call runs on a daemon thread so a hung network read can never block the caller (or
    interpreter exit) past *timeout*; an abandoned read simply finishes or dies in the
    background.
    """
    if timeout is None:
        return fn()
    import threading

    box: dict[str, Any] = {}

    def _target() -> None:
        try:
            box["value"] = fn()
        except BaseException as exc:  # noqa: BLE001 - re-raised on the calling thread
            box["error"] = exc

    worker = threading.Thread(target=_target, name="ef-fingerprint", daemon=True)
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        raise _RemoteTimeout
    if "error" in box:
        raise box["error"]
    return box["value"]


@public_op(name="ef.research.fingerprint_source")
def fingerprint_source(
    uri: str,
    *,
    connection: str | None = None,
    hash_remote: bool = False,
    timeout: float | None = None,
) -> SourceFingerprint:
    """Fingerprint one data source's actual bytes (or its object-store version tag).

    ``capture_run`` hashes a source node's configuration, so the same path can silently point
    at different data. This reads the source itself: a local file is hashed in full (streamed);
    a remote object (``s3://``, ``gs://``, ``abfs://``...) is identified from its store metadata
    (ETag, size, last-modified) without downloading, and hashed in full only when
    ``hash_remote=True``. The result carries ``fingerprinted_at`` so an analysis can cite the
    date its numbers were computed from this source.

    Impure edge helper (filesystem/network access, ``os.environ`` via the connection profile).
    A source that cannot be read returns ``kind="unverifiable"`` with a ``reason`` rather than
    raising, so a notebook can record the gap honestly.

    Parameters
    ----------
    uri:
        A local path or an object-store URI. Globs are not expanded; fingerprint each file.
    connection:
        Connection-profile *name* for remote credentials (never a credential itself), as for
        the ``ef.data.load_*`` loaders. ``None`` uses the ambient credential chain.
    hash_remote:
        Also stream and hash the remote object's bytes.
    timeout:
        Seconds to wait for the remote metadata (and optional hash) read before recording the
        source as ``unverifiable``; ``None`` waits indefinitely. Local files ignore it. A timed
        out read is abandoned on a daemon worker thread, never joined.
    """
    from emergentflow.data import _is_remote_uri, _require_extra, _resolve_storage_options

    now = _utc_iso(datetime.now(UTC)) or ""

    if not _is_remote_uri(uri):
        path = Path(uri)
        try:
            stat = path.stat()
            with path.open("rb") as handle:
                digest = _sha256_stream(handle)
        except OSError as exc:
            return SourceFingerprint(
                uri=uri, kind="unverifiable", fingerprinted_at=now, reason=str(exc)
            )
        return SourceFingerprint(
            uri=uri,
            kind="file",
            sha256=digest,
            size=stat.st_size,
            last_modified=_utc_iso(stat.st_mtime),
            fingerprinted_at=now,
        )

    _require_extra("emergentflow[cloud]")
    import fsspec

    def _read_remote() -> tuple[dict[str, Any], str | None]:
        fs, fs_path = fsspec.core.url_to_fs(uri, **_resolve_storage_options(connection))
        remote_info = fs.info(fs_path)
        digest: str | None = None
        if hash_remote:
            with fs.open(fs_path, "rb") as handle:
                digest = _sha256_stream(handle)
        return remote_info, digest

    try:
        info, remote_digest = _call_with_timeout(_read_remote, timeout)
    except ImportError:
        raise
    except _RemoteTimeout:
        return SourceFingerprint(
            uri=uri,
            kind="unverifiable",
            fingerprinted_at=now,
            reason=f"timed out after {timeout}s reading remote metadata",
        )
    except Exception as exc:  # network/credential/not-found: record, don't raise
        return SourceFingerprint(
            uri=uri,
            kind="unverifiable",
            fingerprinted_at=now,
            reason=f"{type(exc).__name__}: {exc}",
        )

    etag = info.get("ETag") or info.get("etag")
    size = info.get("size")
    return SourceFingerprint(
        uri=uri,
        kind="object",
        sha256=remote_digest,
        size=int(size) if size is not None else None,
        etag=str(etag).strip('"') if etag else None,
        last_modified=_utc_iso(info.get("LastModified") or info.get("mtime")),
        fingerprinted_at=now,
    )


# Source-reading ``data.*`` nodes whose ``path`` param names a local file or object-store URI.
_PATH_SOURCE_TYPES = frozenset(
    {
        "data.load_csv",
        "data.load_parquet",
        "data.load_json",
        "data.load_excel",
        "data.load_documents",
    }
)
# ``data.*`` nodes that read from somewhere with no byte-addressable file: recorded as
# unverifiable rather than silently omitted.
_REMOTE_SOURCE_REASONS = {
    "data.http_fetch": "http source: response bytes are not fingerprinted",
    "data.sql_query": "warehouse source: no byte-level fingerprint",
    "data.query_builder": "warehouse source: no byte-level fingerprint",
    "data.describe_relation": "warehouse source: no byte-level fingerprint",
    "data.load_google_sheet": "google sheet source: no byte-level fingerprint",
}
_GLOB_CHARS = set("*?[")
# Default bound on each remote metadata read made while recording a run, so a slow or
# unreachable object store cannot delay the run record (and the stream's run_complete).
DEFAULT_REMOTE_TIMEOUT_S = 5.0


def _looks_like_glob(uri: str) -> bool:
    """Same rule the local loaders use (``emergentflow.data``): a path is a glob only if it has
    glob characters AND does not exist as a literal file, so ``sales[2024].csv`` is a file."""
    return bool(_GLOB_CHARS & set(uri)) and not Path(uri).exists()


def _now_iso() -> str:
    return _utc_iso(datetime.now(UTC)) or ""


def _fingerprint_node(
    node: Any, unresolved_ref: bool, timeout: float | None
) -> SourceFingerprint | None:
    values = {p.name: p.value for p in node.params}
    path_value = values.get("url") or values.get("path")
    try:
        if node.type in _REMOTE_SOURCE_REASONS:
            return SourceFingerprint(
                uri=str(path_value or node.type),
                kind="unverifiable",
                fingerprinted_at=_now_iso(),
                reason=_REMOTE_SOURCE_REASONS[node.type],
            )
        if node.type not in _PATH_SOURCE_TYPES:
            return None
        path_param = next((p for p in node.params if p.name == "path"), None)
        if unresolved_ref and path_param is not None and path_param.ref is not None:
            return SourceFingerprint(
                uri=str(path_param.value) if path_param.value is not None else "",
                kind="unverifiable",
                fingerprinted_at=_now_iso(),
                reason=f"path references unresolved graph parameter {path_param.ref!r}",
            )
        uri = values.get("path")
        if not isinstance(uri, str) or not uri:
            return None
        # Remote URIs with glob chars are always expanded by the loaders; local paths only
        # when no literal file of that name exists (``data._is_glob`` + ``exists`` rule).
        remote = _is_remote(uri)
        is_glob = bool(_GLOB_CHARS & set(uri)) if remote else _looks_like_glob(uri)
        if is_glob or (not remote and Path(uri).is_dir()):
            return SourceFingerprint(
                uri=uri,
                kind="unverifiable",
                fingerprinted_at=_now_iso(),
                reason="glob or directory source: fingerprint each file",
            )
        connection = values.get("connection")
        return fingerprint_source(
            uri,
            connection=connection if isinstance(connection, str) else None,
            timeout=timeout,
        )
    except Exception as exc:  # never let fingerprinting break a run
        return SourceFingerprint(
            uri=str(path_value) if path_value is not None else str(node.type),
            kind="unverifiable",
            fingerprinted_at=_now_iso(),
            reason=f"{type(exc).__name__}: {exc}",
        )


def _is_remote(uri: str) -> bool:
    from emergentflow.data import _is_remote_uri

    return bool(_is_remote_uri(uri))


def fingerprint_data_sources(
    graph: Graph,
    *,
    params: dict[str, Any] | None = None,
    node_ids: Collection[str] | None = None,
    remote_timeout: float | None = DEFAULT_REMOTE_TIMEOUT_S,
) -> dict[str, SourceFingerprint]:
    """Impure edge helper: fingerprint the source each ``data.*`` loader node reads.

    Local files are hashed (streamed); remote object URIs are identified by store metadata only
    (``hash_remote`` is never set, so no remote bytes are downloaded), each read bounded by
    *remote_timeout* seconds; globs, directories and warehouse/http/sheet sources are recorded
    as ``kind="unverifiable"`` with a ``reason``. Sinks (``save_frame``, ``write_table``) and
    built-in samples are skipped. Never raises: a failure on one node yields an
    ``unverifiable`` entry (or omits it) and the run proceeds.

    Ref'd node params are resolved against the graph-level params (with *params* overrides
    applied, exactly as ``materialize_graph`` does for execution), so the fingerprinted path is
    the one the run read. Pass the same *params* the run was executed with; re-resolving an
    already-materialized graph with the same *params* is idempotent. A ref that cannot be
    resolved is recorded as ``unverifiable`` rather than fingerprinting a stale literal.

    Composite (``layout.composite``) subgraphs are walked recursively; an inner node is keyed
    ``"<outer id>/<inner id>"``. *node_ids*, when given, restricts fingerprinting to those
    top-level node ids (and everything nested in them) -- e.g. only the nodes that actually
    ran ok, so a loader that errored is not recorded as a source the run read.
    """
    from emergentflow.codegen.params import has_graph_param_refs, materialize_graph

    unresolved_ref = False
    if params or has_graph_param_refs(graph):
        try:
            graph = materialize_graph(graph, params=params)
        except Exception:
            unresolved_ref = True

    allowed = set(node_ids) if node_ids is not None else None
    out: dict[str, SourceFingerprint] = {}

    def _walk(g: Graph, prefix: str) -> None:
        for node_id in sorted(g.nodes):
            node = g.nodes[node_id]
            key = f"{prefix}{node_id}"
            if not prefix and allowed is not None and node_id not in allowed:
                continue
            if node.subgraph is not None:
                _walk(node.subgraph, f"{key}/")
            fp = _fingerprint_node(node, unresolved_ref, remote_timeout)
            if fp is not None:
                out[key] = fp

    _walk(graph, "")
    return out


def default_dependency_packages() -> list[str]:
    """Package names to record: ``emergentflow`` plus its declared direct requirements.

    Cheaper and more relevant than every installed distribution (hundreds in a dev env); the
    requirement names come from ``emergentflow``'s own metadata, extras included, and
    :func:`resolve_dependency_versions` drops the ones not installed.
    """
    import importlib.metadata

    names = ["emergentflow"]
    try:
        requires = importlib.metadata.requires("emergentflow") or []
    except importlib.metadata.PackageNotFoundError:
        requires = []
    for req in requires:
        match = re.match(r"[A-Za-z0-9][A-Za-z0-9._-]*", req)
        if match and match.group(0) not in names:
            names.append(match.group(0))
    return names
