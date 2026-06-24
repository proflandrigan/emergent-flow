# ADR 0014 — Frontend canvas architecture: library, state, panels, and delivery

- **Status:** Accepted
- **Date:** 2026-06-24
- **Deciders:** Colony Mind core team

## Context

Epic 5 Story 1 ("Lock the canvas architectural decisions") requires fixing the canvas's
foundational choices before any `ui/` code is written — mirroring how Epics 1 and 2 fixed the
IR and codegen decisions first, because they are cheap to decide now and expensive to retrofit
once nodes, edges, and panels exist on top of them.

[ADR 0013](0013-single-repo-bundled-ui-topology.md) already fixed the *topology*: a single
repo, a single bundled package, and a coupling invariant where `ui/` never imports `colonymind`
and only the IR JSON Schema, the `compile_to_code` output string, and the rules-as-data
artifact ([ADR 0012](0012-rules-as-portable-data.md)) cross the boundary; everything else talks
to the local server over REST. ADR 0013 Decision 5 further established that, because the local
server can call the real `cm.validate` / `cm.compile_to_code` over localhost, the canvas does
not need to reimplement codegen or validation in TypeScript for Phase 1.

What ADR 0013 left open is the *internal* architecture of the canvas itself: which
node-editor library renders the graph, what state container backs the canvas model and how
that model relates to the IR, how per-node config panels are generated from the node contract
([ADR 0005](0005-node-definition-contract.md)), how the catalog and schema actually reach the
client, and what performance posture the canvas takes before any real graph exists to measure
against. Each of these has a small number of well-understood options and a clear preferred
answer given the constraints already locked (server-backed logic, no Python in the client,
IR as the single source of truth — [ADR 0001](0001-graph-is-single-source-of-truth.md)). This
ADR fixes those five choices so Stories 2–9 build against a stable foundation instead of
re-litigating them mid-implementation.

## Decision

We will fix the following five architectural decisions for the Epic 5 canvas:

1. **Canvas library: React Flow (`@xyflow/react`).** We will build the canvas on React Flow
   rather than Rete.js. React Flow is React-native (no adapter layer between the rendering
   library and the rest of the `ui/` React tree) and ships strong node-editor primitives —
   pan/zoom, multi-select, drag-to-connect, custom node/edge components — that map directly
   onto the Epic 5 Definition of Done. This follows the roadmap's §F item 6 recommendation.
   This choice is final for Phase 1; it is not revisited absent a concrete blocking limitation.

2. **Server-backed logic, not client-ported.** We will call the local server's `/compile`,
   `/validate`, and `/execute` endpoints rather than reimplementing codegen or validation in
   TypeScript, per [ADR 0013](0013-single-repo-bundled-ui-topology.md) Decision 5. The
   rules-as-data client validator described in [ADR 0012](0012-rules-as-portable-data.md) is
   an explicit *later* latency optimization for instant offline edge feedback — it is **not**
   a Phase-1 requirement. Story 7 (live connection validation) ships against `/validate` first;
   adopting the rules-as-data artifact client-side is deferred until the round-trip latency is
   shown to matter.

3. **State container: Zustand, with pure `toIR()` / `fromIR()` mappers.** We will hold the
   canvas model in a single normalized Zustand store shaped as `{ nodes, edges, params }`. Two
   pure functions, `toIR()` and `fromIR()`, convert the store to and from the IR 1:1 — the
   store is never a divergent shadow copy of the graph. We choose Zustand because it is
   minimal, the store is plain serializable objects that map directly onto the IR (no class
   instances, no hidden behaviour), it keeps the bundle small, and a plain-object store stays
   CRDT-friendly: it can later sit underneath a Yjs document (roadmap §F item 4) without a
   rewrite. CRDT support itself is a design intent to preserve, not something built in this
   epic.

4. **Config panels: schema-driven via a custom lightweight renderer.** We will generate each
   node's config panel from a small switch over the declared param types (number, string,
   bool, enum), driven by that node's `NodeSpec.params` and `ValidationHints` — the JSON-able
   half of the node contract fixed in [ADR 0005](0005-node-definition-contract.md). We choose
   a custom renderer over `react-jsonschema-form` to avoid a heavy dependency and its theming
   friction for what is, today, a small and stable param vocabulary. This decision is locked
   now; the panels themselves are built in Story 4, not in this story.

