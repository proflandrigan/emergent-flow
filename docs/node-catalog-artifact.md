# Node Catalog Artifact — the data-driven palette contract

- **Status:** Accepted
- **Date:** 2026-06-25
- **Deciders:** Colony Mind core team

## Context

The canvas's node palette and its schema-driven config panels (roadmap Epic 4 / repo Epic 5
Stories 3–4) must render every node in the registry — `label`, `category`, one-line
`description`, ports, and per-param defaults/help/validation hints — **without importing
Python or round-tripping to a server for metadata that never changes during a session**. This
is the same boundary discipline that already governs the IR schema, the generated-code
string, and the type-rules artifact ([ADR 0012](./adr/0012-rules-as-portable-data.md)): the
canvas (ADR 0013, ADR 0014) consumes **data**, never a shared Python import.

[ADR 0015](./adr/0015-node-catalog-and-export.md) decided that the node catalog is the
**fourth** SDK→canvas contract artifact and fixed its high-level shape and versioning policy.
This document is the artifact's contract spec — the concrete field-by-field shape, ordering
guarantee, and producer contract — the sibling of
[`docs/result-payload-contract.md`](./result-payload-contract.md) and the rules-as-data ADR,
written at the same level of detail so Story 2's `cm.export_catalog()` implementation and any
canvas-side consumer can code against it without re-deriving the decision.

## Purpose

The catalog artifact is the single source every palette entry and every config panel is
rendered from:

- **The palette** lists every registered node, grouped by `category`, labeled by `label`, with
  `description` as the hover/help summary — no per-node frontend component is hand-written.
- **The config panel** for a node on the canvas is generated entirely from that node's
  `params` array — each param's `type_token`, `default`, `required`, `label`, `help`, and
  `hints` drive a generic form-field renderer (ADR 0013/0014's schema-driven panels), so adding
  a node never requires adding UI code.

If a node is in the registry but missing from this artifact, it cannot appear on the canvas at
all — the artifact is not a cache or an optimization, it is the **only** path from a
registered `NodeDefinition` to a visible palette entry.

## The artifact shape

```json
{
  "catalog_version": 1,
  "nodes": [
    {
      "type": "data.load_csv",
      "version": 2,
      "family": "data",
      "label": "Load CSV",
      "category": "Ingest",
      "description": "Load a CSV file into a pandas DataFrame.",
      "paradigm": "functional",
      "ports": [{ "name": "frame", "direction": "out", "data_type": "DataFrame", "...": "..." }],
      "params": [
        {
          "name": "path",
          "type_token": "str",
          "default": null,
          "required": true,
          "label": "CSV path",
          "help": "...",
          "hints": { "widget": "file" }
        }
      ]
    }
  ]
}
```

### Top-level fields

| Field             | Type     | Meaning |
| :---------------- | :------- | :------ |
| `catalog_version` | `int`    | The artifact's own version (see Versioning below). |
| `nodes`           | `list`   | One entry per registered `NodeDefinition`, sorted by `type` (see Ordering below). |

### Per-node fields

| Field         | Type             | Meaning |
| :------------ | :--------------- | :------ |
| `type`        | `str`            | The node's registry key, e.g. `"data.load_csv"` (ADR 0005). |
| `version`     | `int`            | The node's **contract** version — bumped on any `codegen`/param change, independent of `catalog_version` and of `Graph.schema_version`. Lets the canvas detect that a saved graph references an older node contract than the one the SDK currently ships. |
| `family`      | `str`            | The owning family namespace (`data`, `clean`, `stats`, `ml`, `reports`, …). |
| `label`       | `str`            | Human-readable display name for the palette entry. |
| `category`    | `str`            | The palette grouping bucket (e.g. `"Ingest"`, `"Clean"`, `"Model"`). |
| `description` | `str`            | One-line summary, used as palette hover text / config-panel header. |
| `paradigm`    | `str`            | `"functional"` or `"declarative"` (ADR 0003) — which compiler/executor path the node participates in. |
| `ports`       | `list`           | Each port's `name`, `direction` (`"in"`/`"out"`), `data_type` token (ADR 0011), and any port-level metadata the contract carries. |
| `params`      | `list`           | Each param's full schema, below. |

### Per-param fields

| Field         | Type             | Meaning |
| :------------ | :--------------- | :------ |
| `name`        | `str`            | The param's key, as used in `NodeDefinition.params` and the IR. |
| `type_token`  | `str`            | The param's declared type token (e.g. `"str"`, `"int"`, `"float"`, `"bool"`). |
| `default`     | JSON value/`null`| The param's default value, or `null` if it has none. |
| `required`    | `bool`           | Whether the param must be set before the node validates. |
| `label`       | `str`            | Human-readable field label for the generated config-panel form field. |
| `help`        | `str`            | Help text shown alongside the field (tooltip / inline description). |
| `hints`       | `object`         | Validation/widget hints (e.g. `{"widget": "file"}`, min/max, regex) consumed by the generic form-field renderer to pick the right input control and client-side checks. |

These are exactly the fields the Epic 1 node contract (`NodeDefinition`, ADR 0005) already
carries or is extended *minimally* to carry per Story 1's decision — this artifact does not
introduce new node-authoring concepts, it only **exports** what the contract already declares.

## Versioning

`catalog_version` is **decoupled from `Graph.schema_version`**, the same decision ADR 0012
made for the rules-as-data artifact and for the same reason: the catalog grows whenever a node
gains a `description` tweak, a new param hint, or an entirely new node, none of which change
the IR wire format. Coupling the two would force a spurious `schema_version` bump — and every
graph file's migration story along with it — on every catalog change. The two versions evolve
independently:

- `Graph.schema_version` bumps only when the **wire format** of a serialized graph changes
  (new/changed IR fields), driving `migrate_to_current` (Epic 14).
- `catalog_version` bumps whenever the **catalog artifact's shape** changes — a new top-level
  field, a new per-node or per-param field, or a changed field's meaning. Adding a node or
  changing a node's `description` does **not**, by itself, require a `catalog_version` bump;
  it only changes the `nodes` payload, not the artifact's shape.

A node's own `version` (ADR 0005, restated in [ADR 0015](./adr/0015-node-catalog-and-export.md)'s
decision 4) is a third, independent axis: it tracks that **specific node's** contract, so the
canvas can flag "this graph was built against `data.load_csv` v1; the SDK now ships v2" without
implying anything about `catalog_version` or `Graph.schema_version`.

