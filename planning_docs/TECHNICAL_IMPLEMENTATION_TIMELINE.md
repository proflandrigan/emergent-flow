# Colony Mind — Technical Implementation Timeline

*A single, linear order in which one developer can complete every epic across the whole
product. Where the [technical roadmap](./technical_roadmap.md) gives a dependency graph with
parallel tracks, this doc flattens it into one sequence you can walk top-to-bottom, switching
trees (and toolchains) within the one repo only when a dependency forces it.*

---

## How to read this

- The roadmap numbers epics **globally** (Epic 1–15). This timeline keeps those roadmap
  numbers as the canonical id and adds a **step number** (the order to actually do them).
- For the three epics delivered in this SDK repo, the **repo-Epic alias** is shown
  (repo Epic 1 = roadmap Epic 1, repo Epic 2 = roadmap Epic 2, **repo Epic 3 = roadmap Epic
  5**). See [`../epics/README.md`](../epics/README.md) for the full numbering map and the
  "Epic 3" collision warning.
- **One repo, three trees** (per [ADR 0013](../docs/adr/0013-single-repo-bundled-ui-topology.md),
  superseding §A5's three-repo split). The product lives in a single repo, `colony-mind`,
  shipping as one bundled `pip install colonymind` (the JupyterLab model): the SDK
  (`colonymind/`), the React/TS frontend (`ui/`), and the FastAPI/Celery backend
  (`colonymind/server/`). Steps below still flag which **tree** each one touches; wherever a
  step names `colony-mind-canvas` or `colony-mind-server`, read "the `ui/` or
  `colonymind/server/` tree of this repo." The contract-only coupling is unchanged — the UI
  never imports the SDK; only the IR schema, codegen output, and rules-as-data cross the
  boundary, now enforced by a CI check rather than a repo wall.

### Status legend

- `[x]` — **done** (merged to `main`, deliverables present in the repo).
- `[~]` — **in progress** (partial; story-level detail noted).
- `[ ]` — **not started.**

---

## Phase 1 — Foundation (SDK + static canvas, no backend execution)

> Deliverable: a frontend-only canvas that maps a node graph to flawless, downloadable
> Python. Two trees in one repo (`colonymind/` and `ui/`; see [ADR 0013](../docs/adr/0013-single-repo-bundled-ui-topology.md)),
> coupled only by the published IR schema, codegen output, and rules-as-data artifact.

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

- [ ] **Step 4 — Roadmap Epic 3: Frontend Canvas Engine** · `ui/` tree
  - Deps: Steps 1, 2, **3** (consumes IR schema + `compile_to_code` output + rules-as-data;
    never `import colonymind`). React Flow canvas, pan/zoom, edge drawing, grouping,
    schema-driven config panels, in-node "show code" view, live red-edge validation.
  - **Toolchain switch:** first work in the `npm`/Vite/Vitest `ui/` tree. All three SDK contracts it
    consumes have now landed — this is unblocked and is the fastest path to a usable UI.

- [ ] **Step 5 — Roadmap Epic 4: Node Library & Configuration UX** · `ui/` + `colonymind/` *(split)*
  - Deps: Steps 1–3, 4. The end-to-end vertical slice (load → clean → one stats test → one
    model → HTML report), node palette/search, defaults & help text. SDK owns node
    catalog/defaults; canvas owns the config-panel surface. Treat as continuous after the
    first slice.

> **End of Phase 1 milestone:** canvas → valid IR → downloadable, runnable Python, zero
> backend. The strongest early de-risking demo.

---

## Phase 2 — Living Bridge (reactive backend)

> Deliverable: "Execute" runs real Python, with incremental caching and rich results rendered
> back into the canvas. Introduces the backend tree, `colonymind/server/` (per [ADR 0013](../docs/adr/0013-single-repo-bundled-ui-topology.md); formerly the separate `colony-mind-server` repo).
>
> **Happy path — local and in-process (no over-architecting).** On the bundled package's path,
> Phase 2 is a *thin local* FastAPI server (`cm lab` / `colonymind serve`) that calls
> `cm.execute(ir)` **in-process** on localhost — the JupyterLab/dbt-core tier. The reference
> executor is already pure ([ADR 0002](../docs/adr/0002-execute-the-ir-not-the-string.md)), so
> in-process execution is correct and trivially "what-you-see-is-what-runs." The enterprise
> build-out below — Celery/distributed workers, container-per-session sandboxing, Redis +
> object-store tiering, auth/multi-tenancy/deploy — is **deferred to the gated hosted product**
> (the dbt-Cloud tier, proprietary per [ADR 0007](../docs/adr/0007-open-core-licensing-boundary.md)).
> Steps below tag those pieces **(hosted)**; they are not on the bundled package's critical path.

- [ ] **Step 6 — Roadmap Epic 15: Platform Infrastructure, Security & Observability** · `colonymind/server/` (mostly **hosted**)
  - **Happy path:** the bundled local app needs almost none of this. It runs on localhost as a
    single user, so there is **no auth, no tenant model, no deploy pipeline** to stand up — only
    basic local logging and surfacing errors back into nodes. Do *that* much here.
  - **(Hosted)** authn/authz, the workspace/tenant model, managed deployment & CI/CD, secrets,
    and cross-service tracing belong to the gated hosted product and are **deferred** — do not
    stand them up to make local Execute work. The real first Phase-2 deliverable is **Step 7**
    (local in-process execution); this step's hosted half spins up only when the hosted offering
    starts, then runs continuously through Phase 3.

- [ ] **Step 7 — Roadmap Epic 6: Backend Execution Runtime & Sandboxing** · `colonymind/server/`
  - Deps: Steps 1–2 (wraps the reference executor). **Happy path:** a thin local FastAPI server
    (`cm lab` / `colonymind serve`) that calls `cm.execute(ir)` **in-process**, streaming
    logs/progress over WebSocket. No Celery, no broker, **no sandbox** — you run your own code on
    your own machine, the Jupyter trust model. This is the whole "Execute runs real Python" demo.
  - **(Hosted)** Celery/distributed workers, container-per-session sandboxing, resource caps,
    and controlled egress become first-class **and high-severity** the moment code runs on
    shared/hosted infrastructure — deferred to the hosted product. Keep the executor pure
    ([ADR 0002](../docs/adr/0002-execute-the-ir-not-the-string.md)) so the hosted tier can wrap
    it later without retrofitting.

- [ ] **Step 8 — Roadmap Epic 7: DAG Caching & Incremental State Management** · `colonymind/server/`
  - Deps: Step 7 (pairs tightly with it). Per-node execution hash (config + upstream hashes +
    SDK version), backward dependency tracing, invalidation. **Happy path:** a simple in-memory +
    **on-disk** cache keyed by that hash (Parquet/safetensors under a project cache dir) — no
    external services.
  - **(Hosted)** the Redis-metadata + object-store tiering ([A4](./technical_roadmap.md)) and
    cross-user/shared caching are scale-out optimizations, deferred to the hosted product.

- [ ] **Step 9 — Roadmap Epic 14: Project Persistence, Versioning & Git Sync** · `colonymind/` + `colonymind/server/` *(split)*
  - Deps: Steps 1–2 (SDK half: export format + schema-migration scaffolding), Step 7 (server
    half: project storage needs the local server to exist), Step 8 (versioning interacts with the
    cache hash, which includes the SDK version). **Happy path:** basic save/load to **local
    files** (the IR JSON + `cm.export_script` output, both already serializable) and one-way Git
    export of generated code — no project database. A managed/multi-tenant project store is
    **(hosted)**.
  - **Moved out of Phase 1** (was the old Step 4): nothing on the path to a usable package or
    UI depends on it, the IR is already serializable (Step 1) and `cm.export_script` already
    emits runnable code (Step 2), and the server-side storage half cannot be built until the
    server exists here in Phase 2.
  - **Caveat:** keep bumping `Graph.schema_version` on every wire-format change in the
    meantime, so the migration scaffolding has an intact version history to work from when it
    lands. Migrations continue to *mature* through Step 11 as the schema evolves under real
    saved projects.

- [ ] **Step 10 — Roadmap Epic 9: Data Connectors & Credential Management** · `colonymind/server/`
  - Deps: Steps 1, 7. **Happy path:** connector framework + a few local/basic connectors (CSV/
    Parquet upload, local files, one SQL source); secrets kept out of the IR, stored locally
    (e.g., a local secrets file / OS keyring). Per-workspace managed secrets and premium
    connectors are **(hosted)**.

- [ ] **Step 11 — Roadmap Epic 8: Result Rendering & In-Node Visualization** · `ui/` + `colonymind/server/` *(split)*
  - Deps: Steps 4, 7, 8. Renderable result payloads (server shapes heavy artifacts; client
    renders small/interactive), in-node tables/charts/profiling HTML, truncation/pagination.

> **End of Phase 2 milestone:** the infinite canvas feels live — edit a param, only the
> affected subgraph re-runs, results render in the nodes.

---

## Phase 3 — Frontier (DL, GenAI, agents, multiplayer)

> Deliverable: visual deep learning with shape validation, visual agent orchestration, the
> natural-language canvas agent, and real-time collaboration.

- [ ] **Step 12 — Roadmap Epic 10: Deep Learning Module & Tensor Shape Resolution** · `colonymind/` + `ui/` *(split)*
  - Deps: Steps 1, 2, **3** (specializes the structural type framework), 7. PyTorch layer
    nodes, declarative `nn.Module` codegen, real-time shape inference (meta-tensor/FakeTensor
    tracing), shape-mismatch UI. Adds dimension inference on top of Step 3's structural typing.

- [ ] **Step 13 — Roadmap Epic 11: GenAI & Multi-Agent Orchestration** · `colonymind/` + `colonymind/server/` + `ui/` (all three trees)
  - Deps: Steps 1, 2, 7; benefits from Step 11. Provider-agnostic LLM nodes, prompt/router
    nodes, agent-group nodes, LangGraph codegen, live message/token viz, cost & token
    tracking. LLM nodes break the deterministic cache — needs a cache-with-care path.

- [ ] **Step 14 — Roadmap Epic 12: Canvas-Aware Coding Agent (NL → graph)** · `colonymind/` / `colonymind/server/` + `ui/`
  - Deps: Steps 1, 5, 3; ideally 7–11. The agent emits **validated IR mutations** (not free
    text), grounded in the node catalog + type system, with propose-then-apply UX. Quality is
    bounded by the catalog (Step 5) and the type system (Step 3) — do it after they mature.

- [ ] **Step 15 — Roadmap Epic 13: Real-Time Multiplayer Collaboration** · `ui/` + `colonymind/server/` *(split, **hosted**)*
  - Deps: Steps 1 (IR must be CRDT-friendly), 4, 7. Concurrent editing (CRDT/OT), presence,
    cursors, comments, IR conflict resolution. **(Hosted)** — multiplayer is a hosted-product
    feature, not part of the bundled single-user app. Keep the IR CRDT-friendly in Epic 1 so it
    can be added without a rewrite, but do not build sync transport into the bundled package.

---

## Sequencing notes for a solo dev

- **Stay on the happy path; don't over-architect.** The bundled `pip install colonymind` is a
  **single-user, local-first app** (JupyterLab / dbt-core tier, per
  [A6](./technical_roadmap.md) and [ADR 0013](../docs/adr/0013-single-repo-bundled-ui-topology.md)):
  local server, in-process execution, on-disk cache, local-file persistence. The enterprise
  scale-out tagged **(hosted)** above — sandboxed/distributed execution, Redis+object-store
  tiering, auth/multi-tenancy/deploy, multiplayer — is the **future gated hosted product**
  (dbt-Cloud tier) and is *off* the bundled package's critical path. A solo dev ships the local
  happy path end-to-end first and reaches for the heavy machinery only when the hosted offering
  actually needs it.
- **Two unavoidable toolchain switches:** Python (`uv`/`ruff`/`mypy`/`pytest`) for Steps 1–3,
  then TypeScript (`npm`/Vite/Vitest) at Step 4, then back to Python + server infra at Step 6.
  These are now switches between *trees of one repo* ([ADR 0013](../docs/adr/0013-single-repo-bundled-ui-topology.md)),
  not between repos; steps are ordered to cluster same-toolchain work and minimize ping-pong.
- **The canvas (Step 4) is the current frontier.** Step 3 (the type system) is done and was the
  gate for almost everything visual — its rules-as-data is published, so the canvas can wire
  real live validation now. Step 4 is the fastest path to a usable UI on top of the
  already-usable Python package.
- **Epics that span phases:** Epic 14 (persistence) now lands at Step 9 (basic save/load +
  export, once the server exists) and its migrations mature through Step 11 as the schema
  evolves; Epic 15 (infra) is mostly **(hosted)** — only basic local logging is needed for the
  bundled app, the rest starts when the hosted offering does and then runs continuously; Epic 4
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
frontend canvas** (roadmap Epic 3, the `ui/` tree), now fully unblocked by the published
IR schema, codegen output, and rules-as-data artifact — the fastest path to a usable UI.

---

*Keep this in sync with [`technical_roadmap.md`](./technical_roadmap.md) (the source of truth
for scope/decisions) and [`../epics/README.md`](../epics/README.md) (the numbering map). Tick a
step's box when its epic's Definition of Done is met.*
