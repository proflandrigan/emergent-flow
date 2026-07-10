# Epic 14 — Agent Collaboration on the Canvas (humans and agents co-author one graph)

> **Repo ↔ roadmap numbering.** Epic files are numbered by **delivery order in this repo**; the
> [technical roadmap](../planning_docs/technical_roadmap.md) numbers epics **globally**. This file
> is repo **Epic 14**. It delivers the bundled / local happy-path slice of **roadmap Epic 12 —
> the NL→graph agent / AI-assisted authoring**, following the integration design in
> [`planning_docs/shards-marriage-plan.md`](../planning_docs/shards-marriage-plan.md) (rev 2).
> **Do not confuse this with repo Epic 10 (Agentic Flows):** Epic 10 puts agents *inside* the
> graph as nodes the compiler emits; this epic puts agents *outside* the graph as **co-authors** —
> a Shards persona (or any coding agent) that proposes, reviews, and annotates the graph a human
> is building. **Always qualify "repo Epic N" vs "roadmap Epic N"** — see
> [`epics/README.md`](./README.md).

> **The central bet: the graph session is the collaboration surface, and everything else is
> additive.** The product's value rests on two pure functions over one IR (ADR 0001/0002) and a
> deliberately stateless server — every `/compile`, `/validate`, `/execute` carries the whole
> graph in the request body, and the live graph exists only in the canvas's Zustand store
> (`ui/src/store/graphStore.ts`). For a human and an agent to share a live graph, *something*
> must own a shared document — so we introduce **graph sessions** (a server-side
> `GraphSession` document with optimistic concurrency and an SSE event stream) and a
> **`GraphMutation` proposal protocol** (a pydantic model + a pure `apply_mutation`, *not* a
> field on `Graph` — the IR wire format and `CURRENT_SCHEMA_VERSION` are untouched). Agents are
> **producers of ordinary graphs**, never a third consumer path: an accepted proposal flows
> through the same `compile_to_code` / `execute` / `ef.validate` as a hand-built graph, so
> ADR-0002 holds without a single new equivalence case. The agent itself stays where it already
> lives — a Shards persona is a Claude Code agent (markdown prompt + hooks), and it reaches the
> canvas through **plain HTTP tools first, MCP second**; three of the six tools it needs
> (`/catalog`, `/validate`, `/compile`) are existing routes. Two moves the repo already proved
> carry the rest:
> - **Validate-on-propose is the Epic-3 validation pipeline pointed at proposals.** Every
>   incoming `GraphMutation` is applied to a scratch copy and run through `ef.validate`
>   (`emergentflow/codegen/validation.py:263`); the human sees "this proposal type-checks" (or
>   the red/yellow findings) *before* deciding. Agent review findings reuse the same
>   `Diagnostic` vocabulary and the same canvas rendering path — no parallel annotation system.
> - **One-shot persona consults are ADR-0017's injected-client move, unchanged.** Where an
>   embedded "fill in this node's params" consult is wanted, it is a flavored `LLMClient` call
>   (`GatewayClient` live, `ReplayClient` in CI) — never a hidden network effect in the pure core.

**CRITICAL INVARIANT (read this before every story): the package and app must work identically
with or without agents.** No agent, no session, no LLM is required for any existing or new
non-agent workflow. Concretely: the base install gains **zero** new hard dependencies; the
canvas defaults to today's solo mode and a graph never touches a session unless the user opens
one; all new server routes are additive and the existing route contracts are byte-identical;
`compile_to_code` / `execute` / `ef.validate` are untouched; CI never calls a live LLM; and a
dedicated regression suite (Story 11) enforces all of the above permanently. Every story below
carries its own "works-without-agents" task — a story is not done until that box is checked.

**Phase:** Follows repo Epic 7 (the FastAPI server + SSE streaming machinery this epic reuses —
`emergentflow/server/app.py:230` `/execute/stream`), repo Epic 5 (the canvas store/`toIR`
mappers the session mode extends), repo Epic 3 (the validation pipeline + `Diagnostic` model
agent findings reuse), and repo Epic 9 (the `LLMClient` seam Mode-B consults ride). The
Prompt Lab (`ui/src/promptlab/buildEvalGraph.ts`) already builds graphs programmatically
through `toIR` — this epic is the same move, server-side, with an agent as the author.
**Lives in:** `emergentflow/ir/mutation.py` (new — mutation protocol), `emergentflow/collab/`
(new — sessions, collaboration state, persona catalog), `emergentflow/server/` (session routes,
SSE), `ui/src/session/` (new — session mode, proposal UX, review threads), `agents/`
(new, repo root — persona files any Claude Code / Shards install can use), `docs/adr/0019-*`.
**Dependencies:** Epic 1 (IR models, `@register` registry), Epic 2 (`compile_to_code` /
`execute`), Epic 3 (`ef.validate`, `Diagnostic`/`Diagnostics`), Epic 4/7 (FastAPI server, SSE,
`_POST_ROUTES` dispatch), Epic 5 (canvas store, `ui/src/store/ir.ts`, generated contracts via
`scripts/export_ui_contracts.py`), Epic 9 / [ADR 0017](../docs/adr/0017-llm-nodes-injected-effectful-client.md)
(`LLMClient` + `ReplayClient` for Mode-B consults). **New deps: none on the base path.** The
MCP wrapper (Story 7) ships behind an optional `emergentflow[mcp]` extra; Shards itself is
**never a dependency** — persona files are plain markdown that a Shards/Claude Code install
consumes.
**Blocks:** repo Epic 10 (agentic flows — an agent that can *author* graphs is the natural
author of agent-node graphs), the roadmap Epic 12 remainder (hosted multi-user sessions), and
the autonomous-research loop (plan §7 — explicitly deferred here, gated on Epic 6 sandboxing).

