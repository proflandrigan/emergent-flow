# Colony Mind — Technical Roadmap

*A high-level engineering decomposition of the Colony Mind proposal: an infinite-canvas visual platform for DE / Stats / DS / ML / GenAI, backed by an open-source Python SDK that the canvas maps to 1:1.*

---

## How to read this document

This roadmap decomposes the product into **high-level epics** — coherent, independently-plannable bodies of work. It deliberately stops at the epic level; subtasks belong in the tracker once an epic is picked up.

Each epic carries:

- **Goal** — the outcome that defines "done enough to move on."
- **Scope** — what is in, and what is explicitly deferred.
- **Key design decisions & options** — the real forks in the road, with a recommendation.
- **Dependencies** — what must exist first.
- **Notes / risks** — traps, sequencing hazards, and things the proposal under-specifies.
- **Phase** — alignment to the proposal's three-phase plan (with adjustments noted in §D).

Before the epics, §A fixes the cross-cutting architectural decisions that shape almost everything else. Read it first — several "challenges" in the proposal dissolve once these are settled.

---

## A. Foundational architectural decisions (read first)

These five decisions are upstream of nearly every epic. Getting them right early is cheaper than retrofitting.

### A1. The graph is the single source of truth; code is a compiled artifact

The proposal promises both a visual canvas *and* clean exportable Python, and implies users can push that Python to Git. The trap is treating the canvas and the code as two co-equal representations that must stay in sync — that forces you into bidirectional sync (parsing arbitrary edited Python back into a node graph via AST analysis), which is enormous, fragile, and low-ROL early.

**Recommendation:** The serialized graph (the IR — see Epic 1) is canonical. Python is a **one-way build output**, like compiled assembly. Export to Git is a publish step, not a sync. This keeps the "glass-box" promise (you can always see and run the exact code) without owning a Python-to-graph decompiler.

**Consequence to communicate to users:** edits made to exported `.py` files in Git do not flow back to the canvas. Reverse round-tripping can be revisited later as a contained, opt-in feature, but should not gate the platform.

### A2. Execute the IR, not the generated string

There are two ways to "run" a graph: (a) generate a Python string and `exec()` it, or (b) interpret the IR directly by calling SDK functions. Option (a) makes "what you see is what runs" trivially true but means production servers routinely `exec()` generated code — a security and reliability liability. Option (b) is safe and testable but risks the *displayed* code drifting from what *actually executed*.

**Recommendation:** Build **two pure functions over the same IR** — `compile_to_code(ir)` and `execute(ir)` — and treat their equivalence as a hard invariant enforced by golden/property tests (for a corpus of graphs, the artifacts produced by `execute(ir)` must equal those produced by running `compile_to_code(ir)`). Production executes the IR directly; the generated string is for display and export only. Arbitrary user-supplied code (the "raw Python" escape-hatch node) is the sole exception and lives behind the sandbox (Epic 6).

### A3. The SDK supports two paradigms, not one

The clean example in the proposal (`cm.data.load_csv(...) → cm.clean.impute_missing(...) → cm.stats.anova(...)`) is a **functional pipeline**: each node is one function call returning an inspectable object. That maps beautifully to data prep, stats, and classical ML. It does **not** map to deep learning, where a model is a *declarative module graph* (a `nn.Module` class), nor cleanly to multi-agent graphs (stateful, cyclic-ish control flow).

**Recommendation:** Design the SDK and codegen around two first-class shapes from day one:

1. **Functional pipeline** — DAG of pure-ish transforms (DE / Stats / classical ML / reporting).
2. **Declarative module/graph definition** — compiled into a class or graph object (DL architectures via PyTorch; agent graphs via LangGraph).

Codegen, execution, and validation differ per paradigm; pretending everything is a function call will produce ugly code exactly where the proposal promises it won't (Challenge 2).

### A4. Storage tiering: Redis is for metadata, not 10 GB DataFrames

The proposal repeatedly names Redis as the cache. Redis is an in-memory store — pushing multi-GB DataFrames or tensors through it will exhaust memory and serialize slowly.

**Recommendation:** Tier the artifact store. Redis (or equivalent) holds **cache metadata, execution hashes, small scalar/JSON results, and the DAG state index**. Large artifacts (DataFrames, tensors, models, HTML reports) serialize to a **disk- or object-backed store** using columnar/zero-copy formats (Arrow IPC / Parquet for frames; `torch.save` / safetensors for models). The cache key points at the artifact location, not the bytes.

### A5. The frontend canvas is a separate repo that consumes the IR — not a co-equal codebase

The proposal draws the canvas (React Flow / Tailwind / Vite) and the SDK (Pandas / Pingouin / PyTorch …) as two layers of one system, which invites treating them as one codebase. The trap is co-locating a TypeScript frontend and a Python SDK in a single repo: two unrelated toolchains (`npm`/Vite/Vitest vs. `uv`/`ruff`/`mypy`/`pytest`), two CI matrices, and two dependency trees fighting in one tree — and, worse, a temptation for the frontend to reach into Python internals instead of through the published contract.

