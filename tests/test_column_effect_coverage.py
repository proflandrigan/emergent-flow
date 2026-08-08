"""Tests for the Epic 18 column-effect coverage report (Story 8).

The report is a CI-visible gate that lists nodes lacking a ``column_effect``
declaration so coverage is tracked rather than asserted, and a new node can't
silently regress lineage quality. These tests exercise the pure ``coverage()``
function without asserting a hard percentage (the DoD allows the long tail of
non-table-producing nodes to report ``unknown``).
"""

from __future__ import annotations

from scripts.check_column_effect_coverage import coverage


def test_coverage_counts_and_groups_by_family() -> None:
    result = coverage()
    assert result.total > 0
    assert result.declared >= 1
    assert 0 <= result.declared <= result.total
    # The tracer-resolvable subset can't exceed the declared set and is non-empty.
    assert 0 < result.resolvable <= result.declared
    # Every undeclared entry is a real registered node type, grouped by family.
    assert result.undeclared
    for family, types in result.undeclared.items():
        assert family
        assert types
        for t in types:
            assert t.startswith(f"{family}.")


def test_declared_plus_undeclared_equals_total() -> None:
    result = coverage()
    n_undeclared = sum(len(types) for types in result.undeclared.values())
    assert result.declared + n_undeclared == result.total
