# ADR 0019 — Graph sessions and agent collaboration: stateful sessions beside a stateless IR

- **Status:** Accepted
- **Date:** 2026-07-08
- **Deciders:** SDK maintainers (proflandrigan)

## Context

Repo Epic 14 introduces the first **collaborative** surface into a product whose superpower is
purity and statelessness. Humans and AI agents will co-author one graph — an agent can propose
extensions, review human-built flows, and attach findings, while a human can accept, reject, or
edit proposals on the canvas.

Today the product is deliberately stateless: every `/compile`, `/validate`, `/execute` request
carries the whole graph in the body, and the live graph exists only in the browser's Zustand store
(`ui/src/store/graphStore.ts`). There is no server-side document for an agent to read or write.
For two parties to share a live graph, *something* must own a shared document.

This introduces several one-way doors that must be decided up front:

1. **Where does collaboration state live?** On the `Graph` IR model — or beside it?
2. **How do concurrent writers avoid corrupting the graph?** CRDTs, OT, or something simpler?
3. **How does an agent reach the canvas?** Embedded Python API, MCP, plain HTTP?
4. **Where is gate/review policy enforced?** In the pure functions — or at the routes?
5. **What is the trust boundary?**
6. **Does the base install gain new dependencies?**

The design is argued in detail in
[`planning_docs/shards-marriage-plan.md`](../../planning_docs/shards-marriage-plan.md) (rev 2);
this ADR records the decisions as decided and names the invariants they rest on.

## Decision

### The works-without-agents invariant

**The package and app must work identically with or without agents.** This is the epic's central
requirement and is enforced (Story 11 regression suite), not merely asserted. Concretely:

- The base install gains **zero** new hard dependencies.
- The canvas defaults to solo mode; a graph never touches a session unless the user opens one.
- All new server routes are additive; existing route contracts are byte-identical.
- `compile_to_code` / `execute` / `ef.validate` are untouched.
- CI never calls a live LLM.
- `import emergentflow` stays light — `emergentflow/collab/` is never eagerly imported.
- No code path outside an explicit user action ever constructs an LLM client.

Sessions, proposals, reviews, gates, and consults are all **opt-in, additive layers**.

### 1. Collaboration state lives beside the graph, never on it

All collaboration state — `GraphMutation` proposals, `GraphSession` documents,
`CollaborationState` (gates, review threads), and the knowledge base — lives in its own models
*beside* the graph IR. No new field is added to `Graph`, `Node`, or `Edge`;
`CURRENT_SCHEMA_VERSION` (`emergentflow/ir/graph.py:30`) does not bump; no migration step is
registered; `ui/src/generated/ir.schema.json` is unchanged.

**Why the rejected alternative (`gates:`/`knowledge:`/`proposals:` as `Graph` fields) is wrong:**

- Any new `Graph` field bumps `CURRENT_SCHEMA_VERSION`, requires a `register_migration` step
  (`emergentflow/ir/migrate.py`), regenerates `ui/src/generated/ir.schema.json` + TS types, and
  — since the IR models are `extra="forbid"` — makes new graphs rejected by every older
  deployment.
- Two semantically identical pipelines must not serialize differently because of collaboration
  history. The IR is a pure description of *what a pipeline does*, not *who reviewed it*.

The collaboration models (`GraphMutation`, `GraphSession`, `CollaborationState`) are pydantic
models in their own modules (`emergentflow/ir/mutation.py`, `emergentflow/collab/`), with their
own JSON Schemas emitted by `scripts/export_ui_contracts.py` into `ui/src/generated/`, validated
in the UI with the same ajv pattern as `ir.schema.json`.

### 2. Session model and concurrency: optimistic concurrency with monotonic versioning

A `GraphSession` document is the shared artifact a canvas and agents both talk to:

```
GraphSession {
    id: str
    graph: Graph               -- current accepted state
    version: int               -- monotonic; bumps on every accepted change
    proposals: list[Proposal]  -- pending/decided agent proposals
    collab: CollaborationState -- gates, review threads
}
```

Concurrency control is **optimistic, monotonic-version-based**:

- Writers send an expected `version` (the `If-Match` pattern); a mismatch returns a typed 409
  (`stale_version`), never a silent overwrite.
- `GraphMutation` proposals carry `base_version` so stale agent work is detected and rejected,
  not silently applied to a graph that moved since the agent read it.
- The session version bumps on every accepted mutation.

**Rejected alternative: CRDT/OT real-time merge.** Optimistic concurrency is sufficient for the
target workload (one human + one-to-few advisory agents, not simultaneous multi-cursor editing).
CRDTs are future work for a hosted multi-user tier and are recorded as such.

Storage follows ADR 0004: in-memory dict for the local single-user server (same tier as the
report store at `emergentflow/server/app.py`); Redis in a hosted product. Sessions and
collaboration state are metadata, never artifact-tier.

### 3. Agent surface: HTTP first, MCP second

The agent-facing API is additive session routes on `create_app` plus three existing routes
(`GET /catalog`, `POST /validate`, `POST /compile`).