---

## Definition of Done (epic-level)

- [ ] **THE PACKAGE AND APP WORK WITH OR WITHOUT AGENTS — enforced, not asserted.** A dedicated
  regression suite (Story 11) proves: the full existing test suite passes with `emergentflow/collab/`
  never imported; a solo-canvas graph round-trips byte-identically to today; every pre-existing
  server route's response is unchanged; `import emergentflow` stays light (no new eager imports);
  the base install carries zero new hard deps (`uv lock` diff reviewed); no code path outside an
  explicit user action ever constructs an LLM client. Sessions, proposals, reviews, gates, and
  consults are all **opt-in, additive layers**.
- [ ] **The IR wire format is untouched.** No new fields on `Graph`/`Node`/`Edge`;
  `CURRENT_SCHEMA_VERSION` (`emergentflow/ir/graph.py:30`) does not bump; no migration step is
  registered; `ui/src/generated/ir.schema.json` is unchanged. All collaboration state
  (`GraphMutation`, `GraphSession`, `CollaborationState`) lives *beside* the graph, serialized
  by its own versioned schemas.
- [ ] **The mutation protocol is pure and conflict-safe.** `GraphMutation` (pydantic, in
  `emergentflow/ir/mutation.py`) carries `base_version` for optimistic concurrency; a pure
  `apply_mutation(graph, m) -> Graph` (the `migrate_to_current` purity discipline —
  `emergentflow/ir/migrate.py:112`) is the single apply path for server, tests, and any future
  CLI; a stale `base_version` is rejected with a typed error, never silently applied.
- [ ] **Validate-on-propose:** every proposal is stored with the `Diagnostics` of the
  post-mutation graph (via `ef.validate`), and the canvas shows the verdict before the human
  accepts. An accepted proposal produces an ordinary graph consumed by the unchanged
  `compile_to_code` / `execute` — **ADR-0002 needs no new gate cases.**
- [ ] **Purity holds everywhere it holds today:** `compile_to_code`, `execute`, `ef.validate`,
  and `apply_mutation` are pure; sessions/gates/knowledge are server-route state (the same
  quarantine line as `codegen/export.py` and the injected clients); gate policy is enforced at
  the session routes (409 on open gates), **never** inside the pure functions.
- [ ] **An agent can collaborate over plain HTTP on day one** (the happy path): create/read a
  session, submit a proposal, await the verdict over SSE — with `GET /catalog`,
  `POST /validate`, `POST /compile` (all pre-existing) rounding out its toolset. A checked-in
  persona file (`agents/`) documents the surface so a Shards / Claude Code agent drives it with
  `curl`, no new infra. MCP is a wrapper over the same routes, behind `[mcp]`, later.
- [ ] **Collaboration is two-way:** the human can ask an agent to build/extend a flow
  (proposal → ghost diff → accept/reject/edit), **and** an agent can review a human-built flow
  (findings as `Diagnostic`-shaped items anchored to `node_id`/`edge_id`, rendered through the
  existing diagnostics path, with optional one-click fix `GraphMutation`s attached).
- [ ] **The `Diagnostic` extension is additive and done once:** `Severity.INFO` and
  `Diagnostic.source` (`"validator"` | persona slug) added with defaults (both models are
  `frozen`/`extra="forbid"` — `emergentflow/codegen/validation.py:42`), mirrored in
  `ui/src/store/validation.ts`, landed early (Story 6) so the `/validate` contract changes once.
- [ ] **The canvas↔SDK coupling stays generated, not hand-mirrored:** `GraphMutation`, session
  documents, and session events get JSON Schemas + TS types emitted by
  `scripts/export_ui_contracts.py` into `ui/src/generated/`, ajv-validated in the UI exactly
  like `ir.schema.json` (`ui/src/store/validateIR.ts:16`), with golden tests on schema stability.
