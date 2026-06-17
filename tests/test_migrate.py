"""
tests/test_migrate.py
~~~~~~~~~~~~~~~~~~~~~~
Story 9 — migration framework core.

Covers the public API in ``colonymind.ir.migrate``:
  - chaining ordered migration steps and stamping ``schema_version`` after each;
  - no-op when already at the target version;
  - clear errors for missing intermediate steps and downgrade attempts;
  - the entry-copy guarantee (caller's dict is never mutated);
  - ``register_migration``'s validation of `from_version`.

Tests use the injectable ``migrations=`` / ``target=`` params throughout so they never
touch the global registry or depend on ``CURRENT_SCHEMA_VERSION``'s value — except
``TestRegisterValidates``, which exercises the real registry's rejection paths only.
"""

from __future__ import annotations

import pytest

from colonymind.ir.graph import CURRENT_SCHEMA_VERSION
from colonymind.ir.migrate import MigrationError, migrate_to_current, register_migration

# ---------------------------------------------------------------------------
# Step helpers
# ---------------------------------------------------------------------------


def bump(doc: dict) -> dict:
    """Trivial step: marks that it ran, without touching schema_version itself."""
    doc = dict(doc)
    doc["bumped"] = True
    return doc


def add_a(doc: dict) -> dict:
    doc = dict(doc)
    doc["a"] = True
    return doc


def add_b(doc: dict) -> dict:
    doc = dict(doc)
    doc["b"] = True
    return doc


def add_c(doc: dict) -> dict:
    doc = dict(doc)
    doc["c"] = True
    return doc


# ---------------------------------------------------------------------------
# Chaining
# ---------------------------------------------------------------------------


class TestMigrateToCurrent:
    def test_single_step_migrates_and_stamps_version(self):
        migrations = {0: bump}
        result = migrate_to_current({}, found=0, target=1, migrations=migrations)
        assert result["bumped"] is True
        assert result["schema_version"] == 1

    def test_multi_step_chains_in_order(self):
        migrations = {0: add_a, 1: add_b, 2: add_c}
        result = migrate_to_current({}, found=0, target=3, migrations=migrations)
        assert result["a"] is True
        assert result["b"] is True
        assert result["c"] is True
        assert result["schema_version"] == 3

    def test_noop_when_found_equals_target(self):
        doc = {"schema_version": 2, "name": "unchanged"}
        result = migrate_to_current(doc, found=2, target=2, migrations={})
        assert result == doc
        # The no-op still returns a NEW top-level dict (never the caller's object), so a
        # caller mutating the result cannot reach back into its input.
        assert result is not doc

    def test_missing_step_raises_migration_error(self):
        migrations = {0: bump}
        with pytest.raises(MigrationError, match="v1"):
            migrate_to_current({}, found=0, target=2, migrations=migrations)

    def test_downgrade_raises(self):
        with pytest.raises(MigrationError):
            migrate_to_current({}, found=3, target=1, migrations={})

    def test_input_dict_not_mutated(self):
        original = {"schema_version": 0}
        migrations = {0: add_a}
        result = migrate_to_current(original, found=0, target=1, migrations=migrations)
        assert original == {"schema_version": 0}
        assert "a" not in original
        assert result["a"] is True


# ---------------------------------------------------------------------------
# register_migration validation
# ---------------------------------------------------------------------------


class TestRegisterValidates:
    def test_negative_from_version_raises(self):
        with pytest.raises(MigrationError):
            register_migration(-1, bump)

    def test_from_version_at_or_above_current_raises(self):
        with pytest.raises(MigrationError):
            register_migration(CURRENT_SCHEMA_VERSION, bump)

    def test_duplicate_registration_raises(self):
        # Only versions < CURRENT_SCHEMA_VERSION are registerable at all. Register once,
        # confirm the second registration for the same version is rejected, then clean up
        # so this test doesn't leak global state to other tests.
        from colonymind.ir.migrate import _MIGRATIONS

        from_version = CURRENT_SCHEMA_VERSION - 1
        assert from_version >= 0, "CURRENT_SCHEMA_VERSION must be >= 1 for this test to apply"

        already_registered = from_version in _MIGRATIONS
        if not already_registered:
            register_migration(from_version, bump)
        try:
            with pytest.raises(MigrationError):
                register_migration(from_version, bump)
        finally:
            if not already_registered:
                del _MIGRATIONS[from_version]


# ---------------------------------------------------------------------------
# Example migration + document-level walk
# ---------------------------------------------------------------------------


class TestExampleMigrationAndDocumentWalk:
    def test_v0_to_v1_step_renames_mode_to_paradigm(self):
        from colonymind.ir.migrate import _migrate_v0_to_v1

        result = _migrate_v0_to_v1({"mode": "declarative"})
        assert result == {"paradigm": "declarative"}
        assert "mode" not in result

    def test_example_step_is_registered(self):
        import colonymind.ir.migrate

        assert 0 in colonymind.ir.migrate._MIGRATIONS

    def test_migrate_document_flat_v0(self):
        from colonymind.ir.migrate import migrate_document

        doc = {"schema_version": 0, "mode": "functional", "nodes": {}, "edges": {}}
        result = migrate_document(doc)
        assert result["schema_version"] == 1
        assert result["paradigm"] == "functional"
        assert "mode" not in result

    def test_migrate_document_recurses_into_subgraph(self):
        from colonymind.ir.migrate import migrate_document

        doc = {
            "schema_version": 1,
            "paradigm": "functional",
            "nodes": {
                "n1": {
                    "id": "n1",
                    "type": "composite",
                    "subgraph": {
                        "schema_version": 0,
                        "mode": "declarative",
                        "nodes": {},
                        "edges": {},
                    },
                }
            },
            "edges": {},
        }
        result = migrate_document(doc)
        sub = result["nodes"]["n1"]["subgraph"]
        assert sub["schema_version"] == 1
        assert sub["paradigm"] == "declarative"
        assert "mode" not in sub

    def test_migrate_document_does_not_mutate_input(self):
        from colonymind.ir.migrate import migrate_document

        doc = {"schema_version": 0, "mode": "functional", "nodes": {}, "edges": {}}
        original = doc
        migrate_document(doc)
        assert original["schema_version"] == 0
        assert original["mode"] == "functional"
