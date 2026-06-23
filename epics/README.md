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

> **The collision to watch for (now a mirror).** Epic numbers are overloaded across the two
> schemes, so **always qualify "repo Epic N" vs "roadmap Epic N".** The two that cross over:
> **repo Epic 3 = roadmap Epic 5** (Type-Safe Graph, Python in `colonymind/`) and, its mirror,
> **repo Epic 5 = roadmap Epic 3** (Frontend Canvas, React/TS in `ui/`). When in doubt, the
> mapping table below is the source of truth.

## Mapping

| This repo | File | Roadmap | Roadmap title | Track / repo |
| :-- | :-- | :-- | :-- | :-- |
| **Epic 1** | [`epic-1-core-sdk-and-ir.md`](./epic-1-core-sdk-and-ir.md) | Epic 1 | Core SDK & Graph IR | Python SDK — `colonymind/` |
| **Epic 2** | [`epic-2-code-generation-engine.md`](./epic-2-code-generation-engine.md) | Epic 2 | Code Generation Engine | Python SDK — `colonymind/` |
| **Epic 3** | [`epic-3-type-safe-graph-and-validation.md`](./epic-3-type-safe-graph-and-validation.md) | **Epic 5** | Type-Safe Graph & Connection Validation | Python SDK (`colonymind/`) owns the rules; `ui/` consumes them |
| **Epic 4** | [`epic-4-local-server.md`](./epic-4-local-server.md) | **Epic 6** (happy-path sliver) | Local Execution Server (bundled, in-process) | Local server — `colonymind/server/` |
| **Epic 5** | [`epic-5-frontend-canvas.md`](./epic-5-frontend-canvas.md) | **Epic 3** | Frontend Canvas Engine | Frontend — `ui/` |

> **Delivery vs. roadmap order.** Repo Epics 4 (local server) and 5 (canvas) are *planned*
> (Epic 4's v0 server has shipped; Epic 5 is not started). The server was front-loaded ahead of
> the canvas — and ahead of its own roadmap position (Epic 6) — because the SDK is proven and a
> thin in-process server over it is the shortest path to a runnable app (roadmap §A6 / §E,
> [ADR 0013](../docs/adr/0013-single-repo-bundled-ui-topology.md)).

### Roadmap epics not yet decomposed in this repo

These are referenced by the roadmap but do not yet have a story-level epic file here — they live
in the `ui/`, `colonymind/server/`, or SDK trees (same repo, per ADR 0013) and gain a file when
picked up:

- **Roadmap Epic 4 — Node Library & Configuration UX** → *split*: config-panel UI in `ui/`,
  node catalog/defaults in the SDK (`colonymind/`) tree (folded into the SDK node work).
- **Roadmap Epics 7–15** → the `colonymind/server/` and/or `ui/` trees (with the heavyweight
  hosted pieces deferred to the gated hosted product per §A6). The happy-path sliver of roadmap
  **Epic 6** is already decomposed as **repo Epic 4** above.

## Reading cross-references

Inside the epic files, prose cross-references like "Blocks: Epic 5 (typing)" or "Epic 10
(tensor dimensions)" use **roadmap numbers** — they point at the global plan, not at files in
this directory. Only the **filenames and the `# Epic N` headings** use repo-delivery numbers.
When in doubt, this table is the source of truth.
