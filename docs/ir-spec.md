# Colony Mind IR Specification

- **Version:** 1 (matches `CURRENT_SCHEMA_VERSION`)
- **Status:** Accepted
- **Date:** 2026-06-16

---

## Overview

The Colony Mind Intermediate Representation (IR) is the canonical, serializable,
declarative graph representation of a pipeline, module, or agent. It is the single
source of truth for what a graph *is* — exported Python code is a one-way compiled
artifact and does not sync back (ADR 0001). Execution runs over the IR directly
(`execute(ir)`), not over a generated string (ADR 0002). The IR is self-describing:
a frontend can produce a valid IR document with no Python runtime present.

Relevant ADRs:

- [ADR 0001 — Graph is the single source of truth](adr/0001-graph-is-single-source-of-truth.md)
- [ADR 0002 — Execute the IR, not the string](adr/0002-execute-the-ir-not-the-string.md)
- [ADR 0003 — SDK supports two paradigms from day one](adr/0003-sdk-supports-two-paradigms.md)
- [ADR 0004 — Storage tiering](adr/0004-storage-tiering.md)

---

## Model Reference

All models are defined in `colonymind/ir/` and are Pydantic v2 subclasses of `IRModel`
(`extra="forbid"`, `validate_assignment=True`). `IRId` is an opaque `str`; `new_id()`
generates a UUID4 string.

### Graph

`colonymind.ir.graph.Graph` — top-level serializable IR object.

| Field | Type | Default | Semantics |
|---|---|---|---|
| `schema_version` | `int` | `1` (`CURRENT_SCHEMA_VERSION`) | Embedded schema version; loaders detect stale or future graphs. |
| `paradigm` | `Paradigm` | `"functional"` | Graph-level paradigm tag; drives codegen/execution branching. |
| `name` | `str \| None` | `None` | Optional human-friendly label for the graph. |
| `nodes` | `dict[IRId, Node]` | `{}` | CRDT-friendly id→Node map. Keys must equal `node.id`. |
| `edges` | `dict[IRId, Edge]` | `{}` | CRDT-friendly id→Edge map. Keys must equal `edge.id`. |

Structural invariants enforced at construction: key/id agreement in both maps; edge
endpoints reference nodes and ports that exist; source port direction is `OUT`, target
is `IN`; `group_id` references an existing node.

### Node

`colonymind.ir.node.Node` — the central element of a graph.

| Field | Type | Default | Semantics |
|---|---|---|---|
| `id` | `IRId` | `new_id()` | Stable unique identifier (auto-generated). |
| `type` | `str` | required | Node type/family key, e.g. `"data.load_csv"`. Non-empty. |
| `label` | `str \| None` | `None` | Optional human-friendly display label. |
| `paradigm` | `Paradigm` | `"functional"` | Per-node paradigm tag; codegen and executor branch on this. |
| `params` | `list[Param]` | `[]` | Typed parameter values attached to this node. |
| `ports` | `list[Port]` | `[]` | The node's in/out connection points. |
| `position` | `Position` | `Position(x=0.0, y=0.0)` | Canvas coordinates. |
| `group_id` | `IRId \| None` | `None` | ID of the parent group node, or `None` for top-level. |
| `subgraph` | `Graph \| None` | `None` | Optional inner graph for composite/module/agent nodes. `None` for leaf nodes. |

### Position

`colonymind.ir.node.Position` — 2-D canvas coordinates.

| Field | Type | Default | Semantics |
|---|---|---|---|
| `x` | `float` | `0.0` | Horizontal canvas coordinate. |
| `y` | `float` | `0.0` | Vertical canvas coordinate. |

### Port

`colonymind.ir.port.Port` — a typed connection point on a node.

