# Emergent Flow

### The Visual Architecture Platform for Data Science, Analytics & Machine Learning

[![CI](https://github.com/proflandrigan/emergent-flow/actions/workflows/ci.yml/badge.svg)](https://github.com/proflandrigan/emergent-flow/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue)

Emergent Flow is an **infinite-canvas** visual development platform that unifies the
fragmented data ecosystem. It bridges the divide between low-code/no-code visual tools
(which lack flexibility and lock users into proprietary environments) and code-first
environments (which are linear, complex, and prone to technical friction).

Through a **Figma-like multiplayer whiteboard interface**, Emergent Flow lets you visually
architect entire data lifecycles — from raw ETL and classical hypothesis testing, to
AutoML, custom deep-learning architectures, and generative-AI multi-agent orchestration.
Crucially, the visual canvas maps **1:1** with an underlying, optimized open-source Python
SDK: every drag-and-drop connection compiles to beautiful, production-grade, human-readable
Python — eliminating vendor lock-in and preserving true developer freedom.

> **Status:** Phases 1–2 are implemented and CI-tested; Phase 3 is partially built. Done: the
> graph IR with its node contract/registry and type-validated connections (Epics 1, 3); the
> `ef.compile_to_code` / `ef.execute` codegen engine, including the declarative `nn.Module`
> seam (Epic 2); a broad node library spanning data/clean/stats/viz, dedicated per-family
> statistical modeling nodes (linear regression, GLM, GAM, mixed models, Bayesian), feature
> transformation nodes (scaling, encoding, discretization, feature generation), a
> time-series family with forecasting (ARIMA, exponential smoothing, seasonal decomposition)
> and feature transforms (EWMA, lag features, rolling/time-weighted aggregates), a full
> scikit-learn adapter (Epic 8), SHAP-based model explainability with diagnostic plots
> (ADR 0020), custom-code nodes for user-defined Python transforms, data-warehouse
> connectors — DuckDB, Postgres, BigQuery, Redshift (Epic 13) — and LLM nodes behind an
> injected, replayable client seam plus a Prompt Lab for eval/labeling (Epic 9); a text
> embedding family (`ef.embed`) dispatching to an API provider or a local
> sentence-transformers model; a recommender-systems family (`ef.recommend`, Epic 15,
> ADR 0021) spanning baselines, content-based and collaborative filtering, and deep
> recommenders (NCF, two-tower) over sparse interaction matrices, with ranking-aware
> evaluation metrics (precision/recall/NDCG/MAP@k, coverage, diversity); the `ui/`
> canvas (React Flow + Zustand) with CodeMirror 6 code editing, column-aware and
> curated per-algorithm parameter widgets, expandable inspector panels, and markdown notes
> for graph annotation; a bundled local FastAPI server (`emergentflow serve`) with streaming
> execution, DAG-aware incremental caching, and visual results (Epics 5–7); a collaboration
> layer (`emergentflow/collab/`) with an in-app agent chat panel, slash-command-activated
> review personas (data modeller, data scientist, researcher, ML engineer), a one-shot
> persona consult mode, and multi-backend agent adapters (Claude, Gemini, Codex,
> OpenCode) letting an AI agent propose graph edits as reviewable `GraphMutation`s alongside a
> human on the same canvas (Epic 14); and a unified connection manager for warehouse, LLM,
> and agent profiles. Still stubs: full multi-step agentic orchestration / LangGraph codegen
> (Epic 10), RAG (Epic 11), and real-time multiplayer. See
> [`epics/README.md`](./epics/README.md) for the epic-by-epic delivery status, the
> [Technical Roadmap](./planning_docs/technical_roadmap.md) for the engineering
> decomposition, and the [Product Proposal](./planning_docs/proposal.md) for the vision.

---

## Installation

```bash
pip install emergentflow[server]  # SDK + server + bundled canvas
emergentflow serve                # opens localhost:8765 in your browser
```

A bare `pip install emergentflow` installs the SDK for programmatic use (notebooks, scripts,
CI). The `[server]` extra adds FastAPI/Uvicorn so `emergentflow serve` (alias `emergentflow lab`)
can boot the local canvas. Optional extras for specific node families:

```bash
pip install emergentflow[all]       # everything — server + all optional extras
pip install emergentflow[llm]       # LiteLLM gateway for LLM nodes
pip install emergentflow[explain]   # SHAP-based model explainability
pip install emergentflow[embed]     # local sentence-transformers text embeddings
pip install emergentflow[recommend] # implicit-feedback recommenders (ALS/BPR)
pip install emergentflow[bayes]     # Bayesian modeling (PyMC/Bambi/ArviZ)
pip install emergentflow[bigquery]  # BigQuery warehouse adapter
pip install emergentflow[postgres]  # Postgres warehouse adapter
pip install emergentflow[redshift]  # Redshift warehouse adapter
pip install emergentflow[mcp]       # MCP tool wrapper for agent collaboration
```

Combine extras as needed: `pip install emergentflow[server,llm,explain]`, or use
`pip install emergentflow[all]` to get everything in one shot.

---

## Why Emergent Flow

Traditional data science happens in linear, isolated environments like Jupyter notebooks,
which obscure data lineage, make collaboration difficult, and hide the structure of complex
pipelines. Emergent Flow brings the design paradigm of Figma and Miro to the DE / DS / ML / GenAI
stack:

- **Complete lifecycle visibility** — trace data lineage transparently from a raw SQL
  database, through feature transformations, and into deep-learning tensors or LLM prompts.
- **Glass-box code generation** — clicking any node or pipeline path reveals clean,
  PEP8-compliant, runnable Python that can be exported straight to Git.
- **Frictionless AI evolution** — the architecture grows naturally from structured data
  processing to deep-learning execution and multi-agent generative-AI routing, all on the
  same canvas.

```
[ Data Source ] ──> [ Data Prep / Impute ] ──> [ Custom DL Layer ] ──> [ Agent Orchestrator ]
       │                                              │                        │
       └──> [ Classical Statistics ]                  └──> [ Evaluator ]       └──> [ API / App ]
```

---

## Architecture

Emergent Flow ships as **one repository and one bundled `pip install emergentflow[server]`** —
the JupyterLab model: the Python data-science engine *and* a local web canvas in a single
install, launched with `emergentflow serve` (alias `emergentflow lab`). A bare
`pip install emergentflow` gives the SDK for programmatic use; the `[server]` extra adds
FastAPI/Uvicorn for the canvas. The canvas and the SDK are separate toolchains that couple
**only** through published contract artifacts (the IR JSON Schema, the node catalog, the
`GraphMutation`/session-event schemas, and the connection-validation rules-as-data) — the UI
never imports Python. See [ADR 0013](./docs/adr/0013-single-repo-bundled-ui-topology.md).

```
    pip install emergentflow[server]  →  emergentflow serve  (alias: emergentflow lab)
┌──────────────────────────────────────────────────────────┐
│   ui/  —  CANVAS (React Flow / @xyflow, Zustand, Vite)    │  bundled into the wheel
│         talks only via IR schema · codegen · rules-data  │  (never imports emergentflow)
│         · catalog · mutation/session-event schemas        │
└────────────────────────────┬─────────────────────────────┘
                             │ localhost REST + SSE  (no shared import)
                             ▼
┌──────────────────────────────────────────────────────────┐
│   emergentflow/server/  —  LOCAL FastAPI/Uvicorn server  │  calls ef.* in-process
│         streaming execute · DAG cache · sessions/collab   │  (no Celery / Redis / sandbox)
└────────────────────────────┬─────────────────────────────┘
                             │ (pure functions over one IR)
                             ▼
┌──────────────────────────────────────────────────────────┐
│   emergentflow/  —  CORE PYTHON SDK & EXECUTION          │
│  Pandas | Statsmodels | Scikit-Learn | Plotly | DuckDB    │
│  SHAP | SQLAlchemy/BigQuery/Redshift | LiteLLM | PyTorch  │
└──────────────────────────────────────────────────────────┘
```

> **The happy path is local and in-process** ([§A6 of the roadmap](./planning_docs/technical_roadmap.md)).
> The bundled package is a single-user, local-first app — no Celery, no Redis, no sandbox, no
> multi-tenancy. The enterprise scale-out (distributed/sandboxed execution, Redis +
> object-store caching, auth, multiplayer) is **deferred to a future gated hosted product**
> (the dbt-Cloud to this dbt-core), not the bundled install.

### Core design principles

These cross-cutting decisions shape nearly every part of the system. Each is recorded as a
formal Architecture Decision Record in [`docs/adr/`](./docs/adr/) and derives from
[§A of the roadmap](./planning_docs/technical_roadmap.md):

1. **The graph is the single source of truth; code is a compiled artifact.** The serialized
   graph (the intermediate representation, or *IR*) is canonical. Python is a one-way build
   output, not a co-equal representation requiring bidirectional sync.
2. **Execute the IR, not the generated string.** Production interprets the IR directly by
   calling SDK functions; the generated Python is for display and export only. Equivalence
   between `compile_to_code(ir)` and `execute(ir)` is enforced as a hard invariant in CI.
3. **The SDK supports two paradigms.** A *functional pipeline* (DE / stats / classical ML /
   reporting) and a *declarative module/graph definition* (PyTorch architectures, LangGraph
   agent graphs) are first-class from day one.
4. **Storage is tiered (hosted tier).** On the bundled happy path the cache is a simple
   in-memory + on-disk store. The tiered design — Redis for cache metadata/hashes/small
   results, a disk/object store for large artifacts via Arrow / Parquet / safetensors — is a
   *hosted-product* concern (see [ADR 0013](./docs/adr/0013-single-repo-bundled-ui-topology.md)
   and §A6 of the roadmap), not something the local install needs.
5. **Non-deterministic, credentialed I/O is an injected client, never inline.** LLM calls
   (ADR 0017) and data-warehouse queries (ADR 0018) both route through a client object
   `execute`/the compiled entry point receives as a parameter — never a call made directly
   inside `codegen`/`execute` — so a `ReplayClient` keeps the ADR-0002 equivalence gate
   value-exact and offline, and the IR itself stays free of live connections or credentials.
6. **Collaboration state lives beside the graph, never on it** (ADR 0019). Agent proposals,
   review threads, and gates are separate models in `emergentflow/collab/`; the `Graph` IR
   schema is untouched, so the product works identically with or without agents attached.

See the [Architecture Decision Records](./docs/adr/) for the full context, decision, and
consequences of each: [ADR 0001](./docs/adr/0001-graph-is-single-source-of-truth.md),
[ADR 0002](./docs/adr/0002-execute-the-ir-not-the-string.md),
[ADR 0003](./docs/adr/0003-sdk-supports-two-paradigms.md),
[ADR 0004](./docs/adr/0004-storage-tiering.md),
[ADR 0005](./docs/adr/0005-node-definition-contract.md),
[ADR 0006](./docs/adr/0006-node-registry-and-plugin-discovery.md),
[ADR 0007](./docs/adr/0007-open-core-licensing-boundary.md),
[ADR 0008](./docs/adr/0008-codegen-templating-vs-ast.md),
[ADR 0009](./docs/adr/0009-codegen-binding-context.md),
[ADR 0010](./docs/adr/0010-codegen-package-placement.md),
[ADR 0011](./docs/adr/0011-type-model-and-compatibility.md),
[ADR 0012](./docs/adr/0012-rules-as-portable-data.md),
[ADR 0013](./docs/adr/0013-single-repo-bundled-ui-topology.md),
[ADR 0014](./docs/adr/0014-frontend-canvas-architecture.md),
[ADR 0015](./docs/adr/0015-node-catalog-and-export.md),
[ADR 0016](./docs/adr/0016-sklearn-estimator-adapter.md),
[ADR 0017](./docs/adr/0017-llm-nodes-injected-effectful-client.md),
[ADR 0018](./docs/adr/0018-data-source-connector-seam.md),
[ADR 0019](./docs/adr/0019-graph-sessions-and-agent-collaboration.md),
[ADR 0020](./docs/adr/0020-model-explainability-family.md),
[ADR 0021](./docs/adr/0021-recommender-systems-architecture.md).

### Example of generated code

The visual builder compiles structured SDK objects rather than arbitrary code blocks, so the
output stays clean and maintainable:

```python
import emergentflow as ef

# 1. Data ingestion & imputation
df = ef.data.load_csv("customer_churn.csv")
df_clean = ef.clean.impute_missing(df, columns=["age", "income"], strategy="median")

# 2. Statistical validation
stat_results = ef.stats.anova(df_clean, dv="churn_risk", between="segment")

# 3. Model architecture & pipeline training
model, metrics = ef.ml.train_classifier(
    data=df_clean,
    target="churn_risk",
    model_type="random_forest",
    optimize_for="f1",
)

# 4. Export artifacts
ef.reports.generate_html_summary(model, metrics, output_path="churn_report.html")
```

The same `ef.compile_to_code` entry point dispatches on paradigm: **declarative**
`nn.Module` graphs compile through a `libcst`-based generator to idiomatic PyTorch class
definitions (an `__init__` of layers plus a `forward` chain) rather than a flat script.
See the [Declarative Codegen Seam](./docs/codegen-declarative.md) for the worked example.

---

## Technology Stack

| Layer | Technologies |
| :--- | :--- |
| **Canvas (`ui/` tree, bundled)** | React + `@xyflow/react` (React Flow), Zustand, CodeMirror 6, Vite, TypeScript |
| **Local server (`emergentflow/server/`)** | FastAPI + Uvicorn (optional `[server]` extra) — REST, SSE streaming execution, session/collab routes, connection management, in-process `ef.*` |
| **Collaboration (`emergentflow/collab/`)** | `GraphMutation` proposals, sessions, review threads, gates, slash-command-activated review personas (data modeller, data scientist, researcher, ML engineer) plus a one-shot persona consult mode, in-app agent chat, multi-backend agent adapters (Claude, Gemini, Codex, OpenCode); optional MCP tool wrapper (`[mcp]` extra, FastMCP) — ADR 0019 |
| **Backend engine (hosted tier)** | Celery, Redis — *deferred to the hosted product (ADR 0013 / §A6)* |
| **Data wrangling** | Pandas, PyArrow (Parquet) |
| **Feature transforms (`emergentflow/nodes/examples/`)** | Scaling, categorical encoding, discretization, polynomial/interaction feature generation — all via scikit-learn |
| **Data warehouses (`emergentflow/data/warehouse/`)** | DuckDB (in-process, credential-free), Postgres (SQLAlchemy + psycopg, `[postgres]`), BigQuery (`[bigquery]`), Redshift (`[redshift]`); sqlglot for dialect SQL — ADR 0018 |
| **Statistics** | Statsmodels, SciPy; dedicated per-family nodes (linear regression, GLM, GAM, mixed models); optional Bayesian family via PyMC/Bambi/ArviZ (`[bayes]`) |
| **Time series (`emergentflow/timeseries/`)** | Statsmodels-backed forecasting (ARIMA/SARIMAX, Holt-Winters ETS, seasonal decomposition) and pandas-backed feature transforms (EWMA, lag features, rolling/time-weighted aggregates) |
| **Machine learning** | Scikit-Learn |
| **Model explainability (`emergentflow/explain/`)** | SHAP-based feature attribution, error tables, diagnostic plots (residuals, calibration, ROC/PR, predicted-vs-actual) — optional `[explain]` extra for SHAP; diagnostic plots need no extra deps (ADR 0020) |
| **Recommender systems (`emergentflow/recommend/`)** | Baselines, content-based (TF-IDF, feature/embedding KNN), and sklearn-backed collaborative filtering (SVD/NMF) on hard deps; `implicit` (`[recommend]` extra) for ALS/BPR; PyTorch for deep recommenders (NCF, two-tower). Sparse `InteractionMatrix` representation; ranking metrics (precision/recall/NDCG/MAP@k, coverage, diversity) — ADR 0021 |
| **Text embeddings (`emergentflow/embed/`)** | `ef.embed.text` dispatches to an API provider via the injected LLM client seam, or a local `sentence-transformers` model (`[embed]` extra) |
| **Deep learning** | PyTorch (declarative `nn.Module` codegen seam; also backs deep recommenders — not a runtime dependency) |
| **Visualization** | Plotly |
| **Custom code (`emergentflow/script/`)** | User-defined `def transform(value)` Python nodes compiled and executed in-process |
| **GenAI / LLM (`emergentflow/llm/`, `emergentflow/eval/`)** | LiteLLM gateway behind an injected client seam (`[llm]` extra), replay/record fixtures for offline CI, Prompt Lab eval/label/export — ADR 0017. Multi-agent orchestration (LangGraph) is planned, not yet implemented (Epic 10). |
| **Diagnostics** | YData-Profiling |

---

## Roadmap

Development is structured into three iterative phases. The full epic-level decomposition
lives in [`planning_docs/technical_roadmap.md`](./planning_docs/technical_roadmap.md).

### Phase 1 — Foundation (SDK + static canvas) — **done**
The open-source Python SDK and graph IR, the codegen engine, the infinite-canvas frontend,
a broad node library (data/clean/stats/viz/ml, full scikit-learn adapter), structural +
nominal type validation, and save/load + export. **Delivered:** a canvas that maps a node
graph to flawless, downloadable Python, plus a declarative `nn.Module` codegen seam for
PyTorch architectures.

### Phase 2 — Living Bridge (local reactive backend, bundled) — **done**
A **local** FastAPI/Uvicorn server bundled in the package (`emergentflow serve`) that runs
`ef.execute(ir)` **in-process**, streams progress over SSE, DAG-aware incrementally caches
results on disk, and renders results back into the canvas per node. The enterprise
build-out — Celery/sandboxed/distributed execution, Redis + object-store caching,
auth/multi-tenancy/deploy — stays **deferred to the gated hosted product** (ADR 0013 / §A6).

### Phase 3 — Frontier (Deep Learning, GenAI & agents) — **in progress**
Delivered so far: LLM/Prompt Lab nodes with an injected, replayable client seam and an
eval/label/export workflow (Epic 9); a text embedding family (`ef.embed`) over API providers
or a local sentence-transformers model; data-warehouse connectors as a second injected-client
seam (Epic 13); agent collaboration with an in-app chat panel, slash-command-activated review
personas (data modeller, data scientist, researcher, ML engineer) plus a one-shot persona
consult mode, and multi-backend agent adapters (Claude, Gemini, Codex, OpenCode) — an AI
agent proposes `GraphMutation`s that a human reviews on the same canvas via ghost-diffs,
gates, and review threads (Epic 14, ADR 0019); dedicated per-family statistical modeling
nodes (linear regression, GLM, GAM, mixed models, Bayesian); feature transformation nodes
(scaling, encoding, discretization, feature generation); a time-series family with
forecasting (ARIMA, exponential smoothing, seasonal decomposition) and feature transforms
(EWMA, lag features, rolling/time-weighted aggregates); SHAP-based model explainability with
diagnostic plots (ADR 0020); a recommender-systems family (`ef.recommend`, Epic 15,
ADR 0021) spanning baselines, content-based and collaborative filtering, and deep
recommenders over sparse interaction matrices, with ranking-aware evaluation metrics;
custom-code nodes for user-defined Python transforms; markdown notes for graph annotation;
a unified connection manager for warehouse, LLM, and agent profiles; and canvas UX
improvements including CodeMirror 6 code editing, column-aware and curated per-algorithm
parameter widgets, and expandable inspector panels. Still ahead: visual PyTorch composition
with real-time tensor-shape resolution, multi-step agentic orchestration / LangGraph codegen
(Epic 10), RAG (Epic 11), and real-time multiplayer editing, with the IR designed
CRDT-ready from the start.

---

## Repository Layout

```
emergent-flow/
├── emergentflow/               # Python SDK source
│   ├── ir/                   # Graph intermediate representation (schema, serialization, migrations)
│   ├── nodes/                # Node contract, registry, catalog export, and reference examples
│   ├── codegen/              # Whole-graph compiler + reference executor (compile_to_code / execute)
│   ├── types/                # Type catalog, compatibility rules, rules-as-data artifact
│   ├── data/                 # ef.data (+ data/warehouse/: DuckDB/Postgres/BigQuery/Redshift adapters, query builder)
│   ├── clean, stats, ml, viz, reports/   # Reference node-family SDK wrappers
│   ├── timeseries/            # ef.timeseries: forecasting (ARIMA/ETS/decomposition) + feature transforms
│   ├── explain/              # SHAP-based model explainability and diagnostic plots (ADR 0020, [explain] extra)
│   ├── recommend/             # ef.recommend: baselines, content-based/collaborative/deep recommenders, InteractionMatrix, metrics (Epic 15, ADR 0021, [recommend] extra)
│   ├── embed/                  # ef.embed.text: API or local sentence-transformers text embeddings ([embed] extra)
│   ├── script/               # Custom-code node: user-defined Python transform functions
│   ├── connections/          # Unified connection-profile store (warehouse + LLM + agent, TOML-backed)
│   ├── llm/                   # Injected LLM client seam (Gateway/Replay), prompt templating, budget/pricing
│   ├── eval/                  # Prompt Lab eval run / label / export
│   ├── collab/                # Agent collaboration: sessions, chat, personas/consult, agent adapters, GraphMutation, gates, review, MCP (Epic 14)
│   ├── server/                # Local FastAPI/Uvicorn server (ef.* in-process) — `emergentflow serve`
│   ├── clients.py             # Injected-client bundle threaded through execute()/compiled main()
│   ├── cli.py                 # `emergentflow` console entry point (serve / lab)
│   └── api.py                 # @public_op decorator + inspectable-return contract
├── ui/                        # TypeScript/React canvas (Vite), bundled into the wheel — never imports emergentflow
│   └── src/                   # canvas, palette, inspector, exec, session (chat/collab UX), promptlab, connections, store
├── agents/                    # Persona files for AI agents collaborating on a graph over HTTP (Epic 14):
│                              #   the generic collaborator protocol + domain personas (data modeller,
│                              #   data scientist, researcher, ML engineer), slash-command-activated in chat
├── docs/
│   ├── adr/                  # Architecture Decision Records (foundational decisions)
│   ├── runbook.md            # How to install, launch, and use the app (UI, API, CLI)
│   ├── acceptance-demo.md    # End-to-end worked pipeline
│   ├── agent-integration.md, bring-your-own-key.md  # Agent collaboration protocol + LLM credentials
│   ├── node-contract-spec.md, node-registry.md, node-catalog-artifact.md, authoring-a-node.md
│   ├── codegen-compiler.md, codegen-executor.md, codegen-traversal.md, codegen-declarative.md, how-codegen-works.md
│   ├── ir-spec.md, ir-serialization-format.md, ir-migrations.md, result-payload-contract.md
│   ├── type-system-spec.md, connection-validation.md
│   ├── package-layout.md, public-api-conventions.md, sdk-design-philosophy.md, ui-server-boundary.md
│   ├── versioning-and-releases.md, licensing-and-dependencies.md, open-core-boundary.md
│   └── stats-viz-design.md
├── epics/                     # Epic 1–15 story-level decomposition (README.md maps repo ↔ roadmap numbering)
├── examples/                  # Ready-made IR graphs + acceptance demos (sklearn, stats/viz, data connectors, agent collab)
├── planning_docs/
│   ├── proposal.md            # Product vision & market mapping
│   └── technical_roadmap.md   # Engineering decomposition (epics, phases, decisions)
├── schema/                    # Exported JSON Schemas (diagnostics, connection-validation rules)
├── scripts/                   # export_ui_contracts.py, check_ui_boundary.py (CI-enforced UI/SDK boundary)
├── .github/workflows/         # CI (Python lint/type/test, UI build/test, warehouse driver integration) and release pipelines
├── pyproject.toml             # Packaging, dependencies, tool config (ruff, mypy, pytest)
├── uv.lock                    # Pinned, reproducible dependency lockfile
└── README.md
```

---

## Documentation

- [Runbook](./docs/runbook.md) — install, launch (`emergentflow serve`), use the canvas, drive
  the REST/SSE API directly, develop `ui/`, and run the full local CI gate set.
- [The Acceptance Demo](./docs/acceptance-demo.md) — the end-to-end pipeline that shows what
  the app can do today.
- [Agent Integration](./docs/agent-integration.md) and the
  [`agents/emergent-flow-collaborator.md`](./agents/emergent-flow-collaborator.md) persona —
  how an AI agent (Claude Code, Shards, or any HTTP client) joins a session and proposes
  `GraphMutation`s alongside a human, per [ADR 0019](./docs/adr/0019-graph-sessions-and-agent-collaboration.md).
- [Bring Your Own Key](./docs/bring-your-own-key.md) — how LLM/warehouse credentials are
  supplied (env-var names only; never embedded in the IR — ADR 0017/0018).
- [Package Layout & Namespace Conventions](./docs/package-layout.md) — the `emergentflow` / `ef`
  package structure and namespaces.
- [Public API Conventions](./docs/public-api-conventions.md) — naming, signatures, and the
  serializable + inspectable return-object contract every wrapper must meet.
- [SDK Design Philosophy](./docs/sdk-design-philosophy.md) — the thin / deterministic / pure
  rules and the `@ef.public_op` runtime check that enforces them.
- [Codegen Engine](./docs/codegen-compiler.md) — the whole-graph `compile_to_code` compiler
  and reference `execute` interpreter, plus the
  [declarative `nn.Module` seam](./docs/codegen-declarative.md),
  [traversal](./docs/codegen-traversal.md), and [executor](./docs/codegen-executor.md) internals.
- [How Codegen Works](./docs/how-codegen-works.md) — an overview of the codegen pipeline,
  the two paradigms, and the golden / equivalence quality gates that back the
  "what you see runs" promise.
- [The IR Spec](./docs/ir-spec.md), [Serialization Format](./docs/ir-serialization-format.md),
  and [Migrations](./docs/ir-migrations.md) — the graph intermediate representation and its
  wire-format evolution policy.
- [Result Payload Contract](./docs/result-payload-contract.md) — the schema every node's
  `execute` output and the server's `/execute` response conform to.
- [The Type System & Connection Validation](./docs/type-system-spec.md) — the nominal type
  model, compatibility + cardinality rules, whole-graph inference, `ef.validate`/`Diagnostics`,
  the strictness policy, and the shared codegen/execute gate.
- [Connection Validation: Rules as a Portable Artifact](./docs/connection-validation.md) — the
  type rules + `Diagnostics` schema shipped to the frontend canvas as data, and the
  frontend-vs-SDK authority model.
- [UI ↔ Server Boundary](./docs/ui-server-boundary.md) — the contract artifacts (`ir.schema.json`,
  the node catalog, mutation/session-event schemas) that are the *only* thing crossing the
  `ui/ ↔ emergentflow/` wall, and the CI check that enforces it.
- [Node Catalog Artifact](./docs/node-catalog-artifact.md) — how the palette/config-panel
  catalog is exported as data for the canvas.
- [Versioning & Releases](./docs/versioning-and-releases.md) — Semantic Versioning policy and
  the tag-driven release process.
- [Architecture Decision Records](./docs/adr/) — the foundational `§A` decisions.
- [How to Author a Node](./docs/authoring-a-node.md) — the node-definition contract in practice.

The SDK uses [`uv`](https://docs.astral.sh/uv/) for reproducible installs (`uv sync`), `ruff`
for lint + format, and `mypy` for type-checking; the canvas uses `npm`, `eslint`, `tsc`, and
`vitest`. CI runs the Python gates on 3.11/3.12, a separate `ui/` job (lint, typecheck, build,
test), and a driver-integration job against a live Postgres for the warehouse adapters.

---

## License

The Emergent Flow SDK in this repository is licensed under the
[Apache License 2.0](./LICENSE). Emergent Flow follows an **open-core** model: the
Python SDK is open source, while the collaborative platform (visual canvas,
real-time multiplayer, hosting, and enterprise features) is a separate
proprietary product. See [Open-Core Boundary](./docs/open-core-boundary.md) for
what is SDK vs. platform-only, and
[Dependency Licensing & Compatibility](./docs/licensing-and-dependencies.md) for
the dependency-license policy.

Contributions are accepted under a license-grant CLA — see
[CONTRIBUTING.md](./CONTRIBUTING.md).