- [ ] **CI never calls a live LLM or requires an agent:** Mode-B consults are tested under
  `ReplayClient` (`emergentflow/llm/replay.py`); Mode-A flows are tested by driving the HTTP
  surface directly from pytest (an agent is just an HTTP client — so the tests *are* the agent).
- [ ] **Trust boundary stated and enforced:** session routes ship on the localhost-bound server
  (`serve`, `emergentflow/server/app.py:436`); a bearer-token check is in place (default: open
  on localhost, required when `host != 127.0.0.1`) so non-local deployment is not a retrofit.
- [ ] **Acceptance demos (Story 12):** (a) **agent builds, human accepts** — a scripted agent
  proposes a two-node extension to a canvas graph; the human sees the ghost diff + clean
  validation verdict, accepts, and the graph compiles + executes; (b) **human builds, agent
  reviews** — the agent posts anchored findings incl. one fix-mutation on a human-built flow;
  the human applies the fix with one click. Both run in CI with the "agent" as a pytest-driven
  HTTP client.
- [ ] **Explicitly out of scope (deferred, with owners):** the autonomous-research loop
  (plan §7 — **gated on Epic 6 sandboxing + the execution cache**, do not start here);
  multi-human / multi-agent simultaneous editing (CRDTs — hosted concern); the knowledge base
  beyond a minimal slug-keyed store (plan §6 dedup/GC noted as real costs); persona
  *marketplaces*; any change to `compile_to_code` / `execute`; embedding Shards itself as a
  dependency.

---

## Story group A — Foundations (the collaboration seam)

## Story 1 — Lock the architecture (ADR 0019 + the works-without-agents contract)

> Cheap to decide, expensive to retrofit. This warrants an ADR: it introduces the first
> **stateful** server surface into a deliberately stateless product, and the one-way doors
> (mutation protocol shape, where collaboration state lives, the trust boundary) are exactly
> the ones rev 2 of the marriage plan flagged. Write **ADR 0019**
> (`docs/adr/0019-graph-sessions-and-agent-collaboration.md`) before building. Most decisions
> are already argued in [`planning_docs/shards-marriage-plan.md`](../planning_docs/shards-marriage-plan.md)
> — the ADR records them as decided.

- [x] **Record the works-without-agents contract as a named invariant** (the epic's CRITICAL
  requirement): agents/sessions are additive; zero new hard deps; solo mode untouched; no
  ambient LLM calls; enforcement via the Story 11 regression suite. Every subsequent design
  choice is checked against it.
- [x] **Collaboration state lives beside the graph, never on it.** Record why `gates:` /
  `knowledge:` / proposals as `Graph` fields are rejected: any new field bumps
  `CURRENT_SCHEMA_VERSION`, forces a `register_migration` step, regenerates
  `ui/src/generated/ir.schema.json` + TS types, and — since the IR models are `extra="forbid"`
  — makes new graphs rejected by every older deployment; and two semantically identical
  pipelines must not serialize differently because of collaboration history (plan rev-2 §4.2).
- [x] **Session model + concurrency decision.** `GraphSession{id, graph, version, proposals,
  collab}` with a **monotonic `version`** bumped on every accepted change; writers send
  `If-Match`-style expected-version; a mismatch is a typed 409, and proposals carry
  `base_version` so stale agent work is detected, not applied. Record the rejected
  alternative (CRDT/OT real-time merge) as hosted-tier future work — optimistic concurrency
  is sufficient for one human + advisory agents.
- [x] **Agent surface: HTTP first, MCP second.** The agent-facing API is the session routes
  plus three existing routes (`/catalog`, `/validate`, `/compile`). Record that Shards is
  **not** a dependency in either direction: personas are markdown files agents consume; the
  server knows only HTTP clients. MCP (`fastmcp`/`fastapi-mcp`) is a wrapper behind
  `emergentflow[mcp]`, never on the base path.
- [x] **Gate policy is route-level.** `ef.validate` and `compile_to_code` stay pure and
  gate-ignorant; a *session-scoped* compile/execute with open gates returns 409 with the
  open-gate list; the payload-only `/compile` / `/execute` used by solo canvas and CI are
  untouched (plan rev-2 §4.3).
- [x] **Trust boundary.** Localhost-open / token-required-otherwise (see DoD). Record the
  storage tiering: sessions + collab state are metadata (in-memory locally, Redis hosted —
  ADR 0004); nothing here touches the artifact store.
- [x] **Persona integration modes named and separated** (plan rev-2 §5): **Mode A** — a real
  Shards/Claude Code agent using the HTTP/MCP tools, keeping its own gates/ledger; **Mode B**
  — a server-side one-shot consult through `LLMClient`, honestly described as a flavored LLM
  call. Mode A is the marriage; Mode B is the latency affordance.

## Story 2 — The mutation protocol: `GraphMutation` + pure `apply_mutation` (`emergentflow/ir/mutation.py`)