5. **Catalog and schema delivery: both a build-time artifact and runtime endpoints.** We will
   ship the IR JSON Schema and node catalog to the client two ways:
   - **Build time:** a Python script dumps `Graph.model_json_schema()` and `registry.specs()`
     into `ui/src/generated/`, from which the client codegens TypeScript types. This makes the
     client types unable to drift from the IR without a regeneration step surfacing it.
   - **Runtime:** the local server exposes `GET /schema` and `GET /catalog` so the live node
     palette and config panels always reflect the catalog of the server actually running,
     including any out-of-tree plugin nodes ([ADR 0006](0006-node-registry-and-plugin-discovery.md))
     registered only at runtime.
   The build-time artifact buys compile-time drift-safety for the TypeScript types; the
   runtime endpoints buy live data the build artifact cannot provide. We need both, not one.

6. **Performance budget: state the target and strategy now, defer hardening.** We will target
   smooth interaction (pan/zoom/select/drag) at the dozens-to-hundreds of nodes a real pipeline
   needs, not at synthetic extremes. The stated strategy, if and when the target is missed, is
   virtualization of off-screen nodes plus level-of-detail rendering (simplified nodes when
   zoomed out). We will not build either mechanism now: Story 9 measures against a synthetic
   large graph and implements hardening only if the budget is actually missed, per the epic's
   explicit sequencing (loop first, polish after).

## Consequences

**Positive:**

- Stories 2–9 build against five settled answers instead of re-deciding library, state shape,
  panel strategy, schema delivery, or performance posture mid-implementation — the same payoff
  Epics 1 and 2 got from fixing the IR and codegen decisions early.
- The Zustand store's 1:1 mapping to the IR via `toIR()`/`fromIR()` keeps
  [ADR 0001](0001-graph-is-single-source-of-truth.md)'s single-source-of-truth invariant
  intact on the client: the canvas model is a faithful, serializable view of the IR, not a
  parallel representation that can drift from it.
- Calling `/compile` and `/validate` instead of porting logic to TypeScript (Decision 2) keeps
  the client thin and avoids a second implementation of codegen/validation semantics that
  would need to be kept in lockstep with the Python originals.
- The custom schema-driven panel renderer (Decision 4) and the dual catalog/schema delivery
  (Decision 5) both scale with the node catalog rather than requiring bespoke client code per
  node type, keeping the canvas catalog-scalable as Story 8 (production node families) grows
  it.
- Stating the performance target and strategy without building it (Decision 6) avoids
  gold-plating a mechanism before there is a real graph to measure it against, consistent with
  the epic's explicit "loop before polish" sequencing.

**Negative / obligations:**

- Two schema/catalog delivery paths (Decision 5) must be kept consistent: the build script and
  the server's `/schema`/`/catalog` endpoints both derive from the same Python sources today,
  but a future change to one without the other would silently desynchronize the generated
  TypeScript types from the live server. Story 2's codegen step and Epic 4's endpoints need a
  shared regeneration discipline, not independent maintenance.
- Deferring the rules-as-data client validator (Decision 2) means Story 7's red-edge feedback
  is bounded by a server round-trip; if that latency proves user-visible before a later epic
  revisits it, this ADR's Phase-1 stance — not the rules-as-data artifact itself — is what
  would need to be reopened.
- The custom config-panel renderer (Decision 4) is more code to own than adopting
  `react-jsonschema-form`, in exchange for a smaller bundle and less theming friction; if the
  param vocabulary grows substantially beyond number/string/bool/enum, that trade should be
  revisited.
- Deferring performance hardening (Decision 6) means Stories 2–8 are not validated against a
  large synthetic graph as they land; a regression introduced before Story 9 may not be caught
  until Story 9's measurement pass.

**Deferred:**

- The rules-as-data client-side validator ([ADR 0012](0012-rules-as-portable-data.md)) as a
  latency optimization for live connection validation — revisit only if `/validate` round-trip
  latency is shown to matter (Decision 2).
- CRDT/Yjs adoption under the Zustand store for multiplayer — a design intent the plain-object
  store shape preserves, not a Phase-1 build item; multiplayer itself is hosted (roadmap Epic
  13) (Decision 3).
- Virtualization and level-of-detail rendering — implemented only in Story 9, and only if the
  stated performance budget is actually missed against a synthetic large graph (Decision 6).
- A shared regeneration mechanism that ties the build-time schema/catalog dump and the runtime
  `/schema`/`/catalog` endpoints to one invocation, so they cannot drift apart — left to Story
  2's scaffold work to wire up mechanically.
