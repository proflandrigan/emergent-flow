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

- [x] **Step 3 — Roadmap Epic 5: Type-Safe Graph & Connection Validation** · `colony-mind` · *repo Epic 3*
  - Deps: Steps 1–2. The type-token system, compatibility rules, whole-graph inference,
    `cm.validate`, and the rules-as-data artifact the canvas consumes.
  - Status: **done** — Stories 1–8 merged to `main` (ADRs 0011/0012, type registry/catalog,
    compatibility + cardinality engine, graph inference, `cm.validate`, shared codegen/execute
    gate, rules-export artifact, golden diagnostics corpus).
  - **Unblocks Step 4:** the rules-as-data artifact (Story 7) is published, so the canvas can
    now wire real live validation.

- [ ] **Step 4 — Roadmap Epic 3: Frontend Canvas Engine** · `colony-mind-canvas`
  - Deps: Steps 1, 2, **3** (consumes IR schema + `compile_to_code` output + rules-as-data;
    never `import colonymind`). React Flow canvas, pan/zoom, edge drawing, grouping,
    schema-driven config panels, in-node "show code" view, live red-edge validation.
  - **Toolchain switch:** first work in the `npm`/Vite/Vitest repo. All three SDK contracts it
    consumes have now landed — this is unblocked and is the fastest path to a usable UI.

- [ ] **Step 5 — Roadmap Epic 4: Node Library & Configuration UX** · `colony-mind-canvas` + `colony-mind` *(split)*
  - Deps: Steps 1–3, 4. The end-to-end vertical slice (load → clean → one stats test → one
    model → HTML report), node palette/search, defaults & help text. SDK owns node
    catalog/defaults; canvas owns the config-panel surface. Treat as continuous after the
    first slice.

> **End of Phase 1 milestone:** canvas → valid IR → downloadable, runnable Python, zero
> backend. The strongest early de-risking demo.

---

## Phase 2 — Living Bridge (reactive backend)

> Deliverable: "Execute" runs real Python, with incremental caching and rich results rendered
> back into the canvas. Introduces the third repo, `colony-mind-server`.

- [ ] **Step 6 — Roadmap Epic 15: Platform Infrastructure, Security & Observability** · `colony-mind-server` (+ deploy infra)
  - Deps: underpins Steps 7–15. Stand up first: authn/authz, workspace/tenant model,
    deployment & CI/CD, secrets, logging/metrics/tracing. Ongoing through Phases 2–3.

- [ ] **Step 7 — Roadmap Epic 6: Backend Execution Runtime & Sandboxing** · `colony-mind-server`
  - Deps: Steps 1–2 (wraps the reference executor), Step 6. FastAPI gateway, Celery workers,
    container-per-session sandboxing, resource caps, streamed logs/progress over WebSocket.
  - **Highest-severity risk area** — sandboxing is a first-class deliverable here.

- [ ] **Step 8 — Roadmap Epic 7: DAG Caching & Incremental State Management** · `colony-mind-server`
  - Deps: Step 7 (pairs tightly with it). Per-node execution hash (config + upstream hashes +
    SDK version), backward dependency tracing, invalidation, tiered artifact store
    (Redis metadata + disk/object store for large artifacts).

- [ ] **Step 9 — Roadmap Epic 14: Project Persistence, Versioning & Git Sync** · `colony-mind` + `colony-mind-server` *(split)*
  - Deps: Steps 1–2 (SDK half: export format + schema-migration scaffolding), Step 7 (server
    half: project storage needs the server to exist), Step 8 (versioning interacts with the
    cache hash, which includes the SDK version). Basic save/load, one-way Git export of
    generated code, schema-migration scaffolding.
  - **Moved out of Phase 1** (was the old Step 4): nothing on the path to a usable package or
    UI depends on it, the IR is already serializable (Step 1) and `cm.export_script` already
    emits runnable code (Step 2), and the server-side storage half cannot be built until the
    server exists here in Phase 2.
  - **Caveat:** keep bumping `Graph.schema_version` on every wire-format change in the
    meantime, so the migration scaffolding has an intact version history to work from when it
    lands. Migrations continue to *mature* through Step 11 as the schema evolves under real
    saved projects.

- [ ] **Step 10 — Roadmap Epic 9: Data Connectors & Credential Management** · `colony-mind-server`
  - Deps: Steps 1, 7. Connector framework + first connectors (Postgres/SQL, CSV/Parquet
    upload, object store); secrets kept out of the IR, stored per workspace.

