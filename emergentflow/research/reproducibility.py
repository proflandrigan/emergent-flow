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
from dataclasses import dataclass, field
from typing import Any

from emergentflow.api import public_op
from emergentflow.ir.graph import Graph

__all__ = [
    "SEED_PARAM_NAMES",
    "ReproducibilityCapture",
    "capture_run",
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
        ``"data."``).
    dependency_versions: package name -> resolved version string, exactly as supplied by the
        caller (see ``resolve_dependency_versions``).
    """

    seeds: dict[str, int] = field(default_factory=dict)
    content_hashes: dict[str, str] = field(default_factory=dict)
    dependency_versions: dict[str, str] = field(default_factory=dict)


@public_op(name="ef.research.capture_run")
def capture_run(
    graph: Graph, *, dependency_versions: dict[str, str] | None = None
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

    Returns
    -------
    ReproducibilityCapture
        ``seeds`` collected from every node param named ``"seed"`` or ``"random_state"`` with a
        non-``None`` value; ``content_hashes`` collected from every node whose ``type`` starts
        with ``"data."``; ``dependency_versions`` as supplied (empty dict if not given). Node
        iteration is in sorted node-id order for determinism.
    """
    seeds: dict[str, int] = {}
    content_hashes: dict[str, str] = {}

    for node_id in sorted(graph.nodes):
        node = graph.nodes[node_id]
        for param in node.params:
            if param.name in SEED_PARAM_NAMES and isinstance(param.value, int):
                seeds[node_id] = param.value

        if node.type.startswith("data."):
            params_snapshot = {p.name: p.value for p in node.params}
            content_hashes[node_id] = _content_hash({"type": node.type, "params": params_snapshot})

    return ReproducibilityCapture(
        seeds=seeds,
        content_hashes=content_hashes,
        dependency_versions=dict(dependency_versions or {}),
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
