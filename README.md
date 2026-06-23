# Colony Mind

### The Visual Architecture Platform for Data Science, Analytics & Machine Learning

[![CI](https://github.com/proflandrigan/colony-mind/actions/workflows/ci.yml/badge.svg)](https://github.com/proflandrigan/colony-mind/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue)

Colony Mind is an **infinite-canvas** visual development platform that unifies the
fragmented data ecosystem. It bridges the divide between low-code/no-code visual tools
(which lack flexibility and lock users into proprietary environments) and code-first
environments (which are linear, complex, and prone to technical friction).

Through a **Figma-like multiplayer whiteboard interface**, Colony Mind lets you visually
architect entire data lifecycles — from raw ETL and classical hypothesis testing, to
AutoML, custom deep-learning architectures, and generative-AI multi-agent orchestration.
Crucially, the visual canvas maps **1:1** with an underlying, optimized open-source Python
SDK: every drag-and-drop connection compiles to beautiful, production-grade, human-readable
Python — eliminating vendor lock-in and preserving true developer freedom.

> **Status:** Phase 1 (Foundation), in active development. The open-source Python SDK is
> taking shape: the graph IR with its node contract and registry (Epic 1) and the
> code-generation engine — the pure `cm.compile_to_code` / `cm.execute` pair over one IR,
> including the declarative `nn.Module` codegen seam (Epic 2) — are implemented and
> CI-tested. See the [Technical Roadmap](./planning_docs/technical_roadmap.md) for the
> engineering decomposition and the [Product Proposal](./planning_docs/proposal.md) for
> the vision.

---

## Why Colony Mind

Traditional data science happens in linear, isolated environments like Jupyter notebooks,
which obscure data lineage, make collaboration difficult, and hide the structure of complex
pipelines. Colony Mind brings the design paradigm of Figma and Miro to the DE / DS / ML / GenAI
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

Colony Mind is built around a modular, three-layered stack that separates presentation,
execution, and orchestration.

```
┌──────────────────────────────────────────────────────────┐
│                   FRONTEND CANVAS LAYER                   │
│        React Flow / Rete.js  |  Tailwind CSS  |  Vite     │
└────────────────────────────┬─────────────────────────────┘
                             │ (Bi-directional WebSockets / REST)
                             ▼
┌──────────────────────────────────────────────────────────┐
│                   BACKEND ENGINE LAYER                    │
│           FastAPI  |  Celery Task Queue  |  Redis         │
└────────────────────────────┬─────────────────────────────┘
                             │ (Dynamic 1:1 Code Mapping)
                             ▼
┌──────────────────────────────────────────────────────────┐
│               CORE PYTHON SDK & EXECUTION                 │
│    Pandas / Polars  |  Statsmodels  |  Scikit-Learn       │
│          PyTorch  |  LangGraph  |  YData-Profiling        │
└──────────────────────────────────────────────────────────┘
```

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
4. **Storage is tiered.** Redis holds cache metadata, execution hashes, and small results;
   large artifacts (DataFrames, tensors, models, reports) serialize to a disk/object store
   via Arrow / Parquet / safetensors.

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
[ADR 0010](./docs/adr/0010-codegen-package-placement.md).

### Example of generated code

The visual builder compiles structured SDK objects rather than arbitrary code blocks, so the
output stays clean and maintainable:

```python
import colonymind as cm

# 1. Data ingestion & imputation
df = cm.data.load_csv("customer_churn.csv")
df_clean = cm.clean.impute_missing(df, columns=["age", "income"], strategy="median")

# 2. Statistical validation
stat_results = cm.stats.anova(df_clean, dv="churn_risk", between="segment")

# 3. Model architecture & pipeline training
model, metrics = cm.ml.train_classifier(
    data=df_clean,
    target="churn_risk",
    model_type="random_forest",
    optimize_for="f1",
)

# 4. Export artifacts
cm.reports.generate_html_summary(model, metrics, output_path="churn_report.html")
```

The same `cm.compile_to_code` entry point dispatches on paradigm: **declarative**
`nn.Module` graphs compile through a `libcst`-based generator to idiomatic PyTorch class
definitions (an `__init__` of layers plus a `forward` chain) rather than a flat script.
See the [Declarative Codegen Seam](./docs/codegen-declarative.md) for the worked example.

---

## Technology Stack

| Layer | Technologies |
| :--- | :--- |
| **Frontend canvas** | React Flow / Rete.js, Tailwind CSS, Vite |
| **Backend engine** | FastAPI, Celery, Redis, Jinja2 |
| **Data wrangling** | Pandas, Polars |
| **Statistics** | Statsmodels |
| **Machine learning** | Scikit-Learn |
| **Deep learning** | PyTorch |
| **GenAI / agents** | LangGraph (provider-agnostic LLM nodes) |
| **Diagnostics** | YData-Profiling, Sweetviz |

---

## Roadmap

Development is structured into three iterative phases. The full epic-level decomposition
lives in [`planning_docs/technical_roadmap.md`](./planning_docs/technical_roadmap.md).

### Phase 1 — Foundation (SDK + static canvas)
The open-source Python SDK and graph IR, the codegen engine, the infinite-canvas frontend,
an initial vertical slice of the node library, structural type validation, and basic
save/load + export. **Deliverable:** a frontend-only canvas that maps a node graph to
flawless, downloadable Python — no backend execution required.

### Phase 2 — Living Bridge (reactive backend)
A live FastAPI runtime with Celery workers and sandboxed execution, DAG-based incremental
caching, rich in-node result rendering, data connectors with secure credential handling, and
the platform infrastructure/security/observability layer. **Deliverable:** "Execute" runs
real Python, with incremental caching and results rendered back into the canvas.

### Phase 3 — Frontier (Deep Learning, GenAI & agents)
Visual PyTorch composition with real-time tensor-shape resolution, visual LangGraph
multi-agent orchestration, and the natural-language canvas agent that builds, wires, and runs
pipelines from a single instruction. Real-time multiplayer collaboration is planned here,
with the IR designed CRDT-ready from the start.

---

## Repository Layout

```
colony-mind/
├── colonymind/               # Python SDK source
│   ├── ir/                   # Graph intermediate representation (schema, serialization)
│   ├── nodes/                # Node contract, registry, and reference examples
│   ├── codegen/              # Whole-graph compiler + reference executor (compile_to_code / execute)
│   ├── data, clean, stats, ml, reports/   # Reference node-family SDK wrappers
│   └── api.py                # @public_op decorator + inspectable-return contract
├── docs/
│   ├── adr/                  # Architecture Decision Records (foundational decisions)
│   ├── node-contract-spec.md # Node-definition contract reference
│   ├── node-registry.md      # Registry and plugin discovery guide
│   ├── authoring-a-node.md   # Step-by-step guide to writing a node
│   ├── codegen-compiler.md   # Codegen engine: compiler, executor, declarative seam
│   ├── package-layout.md     # Package layout & namespace conventions
│   ├── versioning-and-releases.md  # Semantic versioning & release process
│   └── public-api-conventions.md   # Public API naming, signatures, return objects
├── epics/
│   ├── epic-1-core-sdk-and-ir.md          # Epic 1 — Core SDK & graph IR
│   └── epic-2-code-generation-engine.md   # Epic 2 — Code generation engine
├── examples/
│   └── plugin_stub/          # Out-of-core node plugin example (cm-texttools, text.reverse)
├── planning_docs/
│   ├── proposal.md           # Product vision & market mapping
│   └── technical_roadmap.md  # Engineering decomposition (epics, phases, decisions)
├── .github/workflows/        # CI (lint, type-check, test) and release pipelines
├── pyproject.toml            # Packaging, dependencies, tool config (ruff, mypy, pytest)
├── uv.lock                   # Pinned, reproducible dependency lockfile
└── README.md
```

---

## Documentation

- [Package Layout & Namespace Conventions](./docs/package-layout.md) — the `colonymind` / `cm`
  package structure and the planned functional-pipeline namespaces.
- [Public API Conventions](./docs/public-api-conventions.md) — naming, signatures, and the
  serializable + inspectable return-object contract every wrapper must meet.
- [SDK Design Philosophy](./docs/sdk-design-philosophy.md) — the thin / deterministic / pure
  rules and the `@cm.public_op` runtime check that enforces them.
- [Codegen Engine](./docs/codegen-compiler.md) — the whole-graph `compile_to_code` compiler
  and reference `execute` interpreter, plus the
  [declarative `nn.Module` seam](./docs/codegen-declarative.md).
- [How Codegen Works](./docs/how-codegen-works.md) — an overview of the codegen pipeline,
  the two paradigms, and the golden / equivalence quality gates that back the
  "what you see runs" promise.
- [Connection Validation: Rules as a Portable Artifact](./docs/connection-validation.md) — the
  type rules + `Diagnostics` schema shipped to the frontend canvas as data, and the
  frontend-vs-SDK authority model.
- [Versioning & Releases](./docs/versioning-and-releases.md) — Semantic Versioning policy and
  the tag-driven release process.
- [Architecture Decision Records](./docs/adr/) — the foundational `§A` decisions.
- [How to Author a Node](./docs/authoring-a-node.md) — the node-definition contract in practice.

The SDK uses [`uv`](https://docs.astral.sh/uv/) for reproducible installs (`uv sync`), `ruff`
for lint + format, and `mypy` for type-checking; CI runs all three plus the test suite on
Python 3.11 and 3.12.

---

## License

The Colony Mind SDK in this repository is licensed under the
[Apache License 2.0](./LICENSE). Colony Mind follows an **open-core** model: the
Python SDK is open source, while the collaborative platform (visual canvas,
real-time multiplayer, hosting, and enterprise features) is a separate
proprietary product. See [Open-Core Boundary](./docs/open-core-boundary.md) for
what is SDK vs. platform-only, and
[Dependency Licensing & Compatibility](./docs/licensing-and-dependencies.md) for
the dependency-license policy.

Contributions are accepted under a license-grant CLA — see
[CONTRIBUTING.md](./CONTRIBUTING.md).
