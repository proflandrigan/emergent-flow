# Epics — repo ↔ roadmap numbering

This directory tracks the epics **delivered in this repo** (`emergent-flow`, the Python SDK +
graph IR + codegen). The files here are numbered by **delivery order in this repo**.

> **⚠️ Topology superseded by [ADR 0013](../docs/adr/0013-single-repo-bundled-ui-topology.md).**
> The product is **one repo, one bundled `pip install emergentflow`**, not three repos. Wherever
> this file says `emergent-flow-canvas` or `emergent-flow-server`, read "the `ui/` and
> `emergentflow/server/` *trees* of this one repo." The numbering map and the "Epic 3 collision"
> below are unchanged; only the repo count collapsed.

The [technical roadmap](../planning_docs/technical_roadmap.md) numbers epics **globally across
the whole product** (the SDK in `emergentflow/`, the canvas in `ui/`, the local server in
`emergentflow/server/` — see roadmap §A5/§B1 as amended by ADR 0013). The two numbering schemes
**drift**: this repo's SDK tree does not deliver every roadmap epic, so repo-Epic-N is not
generally roadmap-Epic-N.

> **The collision to watch for (now a mirror).** Epic numbers are overloaded across the two
> schemes, so **always qualify "repo Epic N" vs "roadmap Epic N".** The two that cross over:
> **repo Epic 3 = roadmap Epic 5** (Type-Safe Graph, Python in `emergentflow/`) and, its mirror,
> **repo Epic 5 = roadmap Epic 3** (Frontend Canvas, React/TS in `ui/`). When in doubt, the
> mapping table below is the source of truth.

## Mapping

| This repo | File | Roadmap | Roadmap title | Track / repo |
| :-- | :-- | :-- | :-- | :-- |
| **Epic 1** | [`epic-1-core-sdk-and-ir.md`](./epic-1-core-sdk-and-ir.md) | Epic 1 | Core SDK & Graph IR | Python SDK — `emergentflow/` |
| **Epic 2** | [`epic-2-code-generation-engine.md`](./epic-2-code-generation-engine.md) | Epic 2 | Code Generation Engine | Python SDK — `emergentflow/` |
| **Epic 3** | [`epic-3-type-safe-graph-and-validation.md`](./epic-3-type-safe-graph-and-validation.md) | **Epic 5** | Type-Safe Graph & Connection Validation | Python SDK (`emergentflow/`) owns the rules; `ui/` consumes them |
| **Epic 4** | [`epic-4-local-server.md`](./epic-4-local-server.md) | **Epic 6** (happy-path sliver) | Local Execution Server (bundled, in-process) | Local server — `emergentflow/server/` |
| **Epic 5** | [`epic-5-frontend-canvas.md`](./epic-5-frontend-canvas.md) | **Epic 3** | Frontend Canvas Engine | Frontend — `ui/` |
| **Epic 6** | [`epic-6-node-library.md`](./epic-6-node-library.md) | **Epic 4** | Node Library & Configuration UX | Python SDK (`emergentflow/`) owns the catalog; `ui/` renders palette/panels |
| **Epic 7** | [`epic-7-live-iteration.md`](./epic-7-live-iteration.md) | **Epics 6 (remaining) + 7 + 8 (partial)** | Live Iteration & Visual Results | `emergentflow/server/` (FastAPI, cache) + `ui/` (streaming, Results tab) |

> **Delivery vs. roadmap order.** Repo Epics 4 (local server) and 5 (canvas) are *planned*
> (Epic 4's v0 server has shipped; Epic 5 is not started). The server was front-loaded ahead of
> the canvas — and ahead of its own roadmap position (Epic 6) — because the SDK is proven and a
> thin in-process server over it is the shortest path to a runnable app (roadmap §A6 / §E,
> [ADR 0013](../docs/adr/0013-single-repo-bundled-ui-topology.md)).

### Roadmap epics not yet decomposed in this repo

These are referenced by the roadmap but do not yet have a story-level epic file here — they live
in the `ui/`, `emergentflow/server/`, or SDK trees (same repo, per ADR 0013) and gain a file when
picked up:

- ~~**Roadmap Epic 4 — Node Library & Configuration UX**~~ → now decomposed as **repo Epic 6**
  ([`epic-6-node-library.md`](./epic-6-node-library.md)): the SDK (`emergentflow/`) tree owns the
  node catalog/defaults + the catalog-as-data export; the config-panel UI in `ui/` (repo Epic 5
  Stories 3–4) consumes it.
- **Roadmap Epics 6 (remaining) + 7 + 8 (partial)** → now decomposed as **repo Epic 7**
  ([`epic-7-live-iteration.md`](./epic-7-live-iteration.md)): FastAPI server upgrade,
  streaming progress, run granularity, DAG caching, figure/HTML payload extensions, and the
  Inspector Results tab.
- **Roadmap Epics 9–15** → the `emergentflow/server/` and/or `ui/` trees (with the heavyweight
  hosted pieces deferred to the gated hosted product per §A6).

## Reading cross-references

Inside the epic files, prose cross-references like "Blocks: Epic 5 (typing)" or "Epic 10
(tensor dimensions)" use **roadmap numbers** — they point at the global plan, not at files in
this directory. Only the **filenames and the `# Epic N` headings** use repo-delivery numbers.
When in doubt, this table is the source of truth.