**Recommendation:** Split by toolchain into separate repos that couple **only through serialized artifacts**, never a shared source import:

- `colony-mind` — this repo: the open-source Python SDK + graph IR + codegen (Epics 1, 2, 5/typing, 14).
- `colony-mind-canvas` — the React frontend canvas (roadmap Epic 3) + node config UX (Epic 4 surface) + result rendering (Epic 8).
- `colony-mind-server` — the FastAPI/Celery execution backend (Epics 6, 7, 9, 15) that wraps the SDK's reference executor.

The boundary the canvas consumes from the SDK is exactly three published, versioned artifacts:

1. the **IR JSON Schema** (Epic 1) — so the canvas produces and reads valid graphs with no Python present;
2. the **generated-code string** from `compile_to_code(ir)` (Epic 2) — for the in-node "show code" panel;
3. the **type catalog + connection-compatibility rules as data** (Epic 5) — so the canvas gives instant red-edge feedback without a Python round-trip.

**Consequences to communicate.** The frontend never `import`s `colonymind`; it talks to the IR contract (Phase 1, no backend) and later to `colony-mind-server` over REST/WebSocket (Phase 2+). This keeps the one-way, IR-is-source-of-truth model (A1), the execute-the-IR equivalence model (A2), and the open-core boundary (which is partly *a repo boundary*: SDK open, canvas/server are the product) all clean. The cost the SDK must pay back: it must **publish stable, serializable schemas and rule artifacts** (versioned alongside the IR schema) as first-class outputs, because a separate frontend can only be as good as the contract it's handed.

---

## B. Repo map: which epic lives where, and when frontend work unblocks

Per §A5, this product is **three repos**, not one, coupled only through published, versioned
artifacts. Before diving into individual epics, this section gives the at-a-glance map: which
track (repo) owns each epic, and — for everything that touches the frontend — exactly what
SDK contract has to exist before that frontend work can begin.

### B1. Epic → Track → Repo

| Epic | Title | Track | Repo |
| :-- | :-- | :-- | :-- |
| 1 | Core SDK & Graph IR | **Python SDK** | `colony-mind` |
| 2 | Code Generation Engine | **Python SDK** | `colony-mind` |
| 3 | Frontend Canvas Engine | **Frontend** | `colony-mind-canvas` |
| 4 | Node Library & Configuration UX | **Frontend** (config-panel UI) + **Python SDK** (node catalog/defaults) — *split* | `colony-mind-canvas` + `colony-mind` |
| 5 | Type-Safe Graph & Connection Validation | **Cross-cutting** — SDK owns the type system + rules; canvas consumes the rules-as-data for live feedback — *split* | `colony-mind` (owns) / `colony-mind-canvas` (consumes) |
| 6 | Backend Execution Runtime & Sandboxing | **Backend/Server** | `colony-mind-server` |
| 7 | DAG Caching & Incremental State Management | **Backend/Server** | `colony-mind-server` |
| 8 | Result Rendering & In-Node Visualization | **Frontend** (rendering) + **Backend/Server** (heavy-artifact rendering, payload shaping) — *split* | `colony-mind-canvas` + `colony-mind-server` |
| 9 | Data Connectors & Credential Management | **Backend/Server** | `colony-mind-server` |
| 10 | Deep Learning Module & Tensor Shape Resolution | **Python SDK** (layer nodes, declarative codegen, shape inference) + **Frontend** (real-time shape-mismatch UI) — *split* | `colony-mind` + `colony-mind-canvas` |
| 11 | GenAI & Multi-Agent Orchestration | **Python SDK** (nodes, codegen) + **Backend/Server** (execution, cost tracking) + **Frontend** (live message/token viz) — *split* | all three |
| 12 | Canvas-Aware Coding Agent (NL → graph) | **Cross-cutting** — agent logic likely SDK/server-side, propose/apply UX is frontend | `colony-mind` / `colony-mind-server` + `colony-mind-canvas` |
| 13 | Real-Time Multiplayer Collaboration | **Frontend** (presence/cursors/CRDT client) + **Backend/Server** (sync transport) — *split* | `colony-mind-canvas` + `colony-mind-server` |
| 14 | Project Persistence, Versioning & Git Sync | **Python SDK** (schema migrations, IR/export format) + **Backend/Server** (project storage) — *split* | `colony-mind` + `colony-mind-server` |
| 15 | Platform Infrastructure, Security & Observability | **Cross-cutting** (underpins 6–13; mostly server/infra) | `colony-mind-server` (+ deployment infra) |

This repo (`colony-mind`) ships Epics 1, 2, and 5 (rules-owning half) outright, plus the SDK-side
slices of 4, 10, 11, and 14. Everything else lives downstream in `colony-mind-canvas` or
`colony-mind-server` and only ever touches this repo through the three published artifacts
named in §A5.

### B2. Frontend readiness: what's the gate, and is it met?

This is the practical question for anyone staffing the canvas repo: **what SDK artifact has to
exist before this slice of frontend work can start?** Three gates, in order of when they open:

| Frontend slice | Gating SDK artifact (this repo) | Gate met today? | Can frontend start? |
| :-- | :-- | :-- | :-- |
| Phase-1 static canvas: node placement, edge drawing → produces valid IR → "show code" panel → downloadable script (Epic 3 core, Epic 4 surface) | **IR JSON Schema** (Epic 1) + **`compile_to_code(ir)` output** (Epic 2) | **Yes** — both have landed in this repo. | **Yes — can start now.** This is the whole Phase-1 demo and needs zero backend. |
| Live connection/type validation: red-edge feedback, "why is this invalid" tooltips (Epic 5's frontend-facing half, wired into Epic 3) | **Type catalog + connection-compatibility rules-as-data artifact** (Epic 5, repo Epic 3, `epics/epic-3-type-safe-graph-and-validation.md`) | **Yes** — Epic 5 is complete (Stories 1–8 merged to `main`); the rules-as-data artifact is published and versioned. | **Yes — can start now.** The canvas can wire real live validation against the published artifact, not just a mocked shape. |
| Real-time tensor shape-mismatch UI (Epic 10's frontend half) | Epic 5's general framework **plus** Epic 10's dimension-level shape inference (meta-tensor tracing), exported the same way as the structural rules | **No** — Epic 5 has landed, but Epic 10 (dimension-level shape inference) hasn't started. | **Blocked** on Epic 10. |
| Result rendering inside nodes (Epic 8) | A defined **result-payload contract** from the execution runtime (Epic 6) — sized/paginated/typed renderable payloads | **No** — Epic 6 (backend execution) hasn't started; there is no live executor to shape payloads from yet. | **Blocked** until Epic 6 publishes its result-payload shape (even a draft contract would unblock UI prototyping). |
| Live message/token visualization for GenAI/agent flows (Epic 11's frontend half) | Epic 6 (execution/streaming) + Epic 11's agent-graph execution semantics | **No** — both upstream. | **Blocked.** |
| Multiplayer presence/cursors (Epic 13) | No SDK gate per se, but the **IR must be CRDT-friendly** (a property of Epic 1's schema design, not a separate artifact) — open question whether Epic 1 as landed satisfies this (open question, see §F item 4). | Partially — Epic 1 has landed, but CRDT-friendliness was a *design intent*, not a verified property. | **Nominally startable**, but verify the open question above before investing heavily. |

**Bottom line:** the full Phase-1 canvas is unblocked *today* — the static canvas (Epic 3 core +
Epic 4 surface) on Epics 1–2, **and** live connection/type validation on Epic 5's now-published
rules-as-data artifact (Stories 1–8 merged). All three SDK→canvas contracts have landed, so the
frontend can start in earnest. What remains gated lives downstream behind the backend: result
rendering (Epic 8) waits on the execution runtime (Epic 6), and the GenAI/agent and tensor-shape
UIs wait on Epics 11 / 10 respectively.

---

## C. The Epics

Epics are numbered for reference, not strictly for execution order. §E gives the critical path.

---

### Epic 1 — Core SDK & Graph Intermediate Representation (IR)

**Goal:** A versioned, open-source Python SDK plus a canonical graph schema (the IR) that every other layer reads and writes. This is the spine of the product.

**Scope**
- In: the IR schema (nodes, ports, edges, params, sub-graphs/groups); the node-definition contract (each node declares its ports, typed params, codegen template, executor, and — where relevant — a shape/type-inference function); SDK packaging, versioning, and public API conventions; serialization/deserialization of graphs.
- In: the DE / clean / stats / classical-ML / reporting wrappers (Pandas/Polars, Pingouin/Statsmodels, Scikit-Learn, YData-Profiling/Sweetviz) as the first concrete node families.
- Out (later epics): DL and GenAI node families; the visual UI; backend execution.

**Key design decisions & options**
- **IR as data vs. IR as code.** Recommend a declarative, serializable data structure (JSON/Protobuf-able) — *not* a Python object graph that only exists at runtime — so the frontend, backend, and codegen can all operate on it without a Python runtime present. (Phase 1 has no backend; the frontend must produce valid IR and code on its own.)
- **Node registry / plugin architecture.** Define nodes declaratively in a registry so the catalog can grow (and eventually be community-extensible) without core changes. This is the difference between a fixed tool and a platform.
- **SDK design philosophy** (set and enforce now): thin wrappers, deterministic, version-pinned dependencies, every operation returns a serializable + inspectable object, pure functions where possible. Pingouin was chosen in the proposal specifically because it returns clean DataFrames — adopt "returns inspectable structured data" as a selection criterion for *every* wrapped library.

**Dependencies:** none — this is the root.

**Notes / risks**
- The IR schema is the hardest thing to change later; over-invest in getting node/port/type modeling right and in a **schema versioning + migration** strategy (saved graphs from v1 must open in v2 — see Epic 14).
- Open-core licensing decision lives here: the SDK is pitched as open-source, the platform as the product. Decide the boundary early (which nodes/features are SDK vs. platform-only) because it affects packaging.

**Phase:** 1 (foundation).

---

### Epic 2 — Code Generation Engine

**Goal:** Deterministic IR → idiomatic, PEP8-clean, runnable Python. The "glass-box" promise made real.

**Scope**
- In: template-based codegen (Jinja2 per the proposal) for the functional-pipeline paradigm; deterministic variable naming; import collection/dedup; formatting pass (run `ruff`/`black` over output); export of a runnable script/module.
- In: codegen for the declarative paradigm (Epic 3-adjacent) once DL/agents exist — generating a `nn.Module` class or a LangGraph definition rather than a flat call chain.
- Out: bidirectional (code → graph) parsing (deferred per A1).

**Key design decisions & options**
- **Templating vs. AST construction.** Jinja2 templates are fast to build and easy to read, but string templating is fragile for nested/declarative structures (DL classes). Consider AST-based generation (`ast` / `libcst`) for the declarative paradigm where structure matters, keeping templates for flat pipelines. A hybrid is fine and likely necessary.
- **Naming strategy.** Avoid the `df_step_3_v2_final` trap (proposal Challenge 2) by deriving readable names from node labels with collision handling, not from execution order.
- **Equivalence enforcement.** Per A2, the generated code and the executor must produce identical artifacts. Bake this into CI as a golden-test corpus — it is the single most important quality gate for trust in the product.

**Dependencies:** Epic 1.

**Notes / risks**
- Codegen quality *is* the marketing claim. A messy edge case in generated code is a credibility hit. Budget for a broad fixture suite covering every node type and common compositions.

**Phase:** 1.

---

### Epic 3 — Frontend Canvas Engine

**Goal:** A fluid infinite canvas: node creation, pan/zoom, edge drawing, selection, grouping/sub-graph nesting, and an extensible node-rendering framework — performant at hundreds-to-thousands of nodes.

**Repo / boundary (per A5):** This epic lives in its own frontend repo (`colony-mind-canvas`), *not* in the Python SDK repo. It consumes the SDK's published contract — the IR JSON Schema, the `compile_to_code` output, and the Epic-5 rules-as-data — and never imports `colonymind`. Plan the SDK side to *publish* those artifacts; plan this epic against them.

**Scope**
- In: canvas runtime; node/edge rendering; interaction (drag, connect, multi-select, group); sub-graph nesting/collapse; the per-node config-panel framework; in-node "show code" view (consumes Epic 2 output).
- Out: collaborative editing (Epic 13); result visualizations inside nodes (Epic 8); backend wiring (Epic 6).

**Key design decisions & options**
- **React Flow (@xyflow) vs. Rete.js.** Given the proposed React + Tailwind + Vite stack, **React Flow** is the natural fit: React-native, large ecosystem, strong node-editor primitives. Rete.js is more rendering-agnostic and plugin-driven but smaller and less React-idiomatic. Recommend React Flow, with an explicit **performance budget** and a virtualization/level-of-detail plan (render simplified nodes when zoomed out; virtualize off-screen nodes) — the "hundreds of components smoothly" claim is not free.
- **Node UI as schema-driven.** Generate config panels from the node's declared param schema (Epic 1) rather than hand-coding a form per node. Keeps the catalog scalable and the UI consistent.

**Dependencies:** Epic 1 (IR schema), Epic 2 (generated code for the code-view panel), Epic 5 (type catalog + connection-compatibility rules-as-data for live edge validation). All consumed as published artifacts, not as a code import (A5).

**Notes / risks**
- Phase-1 milestone is achievable here with **zero backend**: canvas → valid IR → downloadable script. This de-risks the whole product early and is a strong demo.
- Canvas performance is the most likely place to discover the architecture doesn't hold; prototype with a synthetic 1,000-node graph early.
- **Separate repo, contract-only coupling (A5).** The canvas's quality ceiling is the quality of the published SDK contract — get the IR schema, codegen output, and rules artifact stable and versioned before building deeply against them, or the frontend churns every time the SDK shifts. Treat a schema/rules version mismatch as a first-class, surfaced error (ties to Epic 14 migrations).

**Phase:** 1.

---

### Epic 4 — Node Library & Configuration UX

**Goal:** The actual catalog of usable nodes across DE, cleaning, stats, classical ML, and reporting — each surfaced with sensible defaults, inline docs, and config panels.

**Scope**
- In: building out node families on top of Epics 1–3; per-node defaults, validation hints, help text; node search/palette; node versioning within the catalog.
- Out: DL nodes (Epic 10), GenAI nodes (Epic 11).

**Key design decisions & options**
- **Breadth vs. depth for v1.** Recommend a deliberately **narrow but end-to-end vertical slice** first (load → clean → one stats test → one model → HTML report — exactly the proposal's example flow) so the whole pipeline is demonstrable before widening the catalog.
- **Escape hatch policy.** Users *will* want a raw-Python / raw-SQL node. Decide now whether to ship one. It breaks the "no arbitrary code" purity and reintroduces security (Epic 6) and codegen concerns — but its absence caps the platform's ceiling. Recommend shipping it, gated behind the sandbox, clearly marked as un-validated.

**Dependencies:** Epics 1–3.

**Notes / risks**
- This epic is effectively unbounded; treat it as continuous rather than "done." Prioritize by the demo narrative and design-partner needs.

**Phase:** 1 (initial slice) → ongoing.

---

### Epic 5 — Type-Safe Graph & Connection Validation

**Goal:** Prevent invalid graphs before execution. Edges carry types (DataFrame, Series, Model, Tensor, Prompt, AgentState, …); incompatible connections are blocked at draw time with a clear reason.

**Scope**
- In: the port type system; connection-compatibility rules; live UI feedback (highlight invalid edges, explain why). This is the general framework that the tensor-shape work (Epic 10) specializes.
- Out: tensor *dimension* inference (lives in Epic 10, built on this framework).

**Key design decisions & options**
- **Strictness.** Strict static typing catches errors early but can feel rigid for exploratory work. Recommend strict on structural type (you cannot wire a Model into a DataFrame input) with softer, warn-don't-block handling for things only knowable at runtime.
- **Where validation runs.** The frontend (separate repo, A5) needs enough of the type system to give instant feedback without a round-trip; the backend re-validates authoritatively. Plan for the rules to be expressible as **data shippable to the client** — a versioned type-catalog + compatibility-table artifact — not as Python the canvas would have to call. This artifact is the third leg of the SDK→canvas contract (A5), alongside the IR schema and the codegen output.

**Repo / boundary (per A5):** This epic lives in the Python SDK repo and *owns* the type system and rules. The "live UI feedback" it enables is rendered by the separate `colony-mind-canvas` repo, which consumes the exported rules artifact and the `Diagnostics` schema — it does not import this code. The SDK is the authoritative re-validator (server-side, Epic 6).

**Dependencies:** Epic 1 (port types in the IR), Epic 2 (the codegen/execute gate the validation hooks into). The canvas (Epic 3, separate repo) is a *consumer* of this epic's rules artifact, not a dependency.

**Notes / risks**
- The proposal frames tensor validation (Challenge 3) as a DL-only problem; it's actually a special case of general edge typing. Building the general framework first means DL gets validation "for free" at the structural level and only needs dimension inference layered on.

**Phase:** spans 1 (structural typing) → 3 (tensor dimensions).

---

### Epic 6 — Backend Execution Runtime & Sandboxing

**Goal:** A live server that turns "Execute" into real Python runs, isolated and resource-bounded, with progress/logs streamed back to the canvas.

**Scope**
- In: FastAPI gateway; Celery (or equivalent) task workers; execution of the IR (per A2); sandboxing/isolation; resource limits (CPU/mem/time); streaming logs and progress to the frontend over WebSockets.
- Out: caching logic (Epic 7); result rendering (Epic 8); connectors (Epic 9).

**Key design decisions & options**
- **Isolation model.** Options: process-per-execution, container-per-session, or persistent kernels (Jupyter-style). Recommend **container-per-session** (or per-execution for untrusted code) with strict CPU/memory/timeout caps and controlled network egress — non-negotiable once raw-code nodes (Epic 4) or LLM-generated code (Epic 12) exist.
- **Where compute runs.** A single FastAPI process cannot handle the proposal's own 10 GB-CSV example. Plan from the start for workers as separate, scalable units, with a path toward remote/distributed execution. State the scaling assumptions explicitly.
- **Execution granularity.** Support "run this node" / "run to here" / "run all," which the caching layer (Epic 7) makes efficient.

**Dependencies:** Epics 1–2; pairs tightly with Epic 7.

**Notes / risks**
- Security is under-specified in the proposal and is the highest-severity risk in the whole system. Treat sandboxing as a first-class deliverable of this epic, not an afterthought.

**Phase:** 2.

---

### Epic 7 — DAG Caching & Incremental State Management

**Goal:** Editing a downstream parameter re-runs only what changed. (Proposal Challenge 1.)

**Scope**
- In: per-node **execution hash** (node config + ordered upstream output hashes + SDK/dependency version); backward dependency tracing; cache lookup/store; invalidation on change; the tiered artifact store from A4.
- Out: cross-user/shared caching (later optimization).

**Key design decisions & options**
- **Hash inputs.** Must include data fingerprint and code/SDK version, not just params — otherwise an SDK upgrade silently serves stale results. Decide how to fingerprint large inputs cheaply (e.g., source path + size + mtime + sampled checksum vs. full content hash).
- **Artifact storage** per A4: metadata in Redis, large artifacts to disk/object store via Arrow/Parquet/safetensors.
- **Eviction.** Define a memory/disk budget and eviction policy (LRU on artifacts) up front; caches grow without bound otherwise.

**Dependencies:** Epic 6.

**Notes / risks**
- This is the feature that makes the infinite canvas feel "live" rather than a script in disguise. It's also a correctness minefield (stale cache = wrong results = lost trust). Invest in invalidation tests.

**Phase:** 2.

---

### Epic 8 — Result Rendering & In-Node Visualization

**Goal:** Execution results (tables, distributions, charts, profiling reports) render richly *inside* nodes on the canvas, not just in a separate console.

**Scope**
- In: serialization of results to renderable payloads; in-node tables, charts, distribution plots (lightweight SVG/canvas); embedding of generated HTML reports (YData-Profiling/Sweetviz); handling large results (paginate/sample, never dump 10M rows into the DOM).
- Out: collaborative cursors/comments (Epic 13).

**Key design decisions & options**
- **Render where?** Server renders heavy artifacts (profiling HTML, big charts) to static/embeddable form; client renders small/interactive ones. Define the size threshold.
- **Truncation contract.** Always sample/paginate large outputs with a clear "showing N of M" affordance; pushing full datasets to the browser will hang the canvas.

**Dependencies:** Epics 3, 6, 7.

**Notes / risks**
- The "embedded charts inside node expansion windows" claim interacts badly with the canvas-performance budget (Epic 3). Heavy embedded views must be lazy and collapsible.

**Phase:** 2.

---

### Epic 9 — Data Connectors & Credential Management

**Goal:** Pull from real sources — SQL/warehouses, cloud object storage, file uploads — with secure credential handling.

**Scope**
- In: a connector framework; first connectors (Postgres/SQL, CSV/Parquet upload, an object store); secrets storage and per-user/per-workspace credential scoping.
- Out: a long tail of niche connectors (incremental).

**Key design decisions & options**
- **Secrets handling.** Never persist credentials in the graph IR (it gets exported to Git and shared). Store references/handles in the IR; keep secrets in a dedicated secret store keyed by workspace.
- **Pushdown vs. pull.** For warehouse sources, decide whether to push computation down (SQL) or pull data into the engine. Pull is simpler for v1; pushdown is a later performance play.

**Dependencies:** Epics 1, 6.

**Notes / risks**
- The proposal mentions "raw SQL database" as a starting node but doesn't address credentials/egress at all — a real gap. Connector security overlaps with sandbox egress policy (Epic 6).

**Phase:** 2 (basic connectors) → ongoing.

---

### Epic 10 — Deep Learning Module & Tensor Shape Resolution

**Goal:** Visually compose PyTorch architectures with real-time, pre-execution shape validation. (Proposal Challenge 3 + DL vision.)

**Scope**
- In: PyTorch layer nodes; the declarative paradigm codegen (generate an `nn.Module`, training loop nodes); **real-time predictive shape resolution** showing expected-vs-actual dims and blocking incompatible connections.
- Out: distributed/multi-GPU training orchestration (later); pretrained-model hubs (later).

**Key design decisions & options**
- **Shape inference method.** Two routes: (a) hand-written symbolic shape functions per layer (full control, lots of maintenance, must track PyTorch's behavior); (b) **PyTorch meta tensors / FakeTensor / `torch.fx` tracing** — run the forward pass on zero-memory meta tensors to derive real shapes without allocating data. Recommend **(b)**: it leverages PyTorch's own semantics, stays correct as layers evolve, and is far less code. Fall back to symbolic functions only where tracing is impractical.
- **Builds on Epic 5.** Structural connection validity comes from the general type system; this epic adds dimension-level inference on top.

**Dependencies:** Epics 1, 2, 5, 6.

**Notes / risks**
- Generated DL code must read like code a practitioner would write (a clean `nn.Module`), which is why the declarative codegen paradigm (A3) had to exist from the start rather than being bolted on.

**Phase:** 3.

---

### Epic 11 — GenAI & Multi-Agent Orchestration

**Goal:** Visual composition of LLM pipelines and multi-agent graphs (LangGraph / AutoGen / CrewAI), with live token/message flow visualization.

**Scope**
- In: LLM nodes (provider-agnostic), prompt-template nodes (context injection), router/conditional nodes, agent-group nodes; codegen to a LangGraph (or chosen framework) definition; live visualization of messages/tokens traversing edges during execution; **cost and token tracking**.
- Out: the natural-language canvas-building agent (Epic 12) — distinct.

**Key design decisions & options**
- **Framework commitment.** Recommend standardizing the *generated* output on one orchestration framework (LangGraph is the proposal's lead) to keep codegen tractable, while keeping the node abstraction framework-agnostic enough to add others later.
- **Cyclic/stateful flows.** Agent graphs aren't pure DAGs (loops, conditional routing, shared state). Confirm the IR (Epic 1) and the DAG-caching model (Epic 7) accommodate this — caching semantics for stateful agent runs differ from deterministic data transforms and may need a separate execution path.

**Dependencies:** Epics 1, 2, 6; benefits from Epic 8 for live viz.

**Notes / risks**
- LLM nodes incur real per-call cost and are non-deterministic — this breaks the clean cache-by-hash assumption (Epic 7). Surface cost/budgets and treat LLM outputs as cache-with-care.
- Naming "Claude / GPT-4" in node UI is fine; keep the provider layer pluggable and current rather than hardcoded.

**Phase:** 3.

---

### Epic 12 — Canvas-Aware Coding Agent (NL → graph)

**Goal:** A user types an instruction ("ingest my DB, run an ANOVA across tiers, model lifetime value") and the agent builds the nodes, wires edges, fills config, runs the pipeline, and drops the report onto the canvas.

**Scope**
- In: an agent that emits **IR mutations** (not free-text code); grounding the agent in the node catalog and type system; preview/confirm UX before it mutates the user's canvas; running and reporting back.
- Out: general code-writing outside the node vocabulary.

**Key design decisions & options**
- **Output target.** The agent should produce **structured graph edits against the IR**, validated by Epic 5, rather than generating Python. This keeps everything inside the safe, validated, glass-box loop (A1/A2) and means the agent literally can't produce something the canvas can't represent.
- **Autonomy level.** Recommend propose-then-apply (show the graph it intends to build, let the user accept/edit) before fully autonomous "build and run." Auto-running pipelines that hit real data/cost without confirmation is risky.

**Dependencies:** Epics 1, 4, 5; ideally 6–8 for end-to-end; conceptually relies on Epic 11's LLM plumbing.

**Notes / risks**
- This is the highest-wow, highest-uncertainty feature. Its quality is bounded by the richness of the node catalog (Epic 4) and the clarity of the type system (Epic 5) — it should come *after* those are mature, not before.

**Phase:** 3.

---

### Epic 13 — Real-Time Multiplayer Collaboration

**Goal:** Figma-style concurrent editing — multiple users on one canvas with live presence, cursors, and conflict-free merging.

**Scope**
- In: concurrent graph editing (CRDT/OT), presence/cursors, comments; conflict resolution on the IR.
- Out: fine-grained permissioning beyond basic share (can layer on later).

**Key design decisions & options**
- **CRDT library vs. managed service.** Options: self-hosted CRDT (Yjs, Automerge) over your WebSocket layer, or a managed real-time service (e.g., Liveblocks). Recommend evaluating a managed service first to avoid owning hard distributed-systems work early; revisit self-hosting if cost/control demands it.
- **What's collaborative.** Graph structure and config should merge cleanly; **execution state and caches are trickier** — decide whether runs are per-user or shared-canvas, as it changes the caching model (Epic 7).

**Dependencies:** Epics 1, 3, 6.

**Notes / risks**
- **Biggest scoping gap in the proposal.** "Figma-like multiplayer" is stated in the vision but absent from the three-phase plan. Multiplayer is a large, cross-cutting epic that deeply affects the IR, the canvas, and the backend. Decide early whether it's an MVP differentiator or a deliberate fast-follow — retrofitting collaboration onto a single-user data model is painful. Recommend single-user for Phase 1–2, multiplayer as a planned Phase 3 (or 2.5) epic designed for from the IR onward.

**Phase:** 3 (but the IR in Epic 1 should be CRDT-friendly from day one).

---

### Epic 14 — Project Persistence, Versioning & Git Sync

**Goal:** Save/load projects reliably across SDK versions; export generated code to a Git repo.

**Scope**
- In: project storage; **graph schema migrations** (open old saved graphs in new versions); one-way Git export of generated code (per A1); project metadata/organization.
- Out: bidirectional Git ↔ canvas sync (deferred, A1).

**Key design decisions & options**
- **Schema migration strategy.** Versioned IR with explicit migration steps. This is unglamorous and essential — without it, every SDK/node change risks bricking saved work.
- **Export format.** A runnable script vs. a structured project (script + `requirements.txt` pinned to SDK version + data references). Recommend the latter so exports actually run elsewhere.

**Dependencies:** Epics 1, 2.

**Notes / risks**
- Versioning interacts with the cache hash (Epic 7, which includes SDK version) and with export reproducibility. Pin dependency versions in exports.

**Phase:** 1 (basic save/load + export) → 2/3 (migrations as schema evolves).

---

### Epic 15 — Platform Infrastructure, Security & Observability (cross-cutting)

**Goal:** The connective tissue: auth, multi-tenancy, deployment, secrets, monitoring, and the observability needed to debug user pipelines.

**Scope**
- In: authn/authz; workspace/tenant model; deployment & CI/CD; secrets management (pairs with Epic 9); logging/metrics/tracing across canvas → backend → workers; execution observability (streaming logs, progress, error surfacing back to nodes).
- Out: nothing structurally — but it activates with the backend (Phase 2), since Phase 1 is frontend-only.

**Key design decisions & options**
- **Deployment target.** Cloud-hosted SaaS vs. self-hostable (enterprise data-residency is a stated competitor weakness to exploit). Recommend designing for both — containerized, config-driven — even if SaaS ships first.
- **Tenancy isolation.** How strongly are tenants' executions and data isolated? Ties directly to the sandbox model in Epic 6.

**Dependencies:** underpins Epics 6–13.

**Notes / risks**
- Sandboxing/security spans this epic and Epic 6 and is the highest-severity risk area. Treat it as a named owner's responsibility, not diffuse.

**Phase:** 2 onward.

---

## D. Mapping to the proposal's three phases (with adjustments)

The proposal's phasing is sound; two adjustments are recommended.

**Phase 1 — Foundation (SDK + static canvas, no backend execution).**
Epics 1, 2, 3, 4 (initial vertical slice), 5 (structural typing), 14 (basic save/load + export). Deliverable: a frontend-only canvas that maps a node graph to flawless, downloadable Python. Strongest early de-risking milestone — the whole "glass-box codegen" thesis is provable here without infrastructure. Note that even in Phase 1 this is **two repos** (A5): the Python SDK (Epics 1, 2, 5, 14) and the `colony-mind-canvas` frontend (Epics 3, 4 surface), coupled only by the published IR schema, codegen output, and rules artifact.

**Phase 2 — Living Bridge (reactive backend).**
Epics 6, 7, 8, 9, plus 15 spinning up (auth/infra/security/observability), and 14 maturing (migrations). Deliverable: "Execute" runs real Python, with incremental caching and rich results rendered back into the canvas.

**Phase 3 — Frontier (DL, GenAI, agents).**
Epics 10, 11, 12, and 5's tensor-dimension layer. Deliverable: visual deep learning with shape validation, visual agent orchestration, and the natural-language canvas agent.

**Adjustment 1 — Multiplayer (Epic 13) needs a home.** It's in the vision but absent from the phases. Recommend explicitly placing it (a planned Phase 3, or a "Phase 2.5") and, critically, designing the IR (Epic 1) to be CRDT-friendly from the very start so it can be added without a rewrite.

**Adjustment 2 — Security/sandboxing (Epics 6 + 15) is treated as a Phase-2 implementation detail in the proposal but is a first-class, high-severity deliverable.** Promote it to an explicit Phase-2 workstream with a named owner.

**Adjustment 3 — The frontend is a separate repo, not a layer of one codebase (A5).** The proposal's three-layer stack diagram reads as one system; in practice the canvas (`colony-mind-canvas`) and the execution backend (`colony-mind-server`) are distinct repos from this Python SDK, coupled only through the published IR schema, codegen output, and rules-as-data. Decide the repo split at the start of Phase 1 — retrofitting a TypeScript frontend out of a shared Python repo, or untangling frontend reach-ins into SDK internals, is exactly the kind of avoidable rework A1/A2 already warned about for sync.

---

## E. Critical path & sequencing summary

The hard dependency spine:

> **Epic 1 (IR + SDK)** → **Epic 2 (codegen)** → **Epic 3 (canvas)** → *Phase 1 demo* → **Epic 6 (execution) + Epic 7 (caching)** → **Epic 8 (results)** → *Phase 2 product* → **Epics 10 / 11** → **Epic 12 (agent)** → *Phase 3 frontier*.

Run in parallel where possible: Epic 4 (node library, continuous), Epic 5 (typing, alongside 1/3), Epic 9 (connectors, alongside 6), Epic 14 (persistence, alongside 1/2), Epic 15 (infra, alongside 6). Epic 13 (multiplayer) is independent enough to schedule flexibly *if and only if* the IR was designed for it in Epic 1.

The two decisions that most constrain everything downstream and should be locked first: **the IR schema (Epic 1)** and **the execute-the-IR-not-the-string equivalence model (A2)**.

---

## F. Open questions / decision register

| # | Question | Why it matters | Suggested default |
| :-- | :-- | :-- | :-- |
| 1 | One-way codegen, or eventual bidirectional Git sync? | Determines whether a Python→graph parser is ever needed (huge). | One-way; revisit later as opt-in. |
| 2 | Execute generated strings, or execute the IR? | Security, reliability, and the "what runs = what you see" guarantee. | Execute IR; enforce equivalence in CI. |
| 3 | Ship a raw-code / raw-SQL escape-hatch node in v1? | Raises the ceiling but reintroduces sandboxing + codegen concerns. | Yes, sandboxed and marked un-validated. |
| 4 | Is multiplayer an MVP differentiator or a fast-follow? | Single→multi retrofit is expensive; affects IR design now. | Single-user MVP; IR built CRDT-ready. |
| 5 | SaaS-only or self-hostable? | Enterprise data-residency is a stated competitive wedge. | Design for both; ship SaaS first. |
| 6 | React Flow vs. Rete.js for the canvas? | Ecosystem fit vs. rendering flexibility; perf ceiling. | React Flow, with a perf budget + virtualization. |
| 7 | Shape inference: symbolic functions or meta-tensor tracing? | Maintenance burden vs. correctness for DL validation. | Meta-tensor / FakeTensor tracing. |
| 8 | Caching semantics for non-deterministic LLM/agent nodes? | Breaks the deterministic hash-cache assumption. | Separate execution path; cache-with-care + cost tracking. |
| 9 | Open-core boundary: what's SDK vs. platform-only? | Affects packaging, licensing, and community story. | Decide alongside Epic 1 packaging. |
| 10 | Where does heavy compute run at scale (10 GB+)? | Single FastAPI process won't hold it; the proposal assumes it does. | Isolated scalable workers; plan for remote/distributed. |
| 11 | One repo or split SDK / canvas / server? | Toolchain, CI, and the open-core boundary; frontend reach-ins are hard to undo. | Separate repos (A5), coupled only by published IR schema + codegen output + rules-as-data. |