> The vocabulary everything else speaks — proposals, review fixes, and (later, deferred) the
> autonomous-research loop all carry `GraphMutation`s. Pure, small, and testable before any
> server exists. Precedent that programmatic graph construction works: the Prompt Lab already
> builds graphs in code (`ui/src/promptlab/buildEvalGraph.ts`) through the same mappers.

- [ ] Implement `GraphMutation` (pydantic, own module — **not** imported by `ir/graph.py`):
  `base_version: int`, `add_nodes: list[Node]`, `add_edges: list[Edge]`,
  `remove_nodes/remove_edges: list[str]`, `set_params: dict[str, dict[str, ParamValue]]`
  (node id → param name → value — a partial update, so an agent never reconstructs full
  `Param` objects), `description: str`, `author: str` (persona slug or `"human"`). Positions
  on added nodes are **optional** — layout is the canvas's job.
- [ ] Implement pure `apply_mutation(graph: Graph, m: GraphMutation) -> Graph`: returns a NEW
  graph (the `migrate_to_current` discipline — shallow-copy out, never mutate in;
  `emergentflow/ir/migrate.py:112`). Application order: removes → adds → param sets. Typed
  errors (`MutationError`) for: unknown node/edge ids, edges referencing removed/missing
  nodes/ports, `set_params` naming params the node's definition doesn't declare (delegate to
  `NodeDefinition.validate_node`, `emergentflow/nodes/contract.py:326`, when the type is
  registered), duplicate added ids.
- [ ] Implement `propose_diagnostics(graph, m) -> Diagnostics` — the **validate-on-propose**
  helper: `ef.validate(apply_mutation(graph, m))` with the mutation's typed failures folded
  into the same `Diagnostics` shape, so one call yields everything the canvas shows the human.
- [ ] Unit + property-style tests alongside `tests/test_migrate.py`'s patterns: apply →
  validate round-trips; input graph never mutated (deep-compare before/after); apply is
  deterministic; every `MutationError` case covered; a mutation built from a real
  `NodeDefinition.instantiate(...)` node round-trips through JSON (agents send JSON).
- [ ] **Works-without-agents check:** `emergentflow/__init__.py` does **not** eagerly import
  the module (lazy like the `ef.*` families); nothing in `codegen/` or `ir/graph.py` references it.

## Story 3 — Graph sessions on the server (`emergentflow/collab/` + session routes)

> The one genuinely new architectural piece: a server-side shared document. Keep it boring —
> an in-memory store, additive routes, and SSE reusing the Epic 7 machinery. No canvas work
> yet; this story is proven entirely with pytest/`curl` (which is also the first proof an
> *agent* can drive it, since an agent is just an HTTP client).

- [ ] `emergentflow/collab/session.py`: `GraphSession` model + an in-memory, thread-safe
  `SessionStore` (the report-store precedent — `get_default_store`,
  `emergentflow/server/app.py:322`). Accepting a proposal calls `apply_mutation`, bumps
  `version`, records the proposal's final status. Graph payloads entering a session route
  route through `deserialize_graph` exactly like `_to_graph`
  (`emergentflow/server/service.py:95`) so schema checks/migrations apply uniformly.
- [ ] Routes on `create_app` (`emergentflow/server/app.py:306`), same `_dispatch`/error-shape
  conventions (`_error_json`, `app.py:143`; 400 bad JSON / 422 service failure / 404 unknown):
  - `POST /sessions` (optional initial graph) / `GET /sessions/{id}` / `DELETE /sessions/{id}`
  - `PUT /sessions/{id}/graph` with expected `version` → 409 `stale_version` on mismatch
  - `POST /sessions/{id}/proposals` → stores the `GraphMutation` **with its
    `propose_diagnostics` result attached**; stale `base_version` → 409
  - `POST /sessions/{id}/proposals/{pid}/accept` (applies, bumps version) and `/reject`
  - `GET /sessions/{id}/events` — SSE stream (proposal added / accepted / rejected / graph
    replaced / gate events later), reusing the `_sse_frame` + queue-bridge machinery from
    `/execute/stream` (`app.py:230`)
- [ ] Bearer-token check per Story 1 (open on localhost by default; required otherwise).
- [ ] Tests in `tests/test_server_sessions.py`: full lifecycle over the ASGI test client;
  concurrent-writer 409s; a proposal against a moved graph rejected; SSE events observed for
  each transition; unknown session/proposal → 404; **the "agent" in these tests is literally
  the HTTP client — no LLM anywhere.**
- [ ] **Works-without-agents check:** every pre-existing route's behavior is untouched
  (`tests/test_server.py` passes unmodified); the session store is created lazily on first
  session route hit; a server that never receives a session call allocates nothing new.

---

## Story group B — The happy path (an agent collaborating on the canvas, soonest)

## Story 4 — Canvas session mode + proposal UX (ghost diffs, accept/reject)

