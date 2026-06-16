# ADR 0004 — Storage tiering: metadata in Redis, artifacts on disk/object store

- **Status:** Accepted
- **Date:** 2026-06-16
- **Deciders:** Colony Mind core team

## Context

The Colony Mind proposal names Redis as the cache throughout. Redis is an in-memory store —
its design is optimized for small, fast key-value lookups, not bulk binary data. Pushing
multi-GB DataFrames or tensors through it would exhaust available memory rapidly and incur
slow serialization round-trips on every cache read and write.

A clear policy on what Redis is and is not responsible for is required before any caching or
execution-result storage logic is built. Without it, individual features will make inconsistent
assumptions about where large artifacts live, producing a system that is impossible to scale.

## Decision

We will tier the artifact store. Redis (or an equivalent in-memory index) holds **cache
metadata, execution hashes, small scalar/JSON results, and the DAG state index** — any value
small enough to live cheaply in memory. Large artifacts (DataFrames, tensors, models, HTML
reports) are serialized to a **disk- or object-backed store** using columnar or zero-copy
formats: Arrow IPC / Parquet for tabular frames, and `torch.save` / safetensors for model
weights. The cache key stored in Redis points at the artifact **location** (a path or object
store URI), not the artifact bytes themselves.

## Consequences

**Positive:**

- Redis memory usage stays bounded regardless of artifact size, making the system safe to
  operate at scale.
- Columnar and zero-copy formats (Arrow IPC, Parquet, safetensors) allow large artifacts to be
  read back without deserializing the entire file, enabling efficient partial reads.
- The split responsibility is explicit: Redis is the index, the disk/object store is the
  archive. Each component does what it is designed for.

**Negative / obligations:**

- The IR must reference artifact **locations**, not embed artifact bytes. This is a hard
  constraint on the Epic 1 IR schema: any node output or cache reference in the IR that touches
  a large artifact must carry a location pointer (path or URI), never raw binary data. Violating
  this constraint would silently re-introduce the memory problem this decision is designed to
  prevent.
- Reads that cross the location pointer boundary (resolve a key in Redis, then fetch bytes from
  the disk/object store) involve two hops. Code that handles artifact retrieval must account for
  this two-step pattern from the start.

**Deferred:**

- The full storage layer — the concrete disk/object store implementation, the serialization
  helpers, eviction policy, and any remote object-store integration — is deferred to Epic 7.
  This ADR records the architectural constraint only; it does not prescribe the Epic 7
  implementation details.
