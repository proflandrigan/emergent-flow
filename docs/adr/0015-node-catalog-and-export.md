# ADR 0015 — Ship the node catalog as a versioned data artifact, with its own version

- **Status:** Accepted
- **Date:** 2026-06-25
- **Deciders:** Emergent Flow core team

## Context

Repo Epic 6 (roadmap Epic 4 — Node Library & Configuration UX) widens each family
(`ef.data`, `ef.clean`, `ef.stats`, `ef.ml`, `ef.reports`) from the one reference node that
proved the contract by construction (the proposal's vertical slice: `load_csv →
impute_missing → anova → train_classifier → generate_html_summary`) into a genuinely usable
palette. Before any family is widened, the catalog-level decisions need to be fixed the same
way Epics 1–5 fixed their decisions before building — cheap to decide now, expensive to
retrofit once a dozen nodes and a canvas palette depend on the shape.

Four questions are open:

1. **How wide does the catalog get, and when is it "done"?** A demoable pipeline needs more
   than five nodes, but "complete coverage of pandas/scikit-learn/statsmodels" is unbounded
   and not this epic's job.
2. **Does the catalog ship an escape-hatch node** — a raw-Python or raw-SQL node that lets a
   user drop arbitrary code into the graph? The roadmap flags this as the one load-bearing
   open question for the node library.
3. **What is the shape of the catalog-as-data artifact** the canvas's data-driven palette
   (ADR 0013, ADR 0014) consumes, and does it carry its own version or ride on
   `Graph.schema_version`?
4. **What discipline governs a node's per-node `version`** (already part of the Epic 1
   contract, ADR 0005) as the catalog grows and existing nodes' codegen/params change?

These are catalog-wide policy calls, not per-node implementation details, so they belong in
an ADR rather than being decided ad hoc inside Story 2's `ef.export_catalog()` work.

## Decision

We will lock the following four decisions for the node catalog:

**1. Breadth policy — demo-narrative-driven, not exhaustive.** We will widen each family only
by what a demoable, end-to-end pipeline needs, mirroring the roadmap's "narrow but
end-to-end" framing for this epic. The catalog is **continuous**, never "done" — there is no
finish line at which the node library is considered complete. Explicitly out of scope for
this epic: DL nodes (roadmap Epic 10), GenAI nodes (roadmap Epic 11), and credentialed/remote
connectors (roadmap Epic 9 — only local-file loaders are in scope here).

**2. Escape-hatch (raw-Python / raw-SQL) node — decided now, deferred.** We will **not** ship
an escape-hatch node in this epic. An arbitrary code string breaks [ADR 0001](./0001-graph-is-single-source-of-truth.md)'s
"no arbitrary code, graph is the source of truth" invariant, and it cannot uphold the
[ADR 0002](./0002-execute-the-ir-not-the-string.md) codegen↔execute equivalence gate: an
opaque string can be neither statically validated nor proven equivalent between the two pure
functions. The local Jupyter trust model is the only context that would make such a node
safe, but safety in one deployment tier does not justify building off the happy path to a
functioning app. We revisit this only when a design partner actually hits the ceiling that a
fixed node catalog cannot express.

**3. Catalog-as-data is the fourth SDK→canvas contract artifact.** Alongside the IR schema,
the generated-code string, and the rules-as-data artifact ([ADR 0012](./0012-rules-as-portable-data.md)),
the node catalog is exported as **data, not code**, so the canvas's palette and schema-driven
config panels need no Python present (ADR 0013, ADR 0014) — the same boundary discipline that
governs every other SDK↔canvas crossing. It carries **its own version**
(`catalog_version`), decoupled from `Graph.schema_version`, for the same reason ADR 0012
decoupled the rules artifact's version: the catalog grows on a different cadence than the
wire format, and coupling the two would force spurious IR migrations every time a node's
`label` or `help` text changes. A palette entry has the shape:

```json
{
  "type": "data.load_csv",
  "version": 2,
  "family": "data",
  "label": "Load CSV",
  "category": "Ingest",
  "description": "Load a CSV file into a pandas DataFrame.",
  "paradigm": "functional",
  "ports": [{ "name": "frame", "direction": "out", "data_type": "DataFrame" }],
  "params": [
    {
      "name": "path",
      "type_token": "str",
      "default": null,
      "required": true,
      "label": "CSV path",
      "help": "Path to the CSV file to load.",
      "hints": { "widget": "file" }
    }
  ]
}
```

`type`, `version`, and `family` already exist on `NodeDefinition` (ADR 0005); `label`,
`category`, `description`, and the per-param `label`/`help`/`hints` are the palette-facing
metadata Story 2 backfills onto the contract. The full artifact shape, ordering rules, and
producer contract are specified in [`docs/node-catalog-artifact.md`](../node-catalog-artifact.md).

**4. Per-node `version` discipline, restated.** We will bump a node's contract `version` on
any `codegen`/param change, exactly as the Epic 1 contract already requires — this decision
does not introduce new behavior, it **restates** the existing discipline because the catalog
artifact now makes a stale `version` externally visible. The canvas can use `version` to
detect a node-contract drift (e.g. a graph saved against an older node version) independently
of any `Graph.schema_version` migration, the same drift signal ADR 0012 gives the type rules.

## Consequences

**Positive:**

- A single data-driven palette: the canvas renders every node — old and new — from the same
  catalog artifact, with no two-tier "hardcoded UI for the first five nodes, generated UI for
  the rest" split and no per-node frontend code to write or maintain.
- The breadth policy gives Stories 3–6 an explicit, bounded scope per family instead of an
  open-ended "add more nodes" mandate, and gives reviewers a clear test for what's in vs. out.
- Deferring the escape-hatch node keeps the whole node library inside the ADR-0001/ADR-0002
  purity guarantees — every node, without exception, is codegen↔execute equivalent and
  expressible as graph data.
- A standalone `catalog_version` avoids coupling catalog growth to IR schema migrations,
  mirroring the rules-as-data precedent ([ADR 0012](./0012-rules-as-portable-data.md)) and
  keeping the migration story (Epic 14) scoped to actual wire-format changes.

**Negative / obligations:**

- Every node shipped is now **forever-maintained surface**: the catalog is continuous, so
  there is no "ship and forget" — each new node carries an ongoing equivalence-test and
  metadata-maintenance burden (Story 2's golden test, the ADR-0002 equivalence harness).
- The palette metadata (`label`, `category`, `description`, per-param `help`/`hints`) must be
  **backfilled** onto the five existing reference nodes so they render identically to newly
  added ones — Story 2 work, not optional polish.
- The catalog artifact and its golden test must be regenerated whenever a node's metadata or
  `version` changes; a stale artifact would silently desync the palette from the registry.

**Deferred:**

- The raw-Python / raw-SQL escape-hatch node — revisit only when a design partner's pipeline
  cannot be expressed by the fixed catalog.
- DL nodes (roadmap Epic 10), GenAI nodes (roadmap Epic 11), and credentialed/remote
  connectors beyond local-file loaders (roadmap Epic 9).
- The catalog metadata fields, the `ef.export_catalog()` builder, and the golden test on its
  output — Story 2, specified in [`docs/node-catalog-artifact.md`](../node-catalog-artifact.md).
- The actual per-family node additions (Stories 3–6) and the end-to-end acceptance pipeline
  (Story 7), which build on the breadth policy fixed here.