Session routes:
- `POST /sessions` / `GET /sessions` / `GET /sessions/{id}` / `DELETE /sessions/{id}`
- `PUT /sessions/{id}/graph` (with expected version, 409 on mismatch)
- `POST /sessions/{id}/proposals` (validates via `propose_diagnostics`, 409 on stale
  `base_version`)
- `POST /sessions/{id}/proposals/{pid}/accept` and `/reject`
- `GET /sessions/{id}/events` (SSE stream reusing the `_sse_frame` machinery from
  `/execute/stream`)

An MCP wrapper (`fastmcp`/`fastapi-mcp`) ships behind an optional `emergentflow[mcp]` extra —
never on the base install path. The MCP tools delegate to the same service functions as the HTTP
routes: one behavior, two doors.

**Shards is not a dependency in either direction.** Personas are markdown files that a
Shards/Claude Code install consumes; the server knows only HTTP clients. No emergentflow code
imports Shards; no Shards code imports emergentflow.

### 4. Gate policy is route-level

`ef.validate`, `compile_to_code`, and `execute` stay pure and gate-ignorant. Gate enforcement
is a session-route concern:

- A session-scoped `/sessions/{id}/compile` or `/sessions/{id}/execute` with open gates returns
  409 with the open-gate list.
- The payload-only `/compile` and `/execute` used by solo canvas and CI are **untouched** — they
  know nothing about sessions or gates.

This keeps the purity invariant (ADR 0002) intact by construction: the pure functions never
read workflow state, and a graph without a session compiles instantly, as today.

### 5. Trust boundary

Session routes ship on the localhost-bound server (`serve`, `emergentflow/server/app.py`). The
trust model:

- **Localhost (`127.0.0.1`):** open by default — the same Jupyter-style trust model the existing
  routes already use.
- **Non-local bind:** a bearer-token check is required. This ships with the session routes so
  non-local deployment is a configuration change, not a security retrofit.

Sessions + collaboration state are metadata (ADR 0004 metadata tier); nothing here touches the
artifact store.

### 6. Persona integration modes: Mode A and Mode B

Two honest integration modes, named and separated:

- **Mode A — full agent (interactive):** a real Shards/Claude Code agent, running its own
  persona prompt and hooks, reaches the canvas through the HTTP/MCP tools (§3). It keeps its own
  gates, knowledge ledger, and cross-review discipline intact. Emergent-flow supplies the typed
  artifact and the collaboration surface; the agent keeps its own workflow. This is the true
  marriage. Zero emergent-flow code embeds an agent.

- **Mode B — one-shot consult (embedded):** for fast, targeted asks ("fill in this node's
  params"), the server calls a persona's `system_prompt` through the existing `LLMClient` seam
  (ADR 0017; `GatewayClient` live, `ReplayClient` in CI). Mode B is a *flavored LLM call* — it
  has no gates, no ledger, no cross-review. Useful for latency-sensitive affordances, but
  honestly labeled in UX and docs as distinct from Mode A.

The persona catalog (`AgentPersona`) is a flat registry, explicitly *not* the node registry.
`@register` takes `NodeDefinition` subclasses with `codegen`/`execute` contracts; a persona is a
prompt. The two are different contracts and must not be conflated.

## Consequences

**Easier / positive**

- The IR wire format is untouched — no migration, no schema-version bump, no blast radius to
  older deployments. Collaboration is purely additive.
- `compile_to_code`, `execute`, `ef.validate` stay pure. Agents are graph *producers*, never a
  third consumer path — an accepted proposal is an ordinary graph, and ADR-0002 needs no new
  gate cases.
- The works-without-agents invariant is enforced by a regression suite (Story 11), not by
  discipline. A solo-canvas graph round-trips byte-identically to today.
- The `Diagnostic` model (with `INFO` severity and `source` field) lets agent review findings and
  validator findings share one rendering path — no parallel annotation system.
- Mode A (agent over HTTP) and Mode B (server-side consult) are cleanly separated; each can ship
  and be tested independently.

**Harder / negative**

- The session document introduces **shared mutable state** into a codebase whose superpower is
  purity. `base_version` + monotonic versioning + typed 409s contain it, but the concurrent-writer
  tests (Story 3) are load-bearing, not box-ticking.
- Session-scoped operations (compile/execute with gate checks, proposal acceptance) are a new
  server surface to maintain alongside the existing stateless routes.
- Review findings arrive asynchronously (seconds-to-minutes after the human moved on); they must
  anchor to the `base_version` they were computed against and render staleness honestly, which
  is a UX problem the canvas must solve.

**Deferred**

- **Autonomous research loop** (plan §7) — gated on Epic 6 sandboxing + execution cost metering.
  An unattended loop executing generated candidate graphs is the sandbox's core use case; do not
  prototype it against the unsandboxed executor.
- **Multi-human / multi-agent simultaneous editing** — CRDTs/OT for a hosted multi-user tier.
  Optimistic concurrency is sufficient for one human + advisory agents.
- **Knowledge base dedup/versioning/GC** — start with slug-uniqueness and manual curation; the
  costs are real and deferred until usage demands them.
- **Auto-consultation triggers** (agents firing on node drop) — deferred until latency and
  annoyance are understood from manual consults.
- **Embedding Shards as a dependency** — explicitly rejected. Persona files are the coupling
  surface; if tighter integration is needed later, that is a new decision.
