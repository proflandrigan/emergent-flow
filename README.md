# Colony Mind

### The Visual Architecture Platform for Data Science, Analytics & Machine Learning

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

> **Status:** Early-stage. This repository currently contains the planning and design
> material in [`planning_docs/`](./planning_docs/). See the
> [Technical Roadmap](./planning_docs/technical_roadmap.md) for the engineering
> decomposition and the [Product Proposal](./planning_docs/proposal.md) for the vision.

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
│     Pandas / Polars  |  Pingouin  |  Scikit-Learn         │
│          PyTorch  |  LangGraph  |  YData-Profiling        │
└──────────────────────────────────────────────────────────┘
```

### Core design principles

These cross-cutting decisions shape nearly every part of the system (see
[§A of the roadmap](./planning_docs/technical_roadmap.md)):

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

### Example of generated code

The visual builder compiles structured SDK objects rather than arbitrary code blocks, so the
output stays clean and maintainable:

```python
import colony_mind as cm

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

---

## Technology Stack

| Layer | Technologies |
| :--- | :--- |
| **Frontend canvas** | React Flow / Rete.js, Tailwind CSS, Vite |
| **Backend engine** | FastAPI, Celery, Redis, Jinja2 |
| **Data wrangling** | Pandas, Polars |
| **Statistics** | Pingouin, Statsmodels |
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
├── planning_docs/
│   ├── proposal.md           # Product vision & market mapping
│   └── technical_roadmap.md  # Engineering decomposition (epics, phases, decisions)
└── README.md
```

---

## License

To be determined. Colony Mind follows an open-core model: the Python SDK is intended to be
open-source, with the platform as the product. The exact SDK/platform boundary is being
decided alongside the core SDK packaging work (see Epic 1 in the roadmap).
