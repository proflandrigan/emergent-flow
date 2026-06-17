# IR Serialization Format — JSON-first, Protobuf-able later

- **Status:** Accepted
- **Date:** 2026-06-16
- **Deciders:** Colony Mind core team

## Context

Story 2 of Epic 1 publishes the Colony Mind IR as a formal spec. The IR models are defined
in Pydantic v2 (`colonymind/ir/`); the serialization format is the wire/at-rest encoding
that the frontend writes, the backend reads, and external tools validate against.

Several options exist: JSON, MessagePack, Protobuf, CBOR, or a custom binary. Each trades
human-readability, browser-native support, schema tooling, and migration complexity
differently.

## Decision

JSON is the canonical on-the-wire and at-rest serialization format for the Colony Mind IR
during Phase 1.

- **Reference serializer / deserializer:** Pydantic v2 `model_dump_json()` and
  `model_validate_json()` on `colonymind.ir.graph.Graph`.
- **Language-agnostic contract:** the JSON Schema emitted by `colonymind.ir.schema.ir_json_schema()`
  (derived from `Graph.model_json_schema()`) is the validation contract for non-Python clients
  such as the TypeScript frontend.
- **File extension convention:** `.cm.json` for persisted graph files.

## Public API (`colonymind.ir.serialize`)

The reference Pydantic methods above are wrapped by a small, stable public API (Story 5).
Application code should use these rather than calling Pydantic directly — they add
schema-version enforcement, clean error types, and file I/O over the ``.cm.json`` convention.

| Function | Purpose |
| --- | --- |
| `serialize_graph(graph, *, indent=2) -> str` | Graph → JSON text (embeds `schema_version`; `indent=None` for compact). |
| `deserialize_graph(data) -> Graph` | JSON text/bytes → validated `Graph`. |
| `save_graph(graph, path, *, indent=2) -> Path` | Serialize and write UTF-8 (trailing newline). |
| `load_graph(path) -> Graph` | Read a file and deserialize it. |

All four are re-exported from `colonymind.ir`.

### Validation on load

`deserialize_graph` parses JSON, checks the schema version, then runs full model +
structural validation. Structural invariants (edges referencing real nodes/ports, port
directions, group ids) are **not** re-implemented here — they live in
`Graph._validate_structure` and run during validation; this layer only surfaces failures
as clean errors.

### Schema-version policy

A serialized graph carries `schema_version`. On load (`CURRENT` = the version this build
supports):

| Embedded version | Behaviour |
| --- | --- |
| `== CURRENT` | Loads. |
| `> CURRENT` | `SchemaVersionError` — written by a newer build; upgrade to load. |
| `< CURRENT` | **Migrated** up to `CURRENT` by the Story 9 migration framework (`migrate_document`) before validation; loads if a migration path exists. If a required step is missing, raises `SchemaVersionError`. See [IR Schema Migrations](./ir-migrations.md). |

The policy applies to **every** serialized graph in the document, including the subgraphs of
composite nodes — each carries its own `schema_version` and is checked on load.

### Error types

All defined in `colonymind.ir.serialize` and re-exported from `colonymind.ir`:

- `GraphSerializationError` — base class.
- `GraphDeserializationError` — malformed JSON, non-object payload, or failed validation.
- `SchemaVersionError(GraphDeserializationError)` — version not loadable by this build;
  carries `.found` and `.expected` for programmatic branching.

## Why JSON-first

1. **Browser-native, no Python required.** The frontend must produce valid IR graphs without
   a Python runtime present. JSON is parsed natively in every browser and JavaScript runtime;
   no compile step, no protoc, no additional codec.

2. **Human-diffable — the glass-box promise.** IR files exported to Git must be readable and
   reviewable without specialist tooling. JSON diffs in pull requests are straightforward;
   binary formats are not.

3. **JSON Schema for cross-language validation.** Pydantic v2 generates a standard
   JSON Schema document from the models. Frontend code, CI validators, and third-party
   integrations can all validate payloads against this schema without importing Python.

4. **CRDT-friendly shape.** The IR uses `{id: object}` maps keyed by stable string ids (not
   ordered arrays), which keeps the JSON shape amenable to future merge/patch operations
   (Epic 13 multiplayer). This is deliberate, not incidental.

## Protobuf-able later

The schema is intentionally flat and declarative: maps keyed by stable string ids, enums
serialized as strings, no Python-object references, no embedded bytes (ADR 0004). This means
a Protobuf or other binary encoding can be added later as a performance optimization without
changing the logical model or requiring model changes.

Binary encoding is explicitly deferred. It will not be introduced before the core IR and
serialization round-trip are stable, and only if profiling shows JSON throughput is a
bottleneck at real workload sizes.

## Consequences

**Positive:**

- Zero additional dependencies for serialization in Phase 1.
- Frontend team gets a JSON Schema contract they can import directly into TypeScript
  validation (`zod`, `ajv`, etc.).
- IR files are git-diffable and auditable out of the box.

**Negative / watch points:**

- JSON is verbose relative to binary formats; large graphs with many nodes/edges will produce
  larger payloads. Acceptable for Phase 1; revisit if benchmarks show this is material.

**Deferred:**

- Protobuf / MessagePack / CBOR encoding — explicitly out of scope until profiling justifies it.
- Streaming / chunked serialization for very large graphs.
