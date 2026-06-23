# ADR 0006 — Node registry and plugin discovery via entry points

- **Status:** Accepted
- **Date:** 2026-06-16
- **Deciders:** Colony Mind core team

## Context

[ADR 0005](0005-node-definition-contract.md) defines what a node *is* — the two-halves
contract (serializable `NodeSpec` + Python `NodeDefinition` behaviour). What it explicitly
defers is how node types are *indexed* and how the catalog grows over time. That deferral is
now due.

Four consumers — the registry (Story 4), codegen (Epic 2), the executor (Epic 2), and the
config UI (Epic 4) — all need to look up a node type by its `type` string and get a uniform
view of it. Without a registry, each consumer would need its own list of known types, which
means every new node type requires edits in multiple places. The same friction would block
community extensibility entirely.

The forces at play:

- **In-tree nodes need zero-ceremony registration.** A reference node added to
  `colonymind/nodes/examples/` should be available to the rest of the system the moment its
  module is imported, with no separate catalog file to edit.
- **Third parties need to add nodes without forking core.** Community node libraries must be
  able to contribute types via a package-level declaration — the Python ecosystem's
  established mechanism for this is setuptools entry points.
- **Consumers need uniform lookup.** Codegen, execution, and the UI must all be able to
  resolve a `type` string to a definition without knowing whether that definition is in-tree
  or from a plugin. The registry must be the single, authoritative source.
- **Bad or duplicate definitions must fail loudly and early.** A malformed definition that
  silently enters the catalog would cause confusing errors at execution time, potentially far
  from the registration site. Duplicate `type` keys from two different classes must not
  silently shadow each other.
- **The frontend must work with no Python present.** The UI needs a serializable catalog
  view; it must not depend on importing or instantiating executor code.

[ADR 0002](0002-execute-the-ir-not-the-string.md) established that the IR is canonical and
that code is a compiled artifact. The registry is the catalog that makes the IR's `type`
string resolvable to a concrete definition.

## Decision

We will implement the following:

1. **A `NodeRegistry` class** that indexes `NodeDefinition` subclasses by their `type` catalog
   key, with a module-level default singleton (`colonymind.nodes.registry`). All in-tree code
   and the default plugin-discovery path target this singleton. Tests create isolated
   `NodeRegistry()` instances.

2. **Two registration paths:**
   - A `@register` decorator (and `NodeRegistry.register()` method) for in-tree nodes.
     Registration fires at import time, so importing a node module is sufficient to populate
     the catalog. The decorator doubles as a fail-fast validator: it rejects non-`NodeDefinition`
     objects, the abstract base class itself, missing/empty `type`/`family`/`label`, a
     `to_spec()` that raises, and a different class attempting to claim an already-registered
     `type` key (re-registering the same class is a no-op).
   - An **entry-point path** for out-of-core plugins. Third-party packages publish node
     definitions by declaring an entry point in the `colonymind.nodes` group (the constant
     `ENTRY_POINT_GROUP`). `NodeRegistry.discover()` loads every entry point via
     `importlib.metadata` and passes each result to `register()`. Plugins do not call
     `@register` themselves; the entry-point declaration is the only integration surface.

3. **Lookups return definition classes.** `get(type_key)`, `try_get(type_key)`,
   `by_family(family)`, `by_port_type(data_type, direction=None)`, `all()`, and the `in`
   operator and iteration all return `type[NodeDefinition]` (or lists thereof). The caller
   instantiates and calls methods as needed. A `specs()` method returns a serializable
   `list[NodeSpec]` — calling `to_spec()` on a fresh instance of each definition — so the UI
   can consume the catalog as plain JSON without importing any behaviour code.

4. **Two-layer validation:**
   - `register()` performs fail-fast, per-definition checks synchronously (raises
     `ValueError`).
   - `NodeRegistry.validate()` performs a non-raising, whole-catalog sweep and returns a
     `list[str]` of human-readable problem messages. It re-checks stored-key/declared-type
     alignment, re-runs `to_spec()`, and verifies port-name uniqueness per direction,
     param-name uniqueness, and `version >= 1`. This is safe to call in CI startup or health
     checks.

5. **Discovery is resilient.** A single broken entry point — whether `load()` raises, the
   loaded object fails `register()`, or it carries a duplicate `type` key — is recorded as
   a problem string and returned. Discovery continues across all remaining entry points;
   `discover()` never raises. Good definitions still register.

## Consequences

**Positive:**

- The catalog grows without any core change. A new in-tree family adds one decorated class;
  a new plugin adds one `pyproject.toml` entry point and one class. No core edit required in
  either case.
- The UI stays Python-free. `registry.specs()` delivers the complete catalog as
  `list[NodeSpec]` — plain, JSON-serializable Pydantic models (same `IRModel` base as the
  IR). The browser never imports a node module.
- CI can assert catalog health with a single `assert not validate()` call. Fail-fast
  `register()` catches broken definitions at module-import time in development.
- Consumers (codegen, executor, UI) treat every node family identically via uniform lookup —
  no family-specific branching in core.
- Discovery resilience means one broken community plugin does not take down the rest of the
  catalog at startup.

**Negative / obligations:**

- Plugin authors are responsible for choosing globally unique `type` keys. The registry
  rejects a duplicate, but there is no central namespace registry to prevent two unrelated
  plugins from independently choosing the same key. The "first registered wins / second
  rejected" rule means the loser of a name collision gets a startup warning rather than
  silent misbehavior, but the resolution still requires manual intervention by the plugin
  authors.
- The entry-point discovery surface is now part of the public contract. The group name
  `"colonymind.nodes"` and the expectation that each entry-point value resolves to a
  `NodeDefinition` subclass are stable commitments.

**Deferred:**

- **Community plugin trust and sandboxing.** `discover()` calls `ep.load()`, which imports
  arbitrary third-party code into the host process. Sandboxing, code-signing, or a vetted
  marketplace are later-epic concerns.
- **Richer duplicate-key conflict resolution.** The current policy is first-registered wins,
  second-different-class rejected. A priority or version-aware conflict-resolution policy is
  deferred.
- **Type-aware `by_port_type` matching.** `by_port_type` compares `data_type` tokens as
  plain strings for registry lookup. Type-system-aware compatibility — the `"any"` wildcard
  and the declared subtype relation (e.g. `"DataFrame"` satisfies a `"Table"` port) — lives
  in the connection type system (repo Epic 3 / roadmap Epic 5); see
  [ADR 0011](./0011-type-model-and-compatibility.md) and `cm.validate`.
