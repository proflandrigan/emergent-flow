# Colony Mind — Technical Implementation Timeline

*A single, linear order in which one developer can complete every epic across the whole
product. Where the [technical roadmap](./technical_roadmap.md) gives a dependency graph with
parallel tracks, this doc flattens it into one sequence you can walk top-to-bottom, switching
repos only when a dependency forces it.*

---

## How to read this

- The roadmap numbers epics **globally** (Epic 1–15). This timeline keeps those roadmap
  numbers as the canonical id and adds a **step number** (the order to actually do them).
- For the three epics delivered in this SDK repo, the **repo-Epic alias** is shown
  (repo Epic 1 = roadmap Epic 1, repo Epic 2 = roadmap Epic 2, **repo Epic 3 = roadmap Epic
  5**). See [`../epics/README.md`](../epics/README.md) for the full numbering map and the
  "Epic 3" collision warning.
- **"Both repos" is actually three.** The roadmap (§A5) splits the product across
  `colony-mind` (this SDK), `colony-mind-canvas` (React/TS frontend), and `colony-mind-server`
  (FastAPI/Celery backend). "All epics" cannot complete without the server repo, so this
  timeline spans all three — flagging the repo on every step.

### Status legend

- `[x]` — **done** (merged to `main`, deliverables present in the repo).
- `[~]` — **in progress** (partial; story-level detail noted).
- `[ ]` — **not started.**

---

## Phase 1 — Foundation (SDK + static canvas, no backend execution)

> Deliverable: a frontend-only canvas that maps a node graph to flawless, downloadable
> Python. Two repos (`colony-mind`, `colony-mind-canvas`), coupled only by the published IR
> schema, codegen output, and rules-as-data artifact.

- [x] **Step 1 — Roadmap Epic 1: Core SDK & Graph IR** · `colony-mind` · *repo Epic 1*
  - Deps: none (the root). The versioned IR schema, node contract, registry, serialization.
  - Status: **done** — `colonymind/ir/`, node contract/registry, `cm` public API all landed.

- [x] **Step 2 — Roadmap Epic 2: Code Generation Engine** · `colony-mind` · *repo Epic 2*
  - Deps: Step 1. `compile_to_code(ir)` + `execute(ir)`, equivalence as a CI gate, golden corpus.
  - Status: **done** — through Story 9 (`compiler.py`, `executor.py`, formatting, fixtures).

- [~] **Step 3 — Roadmap Epic 5: Type-Safe Graph & Connection Validation** · `colony-mind` · *repo Epic 3*
  - Deps: Steps 1–2. The type-token system, compatibility rules, whole-graph inference,
    `cm.validate`, and the rules-as-data artifact the canvas consumes.
  - Status: **in progress** — Story 1 (ADRs 0011/0012) ✅, Story 2 (type registry/catalog) ✅,
    Story 3 (compatibility + cardinality engine) **active on `epic3-story3`**; Stories 4–8
    (graph inference, `cm.validate`, shared codegen/execute gate, rules-export artifact,
    golden diagnostics) pending.
  - **Gate:** Step 5 (canvas live validation) is blocked until this publishes the rules-as-data
    artifact (Story 7).

- [ ] **Step 4 — Roadmap Epic 14: Project Persistence, Versioning & Git Sync (basic)** · `colony-mind` (+ `colony-mind-server` later)
  - Deps: Steps 1–2. Basic save/load, one-way Git export of generated code, schema-migration
    scaffolding. Stays in the Python repo before the toolchain switch to the canvas.
  - Note: migrations *mature* later (Phase 2, Step 11-adjacent) as the schema evolves.

- [ ] **Step 5 — Roadmap Epic 3: Frontend Canvas Engine** · `colony-mind-canvas`
  - Deps: Steps 1, 2, **3** (consumes IR schema + `compile_to_code` output + rules-as-data;
    never `import colonymind`). React Flow canvas, pan/zoom, edge drawing, grouping,
    schema-driven config panels, in-node "show code" view, live red-edge validation.
  - **Toolchain switch:** first work in the `npm`/Vite/Vitest repo.

- [ ] **Step 6 — Roadmap Epic 4: Node Library & Configuration UX** · `colony-mind-canvas` + `colony-mind` *(split)*
  - Deps: Steps 1–3, 5. The end-to-end vertical slice (load → clean → one stats test → one
    model → HTML report), node palette/search, defaults & help text. SDK owns node
    catalog/defaults; canvas owns the config-panel surface. Treat as continuous after the
    first slice.

> **End of Phase 1 milestone:** canvas → valid IR → downloadable, runnable Python, zero
> backend. The strongest early de-risking demo.

---

## Phase 2 — Living Bridge (reactive backend)

> Deliverable: "Execute" runs real Python, with incremental caching and rich results rendered
> back into the canvas. Introduces the third repo, `colony-mind-server`.

- [ ] **Step 7 — Roadmap Epic 15: Platform Infrastructure, Security & Observability** · `colony-mind-server` (+ deploy infra)
  - Deps: underpins Steps 8–15. Stand up first: authn/authz, workspace/tenant model,
    deployment & CI/CD, secrets, logging/metrics/tracing. Ongoing through Phases 2–3.

