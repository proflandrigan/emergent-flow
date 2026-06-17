# IR Schema Migrations

- **Status:** Accepted
- **Date:** 2026-06-17
- **Deciders:** Colony Mind core team
- **Relates to:** Epic 1 Story 9; `docs/ir-serialization-format.md`

## Why

Saved graphs are long-lived. A graph authored today must still open after the IR schema
evolves. Without a migration path, any schema change risks bricking saved work. This document
describes the migration framework (`colonymind/ir/migrate.py`) and the policy that governs it.

## Model

- Every serialized graph embeds a `schema_version` (an integer). The version this build
  understands is `colonymind.ir.CURRENT_SCHEMA_VERSION`.
- A **migration step** is a pure function `dict -> dict` that transforms a parsed (pre-validation)
  graph dict from version `N` into the shape expected at version `N + 1`. Steps do NOT stamp
  `schema_version` — the framework stamps it after each step runs.
- Migrations operate on the raw parsed JSON dict **before** Pydantic validation, because the IR
  models forbid unknown fields (`extra="forbid"`); a legacy field must be migrated away before
  the model will accept the graph.

## API

| Symbol | Purpose |
| --- | --- |
| `register_migration(from_version, step)` | Register `step` as the migration `from_version -> from_version + 1`. Rejects negative/at-or-above-current versions and duplicates. |
| `migrate_to_current(doc, *, found, target=CURRENT_SCHEMA_VERSION, migrations=None)` | Chain registered steps from `found` up to `target`, stamping `schema_version` after each. Raises `MigrationError` on a missing step or an attempted downgrade. |
| `migrate_document(parsed)` | Migrate a parsed graph dict **and every nested subgraph** (each by its own `schema_version`) up to current. Returns a new dict; does not mutate the input. |
| `MigrationError` | Raised when a graph cannot be migrated (missing step, or downgrade). |
| `MigrationStep` | Type alias: `Callable[[dict], dict]`. |

All are re-exported from `colonymind.ir`.

## On load

`deserialize_graph` (in `colonymind.ir.serialize`) applies the policy:

1. Reject any graph — top-level or nested subgraph — whose `schema_version` is **newer** than
   `CURRENT_SCHEMA_VERSION` (`SchemaVersionError`; upgrade the build to read it).
2. Otherwise route the parsed document through `migrate_document`, migrating older graphs (and
   older nested subgraphs) up to current.
3. Validate the migrated document into a `Graph`.

## Authoring a migration (example)

When a schema change ships, bump `CURRENT_SCHEMA_VERSION` and register the step that upgrades the
previous version to the new one:

```python
from colonymind.ir.migrate import register_migration

def _migrate_v1_to_v2(doc: dict) -> dict:
    doc = dict(doc)
    # ... structural transform from v1 shape to v2 shape ...
    return doc  # do NOT set schema_version; the framework stamps it

register_migration(1, _migrate_v1_to_v2)
```

The repo currently ships ONE synthetic, illustrative example: a `v0 -> v1` step
(`_migrate_v0_to_v1`) that renames a legacy top-level `"mode"` key to `"paradigm"`. There was
never a real released schema v0 — it exists only to exercise and document the mechanism, and
should be replaced when the first real schema bump lands. Fixtures backing the migration tests
live in `tests/fixtures/` (`graph_v0.json`, `graph_nested_v0_subgraph.json`).

## Policy

**No breaking schema change ships without a migration step.** Any change that alters the
serialized IR shape in a way an older graph would not satisfy MUST:

1. Bump `CURRENT_SCHEMA_VERSION`.
2. Register a `register_migration(prev, step)` that upgrades the previous version to the new one.
3. Add a fixture saved at the previous version plus a test asserting it migrates and loads.

A schema change without its migration step is incomplete and must not merge.