- [ ] **Step 11 — Roadmap Epic 8: Result Rendering & In-Node Visualization** · `colony-mind-canvas` + `colony-mind-server` *(split)*
  - Deps: Steps 4, 7, 8. Renderable result payloads (server shapes heavy artifacts; client
    renders small/interactive), in-node tables/charts/profiling HTML, truncation/pagination.

> **End of Phase 2 milestone:** the infinite canvas feels live — edit a param, only the
> affected subgraph re-runs, results render in the nodes.

---

## Phase 3 — Frontier (DL, GenAI, agents, multiplayer)

> Deliverable: visual deep learning with shape validation, visual agent orchestration, the
> natural-language canvas agent, and real-time collaboration.

- [ ] **Step 12 — Roadmap Epic 10: Deep Learning Module & Tensor Shape Resolution** · `colony-mind` + `colony-mind-canvas` *(split)*
  - Deps: Steps 1, 2, **3** (specializes the structural type framework), 7. PyTorch layer
    nodes, declarative `nn.Module` codegen, real-time shape inference (meta-tensor/FakeTensor
    tracing), shape-mismatch UI. Adds dimension inference on top of Step 3's structural typing.

- [ ] **Step 13 — Roadmap Epic 11: GenAI & Multi-Agent Orchestration** · all three repos
  - Deps: Steps 1, 2, 7; benefits from Step 11. Provider-agnostic LLM nodes, prompt/router
    nodes, agent-group nodes, LangGraph codegen, live message/token viz, cost & token
    tracking. LLM nodes break the deterministic cache — needs a cache-with-care path.

- [ ] **Step 14 — Roadmap Epic 12: Canvas-Aware Coding Agent (NL → graph)** · `colony-mind`/`colony-mind-server` + `colony-mind-canvas`
  - Deps: Steps 1, 5, 3; ideally 7–11. The agent emits **validated IR mutations** (not free
    text), grounded in the node catalog + type system, with propose-then-apply UX. Quality is
    bounded by the catalog (Step 5) and the type system (Step 3) — do it after they mature.

- [ ] **Step 15 — Roadmap Epic 13: Real-Time Multiplayer Collaboration** · `colony-mind-canvas` + `colony-mind-server` *(split)*
  - Deps: Steps 1 (IR must be CRDT-friendly), 4, 7. Concurrent editing (CRDT/OT), presence,
    cursors, comments, IR conflict resolution. Schedulable flexibly (a "Phase 2.5" candidate)
    **only if** the IR was designed CRDT-ready in Epic 1 — verify before investing.

---

## Sequencing notes for a solo dev

- **Two unavoidable toolchain switches:** Python (`uv`/`ruff`/`mypy`/`pytest`) for Steps 1–3,
  then TypeScript (`npm`/Vite/Vitest) at Step 4, then back to Python + server infra at Step 6.
  Steps are ordered to cluster same-repo work and minimize ping-pong.
- **The canvas (Step 4) is the current frontier.** Step 3 (the type system) is done and was the
  gate for almost everything visual — its rules-as-data is published, so the canvas can wire
  real live validation now. Step 4 is the fastest path to a usable UI on top of the
  already-usable Python package.
- **Epics that span phases:** Epic 14 (persistence) now lands at Step 9 (basic save/load +
  export, once the server exists) and its migrations mature through Step 11 as the schema
  evolves; Epic 15 (infra) starts at Step 6 and runs continuously through Phase 3; Epic 4
  (node library) is continuous after its first slice at Step 5.
- **Where parallelism would help a team but not a solo dev:** Epic 5 alongside 1/3, Epic 9
  alongside 6, Epic 14 alongside 1/2, Epic 15 alongside 6, Epic 13 anytime after the IR is
  CRDT-ready. A solo dev linearizes these as above; a second pair of hands could fork them off.

---

## Progress at a glance

| Done | In progress | Not started |
| :-- | :-- | :-- |
| Roadmap Epics **1, 2, 5** (repo Epics 1–3) | — | Roadmap Epics **3, 4, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15** |

**3 of 15 epics complete.** The Python package is usable today (`cm.compile_to_code`,
`cm.execute`, `cm.validate`, `cm.export_script`). Next concrete milestone: **Step 4 — the
frontend canvas** (roadmap Epic 3, `colony-mind-canvas`), now fully unblocked by the published
IR schema, codegen output, and rules-as-data artifact — the fastest path to a usable UI.

---

*Keep this in sync with [`technical_roadmap.md`](./technical_roadmap.md) (the source of truth
for scope/decisions) and [`../epics/README.md`](../epics/README.md) (the numbering map). Tick a
step's box when its epic's Definition of Done is met.*