| Field | Type | Default | Semantics |
|---|---|---|---|
| `id` | `IRId` | `new_id()` | Stable unique identifier (auto-generated). |
| `name` | `str` | required | Port name, unique within its node. Non-empty. |
| `direction` | `Direction` | required | `"in"` (incoming edge) or `"out"` (outgoing edge). |
| `data_type` | `str` | `"any"` | Data-type token; stays a string on the wire but is validated against the type registry and resolved by inference during `cm.validate`. See [type-system-spec.md](./type-system-spec.md). |
| `cardinality` | `Cardinality` | `"one"` | `"one"` = single connection; `"many"` = fan-in/out allowed. |

### Edge and PortRef

`colonymind.ir.edge.Edge` — connects an OUT port on a source node to an IN port on a
target node.

| Field | Type | Default | Semantics |
|---|---|---|---|
| `id` | `IRId` | `new_id()` | Stable unique identifier (auto-generated). |
| `source` | `PortRef` | required | The OUT-side endpoint (`node_id` + `port_id`). |
| `target` | `PortRef` | required | The IN-side endpoint (`node_id` + `port_id`). |
| `type_compatible` | `bool \| None` | `None` | Type-compatibility metadata. `None` = not yet checked / unknown; populated by `cm.apply_type_compatibility` from a `cm.validate` result. |

`colonymind.ir.edge.PortRef` — an endpoint reference.

| Field | Type | Default | Semantics |
|---|---|---|---|
| `node_id` | `IRId` | required | ID of the node containing the port. Non-empty. |
| `port_id` | `IRId` | required | ID of the port on that node. Non-empty. |

Edges reference endpoints by id, not by object reference — this is deliberate for
CRDT-friendliness. Structural validation (whether the referenced nodes and ports exist)
is enforced by `Graph`'s model validator.

### Param

`colonymind.ir.params.Param` — a single typed, defaulted, serializable parameter on a node.

| Field | Type | Default | Semantics |
|---|---|---|---|
| `name` | `str` | required | Parameter name. Non-empty. |
| `type_token` | `str` | required | Opaque declared-type label, e.g. `"str"`, `"int"`, `"DataFrame"`. Non-empty. |
| `value` | `ParamValue` | `None` | Current serializable value. |
| `default` | `ParamValue` | `None` | Default serializable value. |

`ParamValue` is a recursive alias:
`str | int | float | bool | None | ArtifactRef | list[ParamValue] | dict[str, ParamValue]`.
`type_token` is a descriptive label for the param value, distinct from the port `data_type`
tokens the [connection type system](./type-system-spec.md) validates.

It is a *discriminated* union: an `ArtifactRef` is recognized only by its `kind`
discriminator tag (see below). A plain mapping that happens to share `ArtifactRef`'s
shape (e.g. `{"uri": "..."}`) is preserved as a mapping, so JSON round-trips are lossless.

### ArtifactRef

`colonymind.ir.common.ArtifactRef` — a pointer to a large artifact stored outside the IR.

| Field | Type | Default | Semantics |
|---|---|---|---|
| `kind` | `Literal["artifact_ref"]` | `"artifact_ref"` | Fixed discriminator tag; always emitted so a serialized `ArtifactRef` is distinguishable from a plain mapping. |
| `uri` | `str` | required | Location of the artifact (file path or object-store URI). Non-empty. |
| `media_type` | `str \| None` | `None` | Optional MIME hint, e.g. `"application/parquet"`. |

Artifact bytes are never embedded in the IR (ADR 0004). `ArtifactRef` carries only a
location pointer and an optional media-type hint. The `kind` tag defaults, so construction
stays `ArtifactRef(uri=...)`; it exists purely to make `ParamValue` round-trips lossless.

---

## The Two Paradigms (ADR 0003)

The IR supports two first-class execution paradigms via a single `paradigm` tag on both
`Graph` and `Node` (enum `Paradigm`):

- `"functional"` — a DAG of pure-ish transforms. Each node is a function call returning
  an inspectable result. Covers data engineering, statistics, classical ML, and reporting.
- `"declarative"` — a definition compiled into a class or graph object. Covers deep
  learning architectures (PyTorch `nn.Module`) and agent graphs (LangGraph).

