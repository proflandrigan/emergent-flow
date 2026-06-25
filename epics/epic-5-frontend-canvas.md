# Epic 5 — Frontend Canvas Engine

> **Repo ↔ roadmap numbering.** Epic files are numbered by **delivery order in this repo**; the
> [technical roadmap](../planning_docs/technical_roadmap.md) numbers epics **globally**. This
> file is repo **Epic 5** = roadmap **Epic 3** (Frontend Canvas Engine). Note the mirror of the
> existing collision: repo Epic 3 = roadmap Epic 5 (type system), and repo Epic 5 = roadmap
> Epic 3 (this). **Always qualify "repo Epic N" vs "roadmap Epic N"** — see [`epics/README.md`](./README.md).
> This is the first epic delivered in the **`ui/` tree** (TypeScript/React), not the SDK tree,
> but the same repo and one bundled package per [ADR 0013](../docs/adr/0013-single-repo-bundled-ui-topology.md).

> A fluid infinite canvas: node creation, pan/zoom, edge drawing, selection, grouping, and
> schema-driven config panels — that produces valid IR and shows the generated Python. It is the
> fastest path to a *usable* product on top of the already-usable SDK, and it is fully unblocked
> today: all three SDK→canvas contracts (IR JSON Schema, `compile_to_code` output, rules-as-data)
> have landed, **and** the local server (repo Epic 4) already exposes them over localhost, so the
> canvas need not re-implement validation or codegen in TypeScript ([ADR 0013](../docs/adr/0013-single-repo-bundled-ui-topology.md) Decision 5).

**Phase:** 1 (Foundation).
**Lives in:** `ui/` (React / Vite / Vitest — own toolchain, bundled into the wheel).
**Coupling (per [ADR 0013](../docs/adr/0013-single-repo-bundled-ui-topology.md) Decision 3):** the canvas **never** imports `emergentflow`. It consumes the IR JSON Schema (Epic 1), the `compile_to_code` output string (Epic 2), and the rules-as-data artifact (repo Epic 3), and talks to the local server (repo Epic 4) over REST.
**Dependencies:** Epic 1 (IR schema), Epic 2 (codegen output), repo Epic 3 / roadmap 5 (rules-as-data), repo Epic 4 (local server endpoints `/compile` `/validate` `/execute`).
**Blocks:** roadmap Epic 4 (node-config UX surface), Epic 8 (in-node result rendering), Epic 10/11 (shape-mismatch & token-flow UIs), Epic 13 (multiplayer — **hosted**).

---

## Definition of Done (epic-level)

- [ ] An infinite canvas renders nodes/edges with pan/zoom, multi-select, and drag-to-connect — smooth at the dozens-to-hundreds of nodes a real pipeline needs. (Grouping / subgraph nesting is deferred — see the Story 3 deferred item.)
- [ ] Config panels are **generated from each node's declared param schema** (Epic 1), not hand-coded per node.
- [ ] The canvas produces and reads **valid IR** (validated against the published JSON Schema) with no Python present in the client.
- [ ] An in-node **"show code"** panel renders the Python from the server's `/compile` for the current graph.
- [ ] **Live connection validation**: incompatible edges go red with an explainable reason, via `/validate` (and/or the rules-as-data artifact).
- [ ] A user can **download the runnable script** and (minimally) **execute** the graph via `/execute` and see raw results in-node (rich rendering is roadmap Epic 8).
- [ ] The canvas **never imports `emergentflow`**; the CI boundary check (repo Epic 4 Story 5) passes.
- [ ] Performance: a documented budget with a plan (virtualization / level-of-detail) — verified later against a synthetic large graph, not gold-plated up front.

---

## Story 1 — Lock the canvas architectural decisions

> Mirror how Epics 1 & 2 fixed their decisions first. Cheap to decide, expensive to retrofit.

- [ ] **Canvas library: React Flow (@xyflow)** vs. Rete.js — recommend React Flow (React-native, strong node-editor primitives), per roadmap §F item 6. Record the choice (an ADR or a `ui/` decision note).
- [ ] **Server-backed vs. client-ported logic:** the canvas calls the local server's `/compile` and `/validate` rather than re-implementing codegen/validation in TS (ADR 0013 Decision 5). Record this; treat the rules-as-data client validator as a *later* latency optimization, not a Phase-1 requirement.
- [ ] **Config panels are schema-driven** from the node param schema — decide the JSON-Schema→form mapping approach.
- [ ] **Performance budget**: state the target node count and the virtualization/LOD strategy up front, but defer the actual perf hardening (Story 9).
- [ ] **State model**: pick the client state container and confirm the in-memory canvas model serializes 1:1 to the IR (CRDT-friendliness is a design intent to preserve, not build — roadmap §F item 4).

---

## Story 2 — `ui/` tree scaffold & toolchain

> Stand up the second toolchain in the one repo (ADR 0013) without disturbing the Python gates.