- [ ] **Step 8 — Roadmap Epic 6: Backend Execution Runtime & Sandboxing** · `colony-mind-server`
  - Deps: Steps 1–2 (wraps the reference executor), Step 7. FastAPI gateway, Celery workers,
    container-per-session sandboxing, resource caps, streamed logs/progress over WebSocket.
  - **Highest-severity risk area** — sandboxing is a first-class deliverable here.

- [ ] **Step 9 — Roadmap Epic 7: DAG Caching & Incremental State Management** · `colony-mind-server`
  - Deps: Step 8 (pairs tightly with it). Per-node execution hash (config + upstream hashes +
    SDK version), backward dependency tracing, invalidation, tiered artifact store
    (Redis metadata + disk/object store for large artifacts).

- [ ] **Step 10 — Roadmap Epic 9: Data Connectors & Credential Management** · `colony-mind-server`
  - Deps: Steps 1, 8. Connector framework + first connectors (Postgres/SQL, CSV/Parquet
    upload, object store); secrets kept out of the IR, stored per workspace.

- [ ] **Step 11 — Roadmap Epic 8: Result Rendering & In-Node Visualization** · `colony-mind-canvas` + `colony-mind-server` *(split)*
  - Deps: Steps 5, 8, 9. Renderable result payloads (server shapes heavy artifacts; client
    renders small/interactive), in-node tables/charts/profiling HTML, truncation/pagination.
  - Also: **Epic 14 migrations mature here** as the schema evolves under real saved projects.

> **End of Phase 2 milestone:** the infinite canvas feels live — edit a param, only the
> affected subgraph re-runs, results render in the nodes.

---

## Phase 3 — Frontier (DL, GenAI, agents, multiplayer)

> Deliverable: visual deep learning with shape validation, visual agent orchestration, the
> natural-language canvas agent, and real-time collaboration.

- [ ] **Step 12 — Roadmap Epic 10: Deep Learning Module & Tensor Shape Resolution** · `colony-mind` + `colony-mind-canvas` *(split)*
  - Deps: Steps 1, 2, **3** (specializes the structural type framework), 8. PyTorch layer
    nodes, declarative `nn.Module` codegen, real-time shape inference (meta-tensor/FakeTensor
    tracing), shape-mismatch UI. Adds dimension inference on top of Step 3's structural typing.

- [ ] **Step 13 — Roadmap Epic 11: GenAI & Multi-Agent Orchestration** · all three repos
  - Deps: Steps 1, 2, 8; benefits from Step 11. Provider-agnostic LLM nodes, prompt/router
    nodes, agent-group nodes, LangGraph codegen, live message/token viz, cost & token
    tracking. LLM nodes break the deterministic cache — needs a cache-with-care path.

- [ ] **Step 14 — Roadmap Epic 12: Canvas-Aware Coding Agent (NL → graph)** · `colony-mind`/`colony-mind-server` + `colony-mind-canvas`
  - Deps: Steps 1, 6, 3; ideally 8–11. The agent emits **validated IR mutations** (not free
    text), grounded in the node catalog + type system, with propose-then-apply UX. Quality is
    bounded by the catalog (Step 6) and the type system (Step 3) — do it after they mature.

- [ ] **Step 15 — Roadmap Epic 13: Real-Time Multiplayer Collaboration** · `colony-mind-canvas` + `colony-mind-server` *(split)*
  - Deps: Steps 1 (IR must be CRDT-friendly), 5, 8. Concurrent editing (CRDT/OT), presence,
    cursors, comments, IR conflict resolution. Schedulable flexibly (a "Phase 2.5" candidate)
    **only if** the IR was designed CRDT-ready in Epic 1 — verify before investing.

---

## Sequencing notes for a solo dev

- **Two unavoidable toolchain switches:** Python (`uv`/`ruff`/`mypy`/`pytest`) for Steps 1–4,
  then TypeScript (`npm`/Vite/Vitest) at Step 5, then back to Python + server infra at Step 7.
  Steps are ordered to cluster same-repo work and minimize ping-pong.
- **Step 3 is the current frontier** and the gate for almost everything visual: the canvas
  (Step 5) needs its rules-as-data, and DL shape validation (Step 12) specializes it. Finish
  it before starting the canvas in earnest.
- **Epics that span phases:** Epic 14 (persistence) appears at Step 4 (basic) and matures at
  Step 11 (migrations); Epic 15 (infra) starts at Step 7 and runs continuously through Phase 3;
  Epic 4 (node library) is continuous after its first slice at Step 6.
- **Where parallelism would help a team but not a solo dev:** Epic 5 alongside 1/3, Epic 9
  alongside 6, Epic 14 alongside 1/2, Epic 15 alongside 6, Epic 13 anytime after the IR is
  CRDT-ready. A solo dev linearizes these as above; a second pair of hands could fork them off.

---

## Progress at a glance

| Done | In progress | Not started |
| :-- | :-- | :-- |
| Roadmap Epics **1, 2** (repo Epics 1–2) | Roadmap Epic **5** (repo Epic 3 — Stories 1–2 done, Story 3 active) | Roadmap Epics **3, 4, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15** |

**2 of 15 epics complete; 1 in progress.** Next concrete milestone: finish repo Epic 3
(roadmap Epic 5) Stories 3–8 to unblock the frontend canvas.

---

*Keep this in sync with [`technical_roadmap.md`](./technical_roadmap.md) (the source of truth
for scope/decisions) and [`../epics/README.md`](../epics/README.md) (the numbering map). Tick a
step's box when its epic's Definition of Done is met.*