This is **Option A** from ADR 0003: one nesting mechanism (`Node.subgraph`) represents
collapsible visual groups, declarative `nn.Module` bodies, and agent graphs alike. The
IR shape is uniform across both paradigms; codegen (`compile_to_code(ir)`) and execution
(`execute(ir)`) branch on the `paradigm` tag to produce idiomatic output.

The `paradigm` tag sits on both `Graph` (graph-level default) and `Node` (per-node
override). Functional-pipeline nodes emit chained function calls; declarative nodes emit
class bodies or graph-construction code. DL and agent node families are deferred to Phase
3; the IR plumbing is in place now to avoid a later structural rewrite.

See `examples/declarative_module.json` for an IR document using the declarative paradigm.

---

## Sub-graphs, Groups, and Nesting

`Node.subgraph` is an optional inner `Graph`. This single field covers three cases:

1. **Collapsible visual groups** — a UI grouping node with a `subgraph` containing the
   member nodes. Membership is expressed by the nesting itself: the members live inside
   the grouping node's `subgraph`.
2. **Declarative module bodies** — a `paradigm="declarative"` node whose `subgraph`
   describes the internal layer topology of an `nn.Module`.
3. **Agent sub-graphs** — an agent orchestration node whose `subgraph` is the agent's
   internal control-flow graph.

`Node.subgraph` (nesting) and `Node.group_id` (flat grouping) are **two distinct
mechanisms**. `group_id` records which group node a node belongs to *within the same
graph*: the grouping node and its members are siblings in one `nodes` map, and each
member's `group_id` points at the grouping node's `id`. `Graph`'s structural validator
enforces that any non-`None` `group_id` references an existing node in the **same** graph
— it does not cross `subgraph` boundaries, so a member nested inside a `subgraph` must not
set `group_id` to a node in the outer graph. Leaf nodes have `subgraph=None` and
`group_id=None`.

---

## Schema Versioning

Every `Graph` carries `schema_version: int` (current value: `1`, defined as
`colonymind.ir.graph.CURRENT_SCHEMA_VERSION`). Loaders can inspect this field to detect
stale or future graphs and reject or migrate them accordingly.

The migration framework (load old version → migrate → current, with versioned, ordered
steps) is Epic 1 Story 9. Full migration maturity is Epic 14. The policy: no breaking
schema change ships without a migration step.

---

## Serialization

JSON is the canonical on-the-wire and at-rest format for Phase 1. See
[docs/ir-serialization-format.md](ir-serialization-format.md) for the full decision record.

Key points:

- **Reference serializer:** `Graph.model_dump_json()` (Pydantic v2).
- **Reference deserializer:** `Graph.model_validate_json()`.
- **Language-agnostic contract:** `colonymind.ir.schema.ir_json_schema()` (wraps
  `Graph.model_json_schema()`) emits a standard JSON Schema document for non-Python
  clients (TypeScript frontend, CI validators, third-party integrations).
- **File extension:** `.cm.json` for persisted graph files.

---

## CRDT-Friendliness

The IR is shaped to support future multiplayer editing (Epic 13) without a structural rewrite:

- **Stable string ids** — every object (`Graph`, `Node`, `Port`, `Edge`) carries an
  immutable `id` (UUID4 string) that never changes across edits or merges.
- **`{id: object}` maps** — `Graph.nodes` and `Graph.edges` are `dict[IRId, ...]`, not
  ordered lists. Map-keyed structures are amenable to merge/patch operations (last-write-wins
  or CRDT merge) without index-offset conflicts.
- **Edges reference by id** — `PortRef` stores `node_id` + `port_id` strings, not object
  references, so edges survive independent serialization of node and edge maps.

These choices are deliberate. They add no runtime cost in Phase 1 and eliminate a class of
multiplayer merge conflicts that ordered-list representations cannot avoid.

---

## Examples

- `examples/functional_pipeline.json` — a functional-paradigm graph (data load → transform → stats node).
- `examples/declarative_module.json` — a declarative-paradigm graph (an `nn.Module`-style layer topology).
