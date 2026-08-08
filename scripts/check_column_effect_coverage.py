#!/usr/bin/env python3
"""Report column_effect coverage across the node catalog (Epic 18, Story 8).

Column lineage (Epic 18) resolves a node's column mapping from its declared
``column_effect`` (``emergentflow.nodes.spec.ColumnEffect``); an undeclared node
reports an explicit "unknown" boundary. This script lists every registered node
lacking a declaration, grouped by family, and prints the overall coverage. It
exit non-zero when tracer-resolvable coverage falls below ``--min-pct``
(default 40), so CI can track it rather than assert a hard number: adding a
node can't silently regress lineage quality.

The gate is on the fraction of nodes the lineage tracer actually *resolves*
(``SOURCE``/``PASSTHROUGH`` kinds plus the two hardcoded special cases), not on
the broader set of advisory ``column_effect`` declarations, so the report
honestly reflects real traceability.

Run::

    uv run python scripts/check_column_effect_coverage.py [--min-pct 40]
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from emergentflow.nodes.registry import registry
from emergentflow.nodes.spec import ColumnEffectKind

# Node types the lineage tracer additionally resolves by hardcoded special-case.
_RESOLVED_TYPES = {"clean.select_columns", "clean.derive_column"}


@dataclass
class Coverage:
    """Result of the column-effect coverage scan.

    ``declared`` is the number of nodes with a non-None ``column_effect``;
    ``resolvable`` is the subset of those the lineage tracer actually resolves
    (a proper subset of ``declared``); ``total`` is the full catalog size;
    ``undeclared`` groups non-declaring node types by family.
    """

    declared: int
    resolvable: int
    total: int
    undeclared: dict[str, list[str]] = field(default_factory=dict)


def _is_resolvable(type_key: str, definition) -> bool:
    """Return whether the lineage tracer actually resolves this node's columns."""
    effect = definition.column_effect
    if effect is not None and effect.kind in (
        ColumnEffectKind.SOURCE,
        ColumnEffectKind.PASSTHROUGH,
    ):
        return True
    return type_key in _RESOLVED_TYPES


def coverage() -> Coverage:
    """Return Coverage with declared/resolvable counts and undeclared grouping."""
    undeclared: dict[str, list[str]] = defaultdict(list)
    declared = 0
    resolvable = 0
    for type_key, definition in sorted(registry._defs.items(), key=lambda kv: kv[0]):
        if definition.column_effect is None:
            undeclared[definition.family].append(type_key)
        else:
            declared += 1
            if _is_resolvable(type_key, definition):
                resolvable += 1
    return Coverage(
        declared=declared,
        resolvable=resolvable,
        total=len(registry._defs),
        undeclared=dict(undeclared),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--min-pct",
        type=float,
        default=40.0,
        help=(
            "Exit non-zero when tracer-resolvable coverage drops below this percent (default 40)."
        ),
    )
    args = parser.parse_args(argv)

    result = coverage()
    declared, resolvable, total, undeclared = (
        result.declared,
        result.resolvable,
        result.total,
        result.undeclared,
    )
    declared_pct = (declared / total * 100.0) if total else 0.0
    resolvable_pct = (resolvable / total * 100.0) if total else 0.0

    print(f"column_effect coverage: {declared}/{total} declared ({declared_pct:.0f}%)")
    print(f"resolvable by the lineage tracer: {resolvable}/{total} ({resolvable_pct:.0f}%)")

    if undeclared:
        by_family = Counter({fam: len(types) for fam, types in undeclared.items()})
        print("\nundeclared nodes by family (column lineage will report 'unknown' past these):")
        for family, count in sorted(by_family.items(), key=lambda kv: (-kv[1], kv[0])):
            print(f"  {family} ({count}): {', '.join(sorted(undeclared[family]))}")
    else:
        print("\nAll registered nodes declare a column_effect.")

    ok = resolvable_pct >= args.min_pct
    if not ok:
        print(
            f"\ntracer-resolvable coverage {resolvable_pct:.0f}% is below --min-pct "
            f"{args.min_pct:.0f}%; some nodes can't be traced by column lineage."
        )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