## Ordering

`nodes` is sorted by `type` (lexicographic, ascending) on every export. This makes the
artifact's JSON serialization **stable and golden-testable** — two exports of an unchanged
registry produce byte-identical output, and a diff of the golden file shows exactly which
nodes changed when the registry changes. Producers must not rely on registry insertion order
or dict iteration order; the sort is applied explicitly before serialization.

## Producer

`cm.export_catalog()` (alongside `cm.build_rules_artifact()` and the other artifact exporters,
each a top-level `cm.*` entry point) builds this artifact from the **live node registry**.
Like every other exporter in this chain, it is:

- **Pure** — no I/O, no global state; it reads the registry and returns data.
- **Deterministic** — the same registry state always produces the same artifact (guaranteed by
  the `type`-sorted `nodes` list above).
- **JSON-native** — every field is a JSON-serializable primitive, list, or object; the artifact
  round-trips through `json.dumps`/`json.loads` with no Python-specific types, matching the
  inspectability bar the rest of the public API holds (`@public_op`'s `is_inspectable` check).

Two consumers are produced from this **single builder** — there is no second, divergent code
path:

- The local server's `GET /catalog` endpoint calls `cm.export_catalog()` at request time.
- The committed `ui/src/generated/catalog.json` is generated from the same builder (e.g. at
  build time or via a regeneration script), so the bundled canvas (ADR 0013) ships a catalog
  snapshot without needing a live server round-trip.

Both paths calling the same pure function is what rules out a two-tier palette: there is no
world in which the server's palette and the bundled UI's palette diverge, because both are
serializations of the same registry through the same function.

## Out of scope (this document)

- The `cm.export_catalog()` implementation itself, and its golden test — Epic 6 Story 2.
- Backfilling `label`/`category`/`description`/param `help`/`hints` onto the five existing
  reference nodes — Story 2.
- Any new node added to widen a family (Stories 3–6) — this document fixes the shape every
  such node's metadata must conform to, not the nodes themselves.