> The human's half of the happy path. Session mode is strictly opt-in: the default canvas
> experience is byte-identical to today, and a user who never opens a session never loads the
> session code path.

- [x] Generate the new contracts: extend `scripts/export_ui_contracts.py` to emit
  `mutation.schema.json` + session/event schemas and TS types into `ui/src/generated/`
  (the `ir.schema.json` flow), ajv-compiled in the UI like `validateIR.ts`
  (`ui/src/store/validateIR.ts:16`). Golden test pins schema stability.
- [x] `ui/src/session/` (new): a session client (join/create via the routes, subscribe to
  `/events` SSE with polling fallback, reuse the `httpJson` helper pattern from
  `ui/src/promptlab/httpJson.ts`) and a `sessionStore` that *wraps* `graphStore` — on accept,
  the server's post-apply graph is loaded through the existing `fromIR`
  (`ui/src/store/ir.ts:125`); on local edit in session mode, the store pushes
  `PUT /sessions/{id}/graph` with the expected version and surfaces a 409 as a "rebase"
  banner, never a silent overwrite.
- [x] **Ghost-diff rendering:** a pending `GraphMutation` renders as ghost nodes/edges
  (dashed, pending visual state) overlaid on the canvas; position-less added nodes get
  auto-layout placement; `set_params` changes badge the affected node. The proposal panel
  shows `author`, `description`, and the attached `Diagnostics` verdict (reusing the
  existing diagnostics rendering — this is the "this proposal type-checks" moment).
- [x] **Accept / Reject / Edit-into-own:** Accept calls the accept route and reloads;
  Reject dismisses; dragging/tweaking a ghost converts the proposal into ordinary local
  edits (proposal marked superseded). Vitest coverage for the store logic and the
  ghost-overlay component; the diff renderer is pure over `(CanvasModel, GraphMutation)`.
- [x] **Works-without-agents check:** session UI is lazy-loaded behind the opt-in entry
  point ("Share session" affordance); `App.tsx` default path renders zero session code;
  existing canvas tests (`ui/src/ir-interactions.test.tsx`, `Canvas.test.tsx`) pass unmodified.

## Story 5 — The first agent + the happy-path milestone (persona file over plain HTTP)

> **The epic's payoff gate, front-loaded.** After this story, a Shards / Claude Code agent and
> a human genuinely collaborate on one graph — everything after deepens it. No MCP, no
> embedded LLM, no new deps: the agent surface is `curl`.

- [x] Write `agents/emergent-flow-collaborator.md` — a persona file (Shards-compatible,
  plain markdown) that teaches any Claude Code agent the surface: how to find the server,
  create/join a session, read the graph + `GET /catalog` for legal node types/params/ports,
  pre-flight candidates with `POST /validate`, show the human implied code via
  `POST /compile`, submit a `GraphMutation` with correct `base_version`, and await the
  verdict on the SSE stream. Include a worked end-to-end transcript (the request → curl
  calls → proposal JSON) as the few-shot spine.
- [x] Add a `GET /sessions` (list active sessions) so an agent can discover the human's
  session without copy-pasting ids; document the discovery flow in the persona file.
