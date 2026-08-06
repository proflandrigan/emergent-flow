#!/usr/bin/env python3
"""Report column_effect coverage across the node catalog (Epic 18, Story 8).

Column lineage (Epic 18) resolves a node's column mapping from its declared
``column_effect`` (``emergentflow.nodes.spec.ColumnEffect``); an undeclared node
reports an explicit "unknown" boundary. This script lists every registered node
lacking a declaration, grouped by family, and prints the overall coverage. It
exit non-zero when declared coverage falls below ``--min-pct`` (default 40),
so CI can track it rather than assert a hard number: adding a node can't
silently regress lineage quality.

Run::

    uv run python scripts/check_column_effect_coverage.py [--min-pct 40]
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict

from emergentflow.nodes.registry import registry


def coverage() -> tuple[int, int, dict[str, list[str]]]:
    """Return (declared, total, {family: [undeclared node types]})."""
    undeclared: dict[str, list[str]] = defaultdict(list)
    for type_key, definition in sorted(registry._defs.items(), key=lambda kv: kv[0]):
        if definition.column_effect is None:
            undeclared[definition.family].append(type_key)
    declared = len(registry._defs) - sum(len(v) for v in undeclared.values())
    return declared, len(registry._defs), dict(undeclared)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--min-pct",
        type=float,
        default=40.0,
        help="Exit non-zero when declared coverage drops below this percent (default 40).",
    )
    args = parser.parse_args(argv)

    declared, total, undeclared = coverage()
    pct = (declared / total * 100.0) if total else 0.0

    print(f"column_effect coverage: {declared}/{total} declared ({pct:.0f}%)")

    if undeclared:
        by_family = Counter({fam: len(types) for fam, types in undeclared.items()})
        print("\nundeclared nodes by family (column lineage will report 'unknown' past these):")
        for family, count in sorted(by_family.items(), key=lambda kv: (-kv[1], kv[0])):
            print(f"  {family} ({count}): {', '.join(sorted(undeclared[family]))}")
    else:
        print("\nAll registered nodes declare a column_effect.")

    ok = pct >= args.min_pct
    if not ok:
        print(
            f"\ncoverage {pct:.0f}% is below --min-pct {args.min_pct:.0f}%; some nodes can't be "
            "traced by column lineage."
        )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
