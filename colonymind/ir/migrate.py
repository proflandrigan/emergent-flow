"""
colonymind.ir.migrate
~~~~~~~~~~~~~~~~~~~~~~
Generic schema-migration framework for the Colony Mind graph IR.

Migrations operate on a **parsed JSON dict** of a serialized :class:`~colonymind.ir.graph.Graph`
*before* Pydantic validation — i.e. the output of ``json.loads(...)``, a plain
``dict[str, Any]``. Each registered migration step is a pure ``dict -> dict`` transform: it
performs the structural change for exactly one schema-version bump and returns the new dict.
It does **not** stamp ``schema_version`` itself — the framework (:func:`migrate_to_current`)
stamps the new version after each step runs, so step authors only worry about the structural
diff, never the bookkeeping.

This module is deliberately low-level and has no knowledge of :class:`Graph` / :class:`Node`
models: it imports nothing from ``colonymind.ir.serialize`` (which will, in a later story, call
into this module to migrate older graphs before validation) and constructs no Pydantic models.
Keeping the dependency direction one-way (``serialize`` → ``migrate``, never the reverse) avoids
a circular import.

This is the Story 9 foundation: the mechanism for chaining ordered migration steps from an
older ``schema_version`` up to :data:`~colonymind.ir.graph.CURRENT_SCHEMA_VERSION`. No concrete
migration step is registered here — see the dedicated migration modules for those — and this
module is not yet wired into ``serialize.py``'s load path.

ADR refs:
  - ADR 0002: execute the IR (data), not a generated string — the graph is the artifact.
  - docs/ir-serialization-format.md: JSON-first, ``.cm.json`` at-rest extension.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from .graph import CURRENT_SCHEMA_VERSION, INITIAL_SCHEMA_VERSION

__all__ = [
    "MigrationStep",
    "MigrationError",
    "register_migration",
    "migrate_to_current",
    "migrate_document",
]

# A migration step transforms a parsed graph dict at version N into the shape expected at
# version N + 1. Steps are pure: given a dict, return a (possibly new) dict. They must NOT
# set "schema_version" themselves — migrate_to_current stamps it after the step returns.
MigrationStep = Callable[[dict[str, Any]], dict[str, Any]]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class MigrationError(Exception):
    """Raised when a graph cannot be migrated up to the target schema version
    (e.g. no registered step exists for some intermediate version, or the source
    version is already at/above the target)."""


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

# Module-level registry: from_version -> step that migrates from_version -> from_version + 1.
_MIGRATIONS: dict[int, MigrationStep] = {}


def register_migration(from_version: int, step: MigrationStep) -> None:
    """Register `step` as the migration from `from_version` to `from_version + 1`.

    Parameters
    ----------
    from_version:
        The schema version `step` migrates *from*. Must be non-negative and strictly
        less than :data:`~colonymind.ir.graph.CURRENT_SCHEMA_VERSION` — there is no such
        thing as a migration step starting at or above the current version.
    step:
        A pure ``dict -> dict`` transform implementing the structural change for this
        one version bump. Must NOT set ``schema_version`` itself.

    Raises
    ------
    MigrationError
        If `from_version` is negative, if `from_version` is at/above
        ``CURRENT_SCHEMA_VERSION``, or if a step is already registered for
        `from_version` (no silent overwrite).
    """
    if from_version < 0:
        raise MigrationError(
            f"cannot register a migration from a negative schema version: {from_version}."
        )
    if from_version >= CURRENT_SCHEMA_VERSION:
        raise MigrationError(
            f"cannot register a migration from schema v{from_version}: it is already at/above "
            f"the current schema version (v{CURRENT_SCHEMA_VERSION})."
        )
    if from_version in _MIGRATIONS:
        raise MigrationError(
            f"a migration from schema v{from_version} is already registered; "
            "refusing to silently overwrite it."
        )
    _MIGRATIONS[from_version] = step


# ---------------------------------------------------------------------------
# Chaining
# ---------------------------------------------------------------------------


def migrate_to_current(
    doc: dict[str, Any],
    *,
    found: int,
    target: int = CURRENT_SCHEMA_VERSION,
    migrations: Mapping[int, MigrationStep] | None = None,
) -> dict[str, Any]:
    """Migrate a parsed graph dict from schema version `found` up to `target`.

    Chains registered migration steps in order, stamping ``doc["schema_version"]`` with
    the new version after each step runs. Always returns a NEW top-level dict — a shallow
    copy of `doc` is taken before anything else (including on the no-op path) — so the
    caller's object is never re-keyed in place. Steps are required to be pure: the
    framework does not deep-copy, so a step that mutates a nested structure of the dict it
    receives can still affect the caller.

    Parameters
    ----------
    doc:
        The parsed (pre-validation) graph dict, i.e. the output of ``json.loads(...)``.
        Not re-keyed in place — a shallow copy is returned.
    found:
        The schema version `doc` is currently at.
    target:
        The schema version to migrate up to. Defaults to
        :data:`~colonymind.ir.graph.CURRENT_SCHEMA_VERSION`.
    migrations:
        The registry to chain through. Defaults to the module-level registry
        populated via :func:`register_migration`. Tests should pass an explicit
        mapping here to avoid depending on global state.

    Returns
    -------
    dict[str, Any]
        The migrated dict, with ``schema_version == target``.

    Raises
    ------
    MigrationError
        If `found > target` (downgrades are not supported), or if no migration step
        is registered for some intermediate version along the chain.
    """
    reg = _MIGRATIONS if migrations is None else migrations

    # Shallow-copy up front so every return path (including the no-op) hands back a new
    # top-level dict and never re-keys the caller's object.
    doc = dict(doc)

    if found == target:
        return doc

    if found > target:
        raise MigrationError(
            f"cannot migrate v{found} -> v{target}: downgrading schema versions is not supported."
        )

    for v in range(found, target):
        step = reg.get(v)
        if step is None:
            raise MigrationError(
                f"no migration registered from schema v{v} to v{v + 1}; cannot migrate "
                f"v{found} -> v{target}."
            )
        doc = step(doc)
        doc["schema_version"] = v + 1

    return doc


# ---------------------------------------------------------------------------
# Registered migrations
# ---------------------------------------------------------------------------


def _migrate_v0_to_v1(doc: dict[str, Any]) -> dict[str, Any]:
    """SYNTHETIC / ILLUSTRATIVE example migration (schema v0 -> v1).

    There was never a real released schema v0; this step exists only to exercise and
    document the migration mechanism end-to-end (Story 9, Epic 1). It models a plausible
    early rename: a hypothetical v0 stored the graph paradigm under a top-level ``"mode"``
    key, which v1 renamed to ``"paradigm"``. The step renames ``mode`` -> ``paradigm`` and
    leaves everything else untouched. It does NOT stamp ``schema_version`` (the framework
    does that). Replace or remove this when the first REAL schema bump lands.
    """
    doc = dict(doc)
    if "mode" in doc:
        doc["paradigm"] = doc.pop("mode")
    return doc


register_migration(0, _migrate_v0_to_v1)


# ---------------------------------------------------------------------------
# Document-level migration
# ---------------------------------------------------------------------------


def migrate_document(parsed: dict[str, Any]) -> dict[str, Any]:
    """Migrate a parsed graph document — and every nested subgraph — to CURRENT_SCHEMA_VERSION.

    Each (sub)graph carries its own ``schema_version``; this walks the node tree and migrates
    each level by its own version, so a composite node's inner graph written at an older
    schema version is migrated too. Returns a new top-level dict and does NOT mutate the input.
    """
    return _migrate_graph_level(parsed)


def _migrate_graph_level(g: dict[str, Any]) -> dict[str, Any]:
    # Absent version => pre-versioning graph; treat as the earliest schema (shared with the
    # loader's _coerce_version so the two cannot drift when CURRENT bumps).
    found = g.get("schema_version", INITIAL_SCHEMA_VERSION)
    # migrate_to_current always returns a fresh top-level dict, so reassigning g["nodes"]
    # below never touches the caller's object.
    g = migrate_to_current(g, found=found)
    nodes = g.get("nodes")
    if isinstance(nodes, dict):
        g["nodes"] = {nid: _migrate_node(node) for nid, node in nodes.items()}
    return g


def _migrate_node(node: Any) -> Any:
    if not isinstance(node, dict):
        return node
    sub = node.get("subgraph")
    if isinstance(sub, dict):
        node = dict(node)
        node["subgraph"] = _migrate_graph_level(sub)
    return node