- [x] **Scripted-agent acceptance test** (`tests/test_agent_happy_path.py`): a pytest
  "agent" (HTTP client following the persona file's exact call sequence) joins a session
  seeded with a small graph, proposes a two-node addition (e.g. `describe` → chart on an
  existing DataFrame output, built from `/catalog` data), the proposal arrives with clean
  diagnostics, "human" accepts, and the resulting graph **compiles and executes** via the
  standard routes. This is the CI-checked happy path, agent-free by construction.
- [ ] **Manual milestone (checked off when demonstrated, like Epic 13's demos):** a real
  Claude Code session with the persona file drives the same flow against `emergentflow serve`
  with the canvas open — the human watches the ghost diff land live and accepts it.
- [x] **Works-without-agents check:** `agents/` is documentation — nothing in the package
  imports it; the milestone alters no code.

## Story 6 — Two-way: the agent reviews the human's work (diagnostics extension + review threads)

> The other half of the stated goal, and deliberately still in the happy-path group: review is
> just proposals' machinery pointed the other way. Land the one-time `Diagnostic` contract
> change here, early, so it never happens piecemeal.

- [x] **`Diagnostic` extension (additive, once):** add `INFO` to `Severity`
  (`emergentflow/codegen/validation.py:39`) and `source: str | None = None`
  (`"validator"` | persona slug) to `Diagnostic` (`validation.py:42`); `ef.validate` stamps
  `source="validator"`. Mirror both in `ui/src/store/validation.ts`; regenerate contracts;
  update the `/validate` golden (`tests/test_validation_golden.py`) — one reviewed diff.
- [x] `emergentflow/collab/review.py`: `ReviewThread{id, author, findings: list[Diagnostic],
  comments, fix: GraphMutation | None, status}` on `CollaborationState`; routes
  `POST/GET /sessions/{id}/reviews`, replies appended, events on the SSE stream. Findings
  anchor to real graph elements via the existing `node_id`/`edge_id`/`port_id` fields —
  the server rejects anchors that don't resolve against the session graph.
- [x] Canvas: review findings render through the **same** diagnostics path as `ef.validate`
  output (red/yellow dots; `info` + persona `source` styled as review comments, not
  failures); a finding with an attached `fix` offers **"apply fix"** → the fix is an
  ordinary proposal accept (Story 4 machinery, zero new apply code).
- [x] Persona file part 2: a review workflow section — read graph + compiled preview,
  post anchored findings with severities, attach fix-mutations where mechanical. Scripted
  review test: pytest agent posts two findings (one `info`, one `warning` with a fix) on a
  seeded flawed graph; "human" applies the fix; graph validates clean.
- [x] **Works-without-agents check:** the `Diagnostic` changes are defaulted so every
  existing producer/consumer is untouched (existing goldens change only by explicit
  regeneration); review UI rides the session lazy-load.

---

## Story group C — Deepening the collaboration (tools, personas, consults)

## Story 7 — MCP tool surface + persona catalog (`emergentflow[mcp]`)

> Ergonomics for Mode A: the same six capabilities as first-class MCP tools so an agent
> doesn't hand-roll `curl`. A wrapper over existing routes — no new behavior, optional extra.

- [ ] MCP server (`emergentflow/collab/mcp.py`, behind the `[mcp]` extra with a typed
  `MissingOptionalDependencyError` on absent-import — the `[bigquery]` discipline) exposing:
  `get_graph`, `list_sessions`, `get_catalog`, `validate_graph`, `compile_preview`,
  `propose_mutation`, `post_review`, `await_verdict` (long-poll over the SSE stream). Each
  tool delegates to the same service functions as the HTTP routes — one behavior, two doors.
- [ ] `AgentPersona` catalog (`emergentflow/collab/personas.py`): a **flat registry** —
  explicitly *not* the node registry; `@register` takes `NodeDefinition` subclasses with
  codegen/execute contracts, and a persona is a prompt (plan rev-2 §5.1). Fields: `slug`,
  `label`, `description`, `node_families`, `system_prompt` (Mode B), `source_path` (Mode A
  markdown). Served at `GET /personas` so the canvas can render "ask the ML Engineer".
- [ ] Ship 2–3 Mode-A persona files mapped from Shards (Data Modeller — grain/join-key
  review on `data.*`; Researcher — methodology review on `stats.*`), each with the Story 5/6
  workflow sections. Scripted tests drive their documented call sequences.
- [ ] Update `docs/` with the agent-integration guide: HTTP surface, MCP config snippet for
  Claude Code, persona-file authoring, and the Shards pairing recipe (install Shards, point
  the persona at the local server).
- [ ] **Works-without-agents check:** base install imports cleanly with the MCP lib absent
  (add to the absent-extras import test); no route behavior changes.

## Story 8 — Mode-B one-shot consults + `advisor_persona` on the node contract

> The latency affordance: "fill in this node's params" without a full coding agent attached.
> ADR-0017's move, unchanged: the consult is an `LLMClient` call, replay-tested, and it
> *returns a `GraphMutation`* — same protocol, no special case.

- [ ] `POST /sessions/{id}/consult` (and a sessionless `POST /consult` for solo-canvas use):
  body names a persona slug + target node ids + the ask; the service composes the persona's
  `system_prompt` + the graph slice + `/catalog` context, calls the injected `LLMClient`
  (`GatewayClient` live — `emergentflow/llm/gateway.py`; `ReplayClient` in tests —
  `emergentflow/llm/replay.py`), parses the structured response into a `GraphMutation`
  (`set_params`-only for the param-fill case), and returns it **as a proposal** with
  diagnostics attached. Malformed LLM output → typed error surfaced as a failed consult,
  never a crash or a silent bad mutation.
- [ ] `advisor_persona: ClassVar[str | None] = None` on `NodeDefinition`
  (`emergentflow/nodes/contract.py:85`) — the contract's third such additive extension
  (after `requires_client`, then `requires`/`ClientKind` — `contract.py:161`). Surface it
  through `to_spec()` (`contract.py:249`) → `/catalog`, so the canvas renders a "consult"
  affordance on nodes that declare one. Set it on 2–3 reference nodes (e.g. an ML training
  node → `ml_engineer`).
- [ ] Canvas: the consult affordance on a node opens the ask box, shows the returned
  proposal through the Story 4 ghost/accept UX. Consults are **always explicit user
  actions** — nothing auto-fires on node drop (the auto-consultation triggers from the
  plan are deferred until latency + annoyance are understood).
- [ ] Replay-fixture tests: a param-fill consult round-trips under `ReplayClient`; the
  emitted mutation validates; a graph with no consult behaves identically with `client=None`.
- [ ] **Works-without-agents check:** `advisor_persona` defaults to `None` on all existing
  nodes (catalog golden updates only by regeneration); consult routes require an explicit
  call; no client is constructed unless one is configured.

## Story 9 — Gates on the session (Shards' checkpoint pattern, route-enforced)

> Shards' defining pattern, reified where it belongs: on `CollaborationState`, enforced at the
> session routes, invisible to the pure core and to every sessionless workflow.

- [ ] `Gate{id, phase, kind: phase|confirm|handoff|execute|final, description, status,
  decisions: list[Decision]}` on `CollaborationState`; routes to open/close/skip gates and
  append decisions; SSE events. Agents open gates and write decisions per their persona
  workflow; the human closes them from the canvas.
- [ ] **Session-scoped compile/execute policy:** `POST /sessions/{id}/compile` and
  `/sessions/{id}/execute` (thin wrappers over the existing service functions) return 409
  with the open-gate list while gates are open. The payload-only `/compile` / `/execute`
  are **untouched** — solo canvas and CI never see a gate.
- [ ] Canvas: gate timeline + decision viewer in the session panel; "Gate open" banner with
  inline decisions; confirm-to-close. The Shards hook-level gates (Stop/PreToolUse) remain
  the *agent's* own discipline — the session gate is where the two systems meet (an
  unaccepted proposal *is* the agent's "awaiting confirmation").
- [ ] Tests: gated session 409s then compiles after close; decisions persist and stream;
  sessionless compile of the same graph unaffected (the explicit works-without-agents case).

---

## Story group D — Hardening, breadth, and the payoff

## Story 10 — Knowledge base, minimal slice (standalone, workspace-level)

> Shards' `.shards/knowledge/` upgraded to typed subgraph templates — deliberately minimal:
> slug-keyed store + port-signature discovery. Dedup/versioning/GC are recorded as real costs
> and deferred until usage demands them (plan rev-2 §6).

- [x] `KnowledgeEntry{slug, description, subgraph: Graph, tags, created_by, metrics}` in a
  standalone store (`emergentflow/collab/knowledge.py`) — **workspace-level, never a `Graph`
  field**; metadata tier per ADR 0004 (JSON file under the workspace locally). Routes:
  `GET/POST /knowledge`, `GET /knowledge/{slug}`; exposed as MCP tools.
- [x] Discovery by **dangling-port signature**: compute an entry's unbound IN-port types →
  produced OUT-port types via `infer_graph_types` (`emergentflow/codegen/inference.py`) at
  save time; `GET /knowledge?in=DataFrame&out=FittedModel` + tag filter. No embeddings — a
  later luxury.
- [x] Persona behaviors (Mode A, documented in the persona files): **harvest** — after a
  session graph is accepted+validated, the agent may propose a parameterized fragment as a
  `KnowledgeEntry` (human confirms via the same proposal UX); **retrieve** — on a fresh ask,
  the agent queries by signature and proposes a matching fragment as its `GraphMutation`.
- [x] Tests: save→discover round-trip; signature computed correctly for a fragment with
  unbound inputs; a retrieved fragment applies through `apply_mutation` and validates.
- [x] **Works-without-agents check:** store created lazily; nothing outside `collab/`
  imports it; the knowledge file's absence is a normal empty state.

## Story 11 — The works-without-agents regression suite + contract stability at scale

> The epic's CRITICAL invariant, made permanent CI instead of a launch-day claim. Mirror the
> Epic 13 Story 9 role: one story that turns every "check" scattered above into gates.

- [x] **Import-isolation gate:** a test that runs the full pre-existing suite selection with
  an import hook asserting `emergentflow.collab` (and the MCP lib) are never imported; plus
  the existing light-import test extended to prove `import emergentflow` pulls in no collab
  module.
- [x] **Byte-identical solo path:** golden tests that a representative graph's
  `compile_to_code` output, `/compile` + `/validate` + `/execute` responses, and canvas
  IR round-trip (`toIR`/`fromIR`) are unchanged from pre-epic goldens; `ir.schema.json`
  asserted untouched; `CURRENT_SCHEMA_VERSION` asserted `== 1` with a comment tying it to
  this epic's invariant.
- [x] **Dependency gate:** lockfile check that the base dependency set gained nothing;
  `[mcp]` extra verified optional via the absent-import test (Story 7).
- [x] **No-ambient-LLM gate:** grep-level + runtime assertion that no session/proposal/review
  route constructs an LLM client; only `/consult` may, and only when configured.
- [x] **Contract stability:** goldens on `mutation.schema.json` + session/event schemas
  (the export_ui_contracts flow) so a model change is a reviewed diff; ajv round-trip tests
  UI-side; a `GraphMutation` serialized by the pytest agent deserializes identically in TS
  (fixture shared across both test suites, the Epic 13 fixture discipline).
- [x] Wire all of the above into `.github/workflows/ci.yml` alongside the existing gates.

## Story 12 — Acceptance demos (the payoff: collaboration in both directions)

> Two end-to-end demos proving the stated goal — plan together, agent builds / human reviews,
> human builds / agent reviews — CI-runnable with the agent as a scripted HTTP client, and
> demonstrable live with a real Claude Code + Shards persona.

- [ ] **Acceptance demo (agent builds, human accepts):** seeded session with a
  `load_csv → describe` graph; the scripted agent (Story 5 persona sequence) proposes
  extending it with a stats + chart pair discovered from `/catalog`; ghost diff renders with
  a clean verdict; accept; the graph compiles to ruff-clean `.py` and executes to results —
  asserted end-to-end in CI, demonstrated live with Claude Code against `emergentflow serve`.
- [x] **Acceptance demo (human builds, agent reviews):** a human-built graph with a planted
  flaw (e.g. a t-test fed by an obviously non-normal column, or a join on mismatched keys);
  the scripted reviewer posts anchored findings (`info` + `warning`) with a fix-mutation;
  the human applies the fix from the finding; re-validate is clean; compile + execute.
- [x] Document both under `docs/acceptance-demo.md` ("human + agent on one canvas — what the
  app can do today") and add `examples/agent_collaboration_acceptance_demo/` (the Epic 8/12/13
  `examples/*_acceptance_demo/` precedent) with the seeded graphs, the persona files, and the
  scripted-agent transcripts.
- [x] Update `epics/README.md` mapping table with the Epic 14 row (done at epic kickoff —
  keep it accurate at close).

---

## Notes / Risks (carry into planning)

- **Shared mutable state is the real cost — everything else is easy.** The session document
  introduces concurrency into a codebase whose superpower is purity. `base_version` +
  monotonic `version` + typed 409s contain it, but test it adversarially (Story 3's
  concurrent-writer cases are load-bearing, not box-ticking). Resist any design that lets a
  proposal apply without a version check "just this once."
- **The IR is the one-way door — keep collaboration out of it.** The moment a `gates:` or
  `proposals:` field lands on `Graph`, every saved graph everywhere carries workflow history,
  the schema version bumps, and older deployments reject new files. The plan litigated this
  (rev-2 §4.2); the Story 11 `CURRENT_SCHEMA_VERSION == 1` assertion is the tripwire.
- **Agents are graph producers, never a third consumer.** The temptation will be an
  "agent-aware execute" or compiler hook. Don't: an accepted proposal is an ordinary graph,
  and ADR-0002 stays one gate. Any agent feature that wants compiler awareness is mis-scoped —
  it belongs at the session routes or in the persona.
- **Don't pretend Mode B is Shards.** A one-shot `LLMClient` consult has no gates, no ledger,
  no cross-review — it's a flavored LLM call. Useful, but label it in UX and docs; the real
  marriage is Mode A, and it's also the cheaper build (prompt files over existing routes).
- **Happy path means deferring the tempting parts.** Auto-consultation triggers (agents
  firing on node drop), the autonomous-research loop, multi-agent panel orchestration, and
  knowledge dedup/GC are all explicitly out of scope or minimal here. AR in particular is
  **gated on Epic 6 sandboxing + cost metering** — an unattended loop executing generated
  graphs is the sandbox's core use case, so do not prototype it against the unsandboxed
  executor.
- **Review latency is a UX problem, not a compiler problem.** Persona review findings arrive
  seconds-to-minutes after the human moved on; anchor them to the `base_version` they were
  computed against and render staleness honestly (like a CI comment on an outdated PR
  revision), rather than trying to make LLM review synchronous.
- **The `Diagnostic` contract changes once (Story 6), early.** `Severity.INFO` + `source`
  touch a frozen model, the `/validate` golden, and the UI mirror — batching them with the
  review feature keeps it to one reviewed diff. Piecemeal extension later would churn the
  contract three times.
- **Localhost is the trust boundary today — say so in every doc.** The session surface lets
  an HTTP client rewrite graphs. Fine on `127.0.0.1` (the Jupyter trust model Epic 13 already
  invoked); the token check for non-local binds ships in Story 3 so hosted work is a
  configuration change, not a security retrofit.
- **Keep Shards decoupled in both directions.** Shards installs must not require emergentflow
  changes beyond the persona files, and emergentflow must never import Shards. The persona
  files are the whole coupling — markdown, versioned in `agents/`, testable by scripted HTTP
  sequence. If a future need wants tighter coupling, that's a new decision (and probably a
  hosted-product one), not scope creep here.

---

*How to use this file: tick each `- [ ]` to `- [x]` as work completes. A story is done when all
its tasks are checked — **including its works-without-agents check** — and the epic is done when
the Definition of Done checklist is complete.*
