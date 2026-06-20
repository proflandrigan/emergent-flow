# Epics — repo ↔ roadmap numbering

This directory tracks the epics **delivered in this repo** (`colony-mind`, the Python SDK +
graph IR + codegen). The files here are numbered by **delivery order in this repo**.

The [technical roadmap](../planning_docs/technical_roadmap.md) numbers epics **globally across
all three repos** of the product (`colony-mind`, `colony-mind-canvas`, `colony-mind-server` —
see roadmap §A5 and §B1). The two numbering schemes therefore **drift**: this repo does not
deliver every roadmap epic, so repo-Epic-N is not generally roadmap-Epic-N.

> **The collision to watch for:** "Epic 3" is overloaded. In **this repo** it means
> *Type-Safe Graph & Connection Validation* (Python). In the **roadmap** it means the
> *Frontend Canvas Engine* (React/TypeScript), which is **not delivered here** — it ships in
> the separate `colony-mind-canvas` repo. Always say "repo Epic 3" or "roadmap Epic 3."

## Mapping

| This repo | File | Roadmap | Roadmap title | Track / repo |
| :-- | :-- | :-- | :-- | :-- |
| **Epic 1** | [`epic-1-core-sdk-and-ir.md`](./epic-1-core-sdk-and-ir.md) | Epic 1 | Core SDK & Graph IR | Python SDK — `colony-mind` |
| **Epic 2** | [`epic-2-code-generation-engine.md`](./epic-2-code-generation-engine.md) | Epic 2 | Code Generation Engine | Python SDK — `colony-mind` |
| **Epic 3** | [`epic-3-type-safe-graph-and-validation.md`](./epic-3-type-safe-graph-and-validation.md) | **Epic 5** | Type-Safe Graph & Connection Validation | Python SDK owns the rules; `colony-mind-canvas` consumes them |

### Roadmap epics not delivered in this repo

These are referenced by the roadmap (and by cross-references inside the epic files) but live in
other repos:

- **Roadmap Epic 3 — Frontend Canvas Engine** → `colony-mind-canvas` (React Flow / TS).
- **Roadmap Epic 4 — Node Library & Configuration UX** → *split*: config-panel UI in
  `colony-mind-canvas`, node catalog/defaults in this repo (folded into the SDK node work).
- **Roadmap Epics 6–15** → `colony-mind-server` and/or `colony-mind-canvas`.

## Reading cross-references

Inside the epic files, prose cross-references like "Blocks: Epic 5 (typing)" or "Epic 10
(tensor dimensions)" use **roadmap numbers** — they point at the global plan, not at files in
this directory. Only the **filenames and the `# Epic N` headings** use repo-delivery numbers.
When in doubt, this table is the source of truth.
