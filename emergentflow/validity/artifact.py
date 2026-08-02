"""
emergentflow.validity.artifact
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Portable validity rule-pack artifact emitter (Epic 17, Story 2).

Serializes the registered validity rule metadata (id, severity, confidence,
title, rationale) as a single versioned JSON artifact (ADR 0012) the canvas
renders rule explanations from with no Python round-trip. ``pack_version`` is
the registry's pack version; bump it when rule metadata changes in a way the
canvas must see.

Distinct from ``emergentflow.types.rules_artifact`` (the TYPE-SYSTEM rules
artifact at ``schema/rules.json``). This one is the EXPERIMENT-VALIDITY rule
pack, written to ``schema/validity-rules.json``.
"""

from __future__ import annotations

import json
from typing import Any

from emergentflow.api import public_op

from .registry import PACK_VERSION, ValidityRuleRegistry
from .registry import registry as default_registry


@public_op(name="ef.build_validity_rules_artifact")
def build_validity_rules_artifact(
    rule_registry: ValidityRuleRegistry = default_registry,
    *,
    pack_version: int = PACK_VERSION,
) -> dict[str, Any]:
    """Build a versioned validity rule-pack artifact from the rule registry.

    The artifact contains the pack version and every registered rule's metadata,
    so the canvas can explain a finding's rule without a server call. Pure
    function of *rule_registry* and *pack_version*: no I/O, no global mutation.
    """
    return {
        "pack_version": pack_version,
        "rules": rule_registry.specs(),
    }


def write_validity_rules_artifact(
    path: str,
    rule_registry: ValidityRuleRegistry = default_registry,
) -> None:
    """Write the validity rule-pack artifact to ``path`` as pretty-printed JSON."""
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(build_validity_rules_artifact(rule_registry), fh, indent=2, sort_keys=True)
        fh.write("\n")


if __name__ == "__main__":
    import sys

    out = sys.argv[1] if len(sys.argv) > 1 else "validity-rules.json"
    write_validity_rules_artifact(out)
    print(f"wrote validity rule pack to {out}")
