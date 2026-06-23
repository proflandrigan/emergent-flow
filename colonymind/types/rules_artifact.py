"""
colonymind.types.rules_artifact
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Portable rules artifact emitter (Epic 3, Story 7).

Serializes the type catalog + subtype relation + compatibility semantics as a
single versioned JSON artifact (ADR 0012) the frontend evaluates for instant
edge feedback with no Python present. The artifact ``version`` is the IR schema
version (:data:`~colonymind.ir.graph.CURRENT_SCHEMA_VERSION`) so the canvas can
detect drift between the rules it shipped with and the rules this SDK enforces.

:func:`build_rules_artifact` is the pure builder over a ``TypeRegistry``;
:func:`write_rules_artifact` is the thin I/O wrapper, mirroring
:mod:`colonymind.ir.schema`.
"""

from __future__ import annotations

import json
from typing import Any

from colonymind.ir.graph import CURRENT_SCHEMA_VERSION
from colonymind.types.registry import TypeRegistry
from colonymind.types.registry import registry as default_registry

#: Compatibility semantics block (ADR 0011 algorithm, ADR 0012 shape). The
#: frontend reimplements the tiny exact/subtype/wildcard check against this.
COMPATIBILITY_SEMANTICS: dict[str, Any] = {
    "wildcard": "any",
    "exact": True,
    "subtype": True,
    "unknown": "warn",
}


def build_rules_artifact(
    registry: TypeRegistry = default_registry,
    *,
    version: int = CURRENT_SCHEMA_VERSION,
) -> dict[str, Any]:
    """Build a versioned rules artifact from the type registry.

    The artifact contains the type catalog, subtype relationships, and
    compatibility semantics needed for frontend validation (ADR 0012). It is a
    pure function of *registry* and *version*: no I/O, no global mutation.
    """
    catalog = registry.to_dict()
    return {
        "version": version,
        "types": catalog["types"],
        "top": catalog["top"],
        "subtypes": catalog["subtypes"],
        "semantics": dict(COMPATIBILITY_SEMANTICS),
    }


def write_rules_artifact(path: str, registry: TypeRegistry = default_registry) -> None:
    """Write the rules artifact to ``path`` as pretty-printed JSON."""
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(build_rules_artifact(registry), fh, indent=2, sort_keys=True)
        fh.write("\n")


if __name__ == "__main__":
    import sys

    out = sys.argv[1] if len(sys.argv) > 1 else "rules.json"
    write_rules_artifact(out)
    print(f"wrote rules artifact to {out}")