- [ ] Create `ui/` with `package.json`, Vite, Vitest, TypeScript, lint/format config — independent of the `uv`/`ruff`/`mypy`/`pytest` toolchain.
- [ ] Add a Node CI job to `.github/workflows/ci.yml` (build + unit tests + lint), running alongside the Python matrix.
- [ ] Land the **CI boundary check** stub (repo Epic 4 Story 5): `ui/` must not import `emergentflow`.
- [ ] Generate/consume TypeScript types from the **published IR JSON Schema** so the client and IR can't drift.
- [ ] A trivial "hello canvas" page renders and the dev server proxies to `emergentflow serve` on localhost.

---

## Story 3 — Canvas runtime: nodes, edges, interaction

- [ ] Node and edge rendering with an extensible node component framework.
- [ ] Pan/zoom, multi-select, drag-to-create-edge, delete, and an undo/redo stack.
- [ ] A node palette / search to add nodes from the catalog (param schema drives the rest).
- [ ] Vitest coverage of the IR-producing interactions (add node, connect).
- [ ] **Deferred (after the loop):** grouping / subgraph nesting + collapse. The IR already
  models subgraphs, so this is a UI affordance, not an IR change — and it is **not** on the
  canvas→IR→code→execute critical path (Story 8). Pick it up once the loop is demoable.

---

## Story 4 — Schema-driven config panels

- [ ] Render a per-node config form from the node's declared param schema (types, defaults, help text, validation hints).
- [ ] Two-way bind form values to the node's params in the IR model.
- [ ] Surface param-level validation hints (from the node spec) inline.
- [ ] Keep panels consistent and catalog-scalable — no bespoke form per node.

---

## Story 5 — Produce & read valid IR

- [ ] Serialize the canvas model to IR JSON that validates against the published schema; deserialize an IR back onto the canvas.
- [ ] Surface a clear, first-class error on **schema/rules version mismatch** (ties to roadmap Epic 14 migrations).
- [ ] Round-trip test: build a graph on the canvas → IR → reload → identical canvas.

---

## Story 6 — In-node "show code" panel

- [ ] On selection (or a panel toggle), `POST` the current IR to the local server `/compile` and render the returned Python with syntax highlighting.
- [ ] Keep it read-only (one-way per ADR 0001 — no code→graph parsing).
- [ ] Debounce/refresh as the graph changes; handle the server's JSON error shape gracefully.

---

## Story 7 — Live connection validation (red edges)

- [ ] As edges are drawn, validate via `/validate` (and/or the rules-as-data artifact) and mark incompatible edges red with the diagnostic reason on hover.
- [ ] Block or warn per the strictness policy (hard-block structural; warn on runtime-only-knowables — roadmap Epic 5 notes).
- [ ] Render the `Diagnostics` payload (the same JSON the SDK and server produce) so client and server agree on verdicts.
- [ ] Distinguish "tensor dims" (roadmap Epic 10, later) from structural typing — structural only here.

---

## Story 8 — Download script & minimal execute

> The Phase-1 milestone: canvas → valid IR → downloadable, runnable Python — plus a first taste
> of live execution now that the local server exists.

- [ ] "Download `.py`" exports the `/compile` output as a runnable script.
- [ ] "Execute" `POST`s the IR to `/execute` and shows **raw** results per node (rich in-node tables/charts are roadmap Epic 8 — keep this minimal).
- [ ] Node status colouring from the server's per-node ok/error result (repo Epic 4 Story 2).
- [ ] End-to-end demo: build the vertical-slice graph on the canvas, show code, download, execute, see results.

---

## Story 9 — Performance pass (deferred until the loop is proven)

> Explicitly **after** the loop works — do not gold-plate perf before there's anything to demo.

- [ ] Define and measure against a synthetic large graph (e.g. 1,000 nodes).
- [ ] Virtualize off-screen nodes; render simplified nodes when zoomed out (LOD).
- [ ] Lazy/collapsible heavy in-node views (pairs with Epic 8).
- [ ] Record the perf budget results; only invest further if a real graph misses it.

---

## Notes / Risks (carry into planning)

- **The canvas's quality ceiling is the published SDK contract.** The IR schema, codegen output, and rules-as-data are all landed and versioned, and the local server (repo Epic 4) serves them — build against those, and surface version mismatches as first-class errors.
- **Don't re-implement Python in TypeScript.** ADR 0013 Decision 5: call the local server for codegen/validation. The client-side rules validator is a *later* optimization, not a Phase-1 gate.
- **Sequence the loop before the polish.** Stories 1–8 deliver the demoable canvas→IR→code→execute loop; grouping/subgraph nesting (Story 3 deferred item), Story 9 (perf), and rich result rendering (Epic 8) come after — pragmatism over edge cases (§A6).
- **Keep the coupling invariant honest.** The CI boundary check (repo Epic 4 Story 5) is the discipline that replaces the old repo wall — land it with the `ui/` scaffold, not after.
- **Multiplayer is hosted (Epic 13).** Keep the IR/canvas model CRDT-friendly as a design intent, but do not build collaboration here.

---

*How to use this file: tick each `- [ ]` to `- [x]` as work completes. A story is done when all
its tasks are checked; the epic is done when the Definition of Done checklist is complete.*
