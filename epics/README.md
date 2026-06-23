# Epics — repo ↔ roadmap numbering

This directory tracks the epics **delivered in this repo** (`colony-mind`, the Python SDK +
graph IR + codegen). The files here are numbered by **delivery order in this repo**.

> **⚠️ Topology superseded by [ADR 0013](../docs/adr/0013-single-repo-bundled-ui-topology.md).**
> The product is **one repo, one bundled `pip install colonymind`**, not three repos. Wherever
> this file says `colony-mind-canvas` or `colony-mind-server`, read "the `ui/` and
> `colonymind/server/` *trees* of this one repo." The numbering map and the "Epic 3 collision"
> below are unchanged; only the repo count collapsed.

The [technical roadmap](../planning_docs/technical_roadmap.md) numbers epics **globally across
the whole product** (the SDK in `colonymind/`, the canvas in `ui/`, the local server in
`colonymind/server/` — see roadmap §A5/§B1 as amended by ADR 0013). The two numbering schemes
**drift**: this repo's SDK tree does not deliver every roadmap epic, so repo-Epic-N is not
generally roadmap-Epic-N.

> **The collision to watch for:** "Epic 3" is overloaded. In **this repo's SDK** it means
> *Type-Safe Graph & Connection Validation* (Python, in `colonymind/`). In the **roadmap** it
> means the *Frontend Canvas Engine* (React/TypeScript), which ships in the **`ui/` tree** of
> this same repo — a different toolchain, not the SDK. Always say "repo Epic 3" or
> "roadmap Epic 3."

## Mapping

| This repo | File | Roadmap | Roadmap title | Track / repo |
| :-- | :-- | :-- | :-- | :-- |
| **Epic 1** | [`epic-1-core-sdk-and-ir.md`](./epic-1-core-sdk-and-ir.md) | Epic 1 | Core SDK & Graph IR | Python SDK — `colonymind/` |
| **Epic 2** | [`epic-2-code-generation-engine.md`](./epic-2-code-generation-engine.md) | Epic 2 | Code Generation Engine | Python SDK — `colonymind/` |
| **Epic 3** | [`epic-3-type-safe-graph-and-validation.md`](./epic-3-type-safe-graph-and-validation.md) | **Epic 5** | Type-Safe Graph & Connection Validation | Python SDK (`colonymind/`) owns the rules; `ui/` consumes them |

### Roadmap epics delivered in other trees of this repo

These are referenced by the roadmap (and by cross-references inside the epic files) but live in
the `ui/` or `colonymind/server/` trees rather than the SDK (`colonymind/`) tree — same repo,
different toolchain (per ADR 0013):

- **Roadmap Epic 3 — Frontend Canvas Engine** → `ui/` tree (React Flow / TS).
- **Roadmap Epic 4 — Node Library & Configuration UX** → *split*: config-panel UI in `ui/`,
  node catalog/defaults in the SDK (`colonymind/`) tree (folded into the SDK node work).
- **Roadmap Epics 6–15** → the `colonymind/server/` and/or `ui/` trees (with the heavyweight
  hosted pieces deferred to the gated hosted product per §A6).

## Reading cross-references

Inside the epic files, prose cross-references like "Blocks: Epic 5 (typing)" or "Epic 10
(tensor dimensions)" use **roadmap numbers** — they point at the global plan, not at files in
this directory. Only the **filenames and the `# Epic N` headings** use repo-delivery numbers.
When in doubt, this table is the source of truth.
