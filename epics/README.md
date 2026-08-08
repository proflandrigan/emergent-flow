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
| **Epic 8** | [`epic-8-scikit-learn-support.md`](./epic-8-scikit-learn-support.md) | **Epic 4** (deep ML build-out) | Complete scikit-learn Support (Supervised & Unsupervised) | Python SDK — `emergentflow/` (estimator adapter, node archetypes, generated catalog) |
| **Epic 9** | [`epic-9-ai-engineering-playground-prompt-lab.md`](./epic-9-ai-engineering-playground-prompt-lab.md) | **Epic 11** (partial — LLM/Prompt Lab foundation) | AI Engineering Playground: Prompt Lab (LLM Foundation) | Python SDK — `emergentflow/` (LLM client seam, node families, eval/label/export) **+** `ui/` (Prompt Lab panel) |
| **Epic 10** *(stub)* | [`epic-10-agentic-flows.md`](./epic-10-agentic-flows.md) | **Epic 11** (multi-agent remainder) + **Epic 12** (partial) | Agentic Flows (Multi-Step Orchestration) | Python SDK — `emergentflow/` (agent nodes, declarative/LangGraph codegen) **+** `ui/` (message/token viz) |
| **Epic 11** *(stub)* | [`epic-11-rag.md`](./epic-11-rag.md) | **Epic 11** (RAG facet of the GenAI stack) | RAG (Retrieval-Augmented Generation) | Python SDK — `emergentflow/` (`ef.rag.*`, embedding/vector-store adapters) **+** `ui/` (retrieval inspector) |
| **Epic 12** | [`epic-12-statistics-visualization-eda.md`](./epic-12-statistics-visualization-eda.md) | **Epic 4** (deep stats/EDA build-out) + **Epic 8** (visual results) | High-Level Statistics, Visualization & Exploratory Data Analysis | Python SDK — `emergentflow/` (`ef.stats`/`ef.viz` model + chart adapters, generated chart catalog, `FittedStatsModel`/`PlotSpec` tokens) **+** `ui/` (palette/panels + Results-tab render) |
| **Epic 13** | [`epic-13-data-connectors-warehouses-sql.md`](./epic-13-data-connectors-warehouses-sql.md) | **Epic 9** (bundled/local slice) | Data Connectors, Warehouses & SQL | Python SDK — `emergentflow/` (`WarehouseClient` seam, `ef.data.query` wrapper, dialect adapters + generated connector catalog, connection-profile store, raw-SQL + visual-builder nodes) **+** `ui/` (connection manager, schema browser, visual-builder panel). Premium/managed connectors + managed secret store stay **(hosted)**. |
| **Epic 14** | [`epic-14-agent-collaboration.md`](./epic-14-agent-collaboration.md) | **Epic 12** (bundled/local slice — NL→graph agent / AI-assisted authoring) | Agent Collaboration on the Canvas | Python SDK — `emergentflow/` (`GraphMutation` + pure `apply_mutation`, `emergentflow/collab/` sessions/reviews/gates/personas, session routes + SSE) **+** `ui/` (session mode, ghost-diff proposal UX, review threads) **+** `agents/` (persona files for Shards / Claude Code). Distinct from repo Epic 10 (agents *inside* the graph as nodes); this is agents *outside* the graph as co-authors. Multi-user real-time editing + autonomous research stay deferred (**hosted** / Epic 6-gated). |
| **Epic 15** | [`epic-15-recommender-systems.md`](./epic-15-recommender-systems.md) | — | Recommender Systems | Python SDK — `emergentflow/` (`ef.recommend` family: baselines, content-based, collaborative filtering, deep recommenders; `FittedRecommender`/`InteractionMatrix` representations; recommender registry + generated catalog; evaluation metrics). Optional `[recommend]` extra for `implicit` (ALS/BPR); `torch` (already optional) for NCF/two-tower. |
| **Epic 16** | [`epic-16-data-transform-analytics-research-depth.md`](./epic-16-data-transform-analytics-research-depth.md) | — | Data Gathering, Transform, Analytics & Research Depth | Python SDK — `emergentflow/` (HTTP/cloud/spreadsheet/document ingestion behind the `requires_client` seam; reshape/derive/dedup/string/date/sample/fuzzy transform verbs in `ef.clean`; non-parametric tests + experiment/power/crosstab/dim-reduction/cohort/funnel analytics in `ef.stats`; new `emergentflow/research/` for the multi-section report builder, DAG lineage, reproducibility capture, and the data-quality gate) **+** `ui/` (Report + Lineage inspector renderers). New optional extras: `[excel]`, `[cloud]`, `[fuzzy]`, `[umap]`, `[causal]`, `[report-pdf]`, `[pii]`, `[docs]` — **no new hard deps**. RAG retrieval explicitly deferred to Epic 11. |
| **Epic 17** | [`epic-17-experiment-validity-analysis.md`](./epic-17-experiment-validity-analysis.md) | — | Experiment-Validity Static Analysis | Python SDK — `emergentflow/` (new `emergentflow/validity/` rule registry + 10 pure topology rules over leakage/temporal/skew/metric-misuse, wired into `ef.validate` via the existing `Diagnostics` channel; versioned rule-pack artifact `schema/validity-rules.json`; `ef.apply_suppressions` boundary-side filter) **+** `emergentflow/server/` (`GET /validity-rules`) **+** `ui/` (rule explanations + suppress in the problems list) **+** CLI (`emergentflow validate --strict`). No new hard deps; disambiguated from `stats.diagnostic_*` model diagnostics. |
| **Epic 18** | [`epic-18-column-level-lineage.md`](./epic-18-column-level-lineage.md) | **—** (issue #128 proposed "epic-21" as a placeholder) | Column-Level Lineage | Python SDK — `emergentflow/` (new optional `column_effect` on the node spec/contract with per-node declarations across `clean.*`/`transform.*`/`stats.*`/`data.load_*`; extended `emergentflow/research/lineage.py` with `ColumnLineageNode`/`ColumnLineageEdge`, `trace_column_lineage` + `trace_column_impact`, runtime refinement from observed schemas, an undeclared-node coverage report) **+** `emergentflow/server/` (`POST /lineage/column`) **+** `ui/` (clickable result-table columns, derivation trail in `LineagePanel`) **+** the validity epic's `target_derived_feature` rule rewritten exact. No new hard deps. |

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
