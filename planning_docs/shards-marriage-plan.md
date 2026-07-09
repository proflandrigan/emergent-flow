# Shards Marriage Plan: Making Emergent Flow AI-Native (rev 2)

## Review Summary — what this revision changes and why

> Rev 2 is a critical pass over the original plan, checked against the actual code in both
> repos. The original's core thesis is right and worth building. Its biggest problems were
> (a) a missing layer, (b) a misreading of what Shards is, and (c) putting collaboration
> state in the wrong place. Specifics:

1. **The transport layer was missing entirely.** The original said *what* agents do to the
   graph but never *how they reach it*. Shards agents are Claude Code sessions (markdown
   personas + hooks), not Python objects; the emergent-flow server
   (`emergentflow/server/app.py:306`, `create_app`) is stateless — every `/compile`,
   `/validate`, `/execute` call carries the whole graph in the request body, and the
   authoritative working graph lives client-side in the canvas's Zustand store
   (`ui/src/store/graphStore.ts`). There is no server-side graph document for an agent to
   read or mutate. **This is the actual integration work**, and it is now Phase 0 (§2, §10).

2. **Shards was misread as a library.** Shards ships persona prompt files, Claude Code
   hooks, and a browser dashboard — there is no importable agent API. "Register personas
   into the node registry with `@register`" conflates two different contracts: `@register`
   registers `NodeDefinition` subclasses (`emergentflow/nodes/registry.py`), which carry
   `codegen`/`execute` behavior; a persona is a prompt. §5 now separates the two honest
   integration modes: (A) real Shards agents reaching the canvas through tools, and
   (B) server-side one-shot persona consults through the `LLMClient` seam.

3. **Gates and knowledge do not belong on `Graph`.** Adding `gates:`/`knowledge:` fields to
   the IR bumps `CURRENT_SCHEMA_VERSION` (`emergentflow/ir/graph.py:30`), requires a
   migration step (`emergentflow/ir/migrate.py`), regenerating `ui/src/generated/ir.schema.json`
   and the TS types, and updating the ajv gate (`ui/src/store/validateIR.ts`) — all to embed
   *collaboration history* into an artifact that is supposed to be a pure description of a
   pipeline. Two semantically identical pipelines would serialize differently depending on
   who reviewed them. Rev 2 moves this into a `CollaborationState` document that lives
   *alongside* a graph session (§4, §6), keyed by graph id, in the ADR 0004 metadata tier.

4. **The purity claims in the old §8 were subtly wrong.** A compiler pass that refuses to
   emit code while gates are open makes compilation depend on workflow state. Rev 2 keeps
   `compile_to_code` and `ef.validate` pure and enforces gate policy where policy belongs:
   in the server's `/compile` route (§4.3).

5. **"Provably correct" overclaimed.** ADR 0002 guarantees `compile_to_code(G)` and
   `execute(G)` agree — it does not prove the graph does the right thing. The honest claim
   (still a strong one no competitor can make): agent proposals are *structurally validated
   and execution-equivalent by construction* (§1, §11).

6. **Sub-second agent validation was acknowledged as hard, then designed as if it weren't.**
   Rev 2 makes the split structural: deterministic passes stay synchronous in `ef.validate`;
   LLM-backed persona passes are async and report like a code review (§5.4, §8).

7. **Smaller fixes:** `GraphMutation` gains `base_version` for conflict detection, drops
   agent-chosen positions in favor of auto-layout, keys param changes by name (§3.1);
   `Diagnostic` today only has `error|warning` severity (`emergentflow/codegen/validation.py:39`)
   — the "green for info" rendering needs an enum extension mirrored in
   `ui/src/store/validation.ts` (§9.5); autonomous research now states its Epic 6 / cost
   dependencies (§7); the agent-review-of-human-work flow (half the stated goal) gets its
   own concrete flow instead of being implied (§5.3).

8. **What survives untouched, because it's right:** the core insight (§1), ghost-node diff
   UX, mutation-as-IR-model, reusing `Diagnostic` as the agent-finding vocabulary, the
   knowledge base as typed subgraph templates, and the overall phase discipline of proving
   the pattern before touching the compiler.

---

## Executive Summary

**Emergent Flow** has the graph IR, equivalence-guaranteed compiler, and visual canvas.
**Shards** has the multi-agent collaboration patterns, structured gate workflow, and
specialist personas. Neither alone is "AI-native" — an AI-native platform is one where
**humans and AI agents jointly author, validate, and iterate on a shared artifact**, and
that artifact is the graph IR.

This document proposes integrating Shards' collaboration protocols with emergent-flow's
graph IR, server, and canvas — making the canvas a collaborative space where a human and a
coding agent plan together: the human can ask an agent to build or extend a flow, and an
agent can review, annotate, and propose changes to a flow the human built.

---

## 1. The Core Insight: Graph IR as Shared Artifact

Today, Shards agents produce flat files (SQL, Python, markdown specs) and a human reviews
them. Emergent Flow has a structured graph IR but it's authored by humans clicking in a
canvas.

**The marriage:** agents propose, validate, and mutate the graph IR directly. The human
collaborates at the graph level — drag, reconnect, tweak params — not at the code level.
ADR 0002 guarantees that whatever the graph says, the compiled code does: an accepted agent
proposal is *structurally validated* (via `ef.validate`,
`emergentflow/codegen/validation.py:263`) and *execution-equivalent by construction* —
not "provably correct" in the semantic sense, but a categorically stronger guarantee than
any flat-file agent workflow can offer.

```
Today:   Human → Canvas → Graph IR → compile_to_code → Python
         Agent → Code/Text files (no shared structure)

Married: Human ↔ Canvas ↔ Graph session (server) ↔ compile_to_code ↔ Python
                              ↕
                        Agent (Shards persona in Claude Code,
                        speaking HTTP/MCP to the same session)
```

Note the revised diagram: the shared thing is a **graph session on the server**, not the
IR floating in the abstract. That session is the new piece (§2); everything else in this
plan rides on it.

---

## 2. Phase 0 — The Missing Layer: How an Agent Reaches the Canvas

### 2.1 Reality check on both sides

- **Shards side:** a persona is a Claude Code agent — a markdown prompt plus hooks
  (`.claude/agents/`, `.shards/hooks/gate-hook.js`). Its capabilities are its *tools*
  (Bash, Read, MCP tools). It cannot import `emergentflow`; it can `curl` an endpoint or
  call an MCP tool. Integration means **giving the agent tools that touch the canvas**,
  not embedding the agent in the SDK.
- **Emergent-flow side:** the FastAPI server (`emergentflow/server/app.py`) is
  deliberately stateless — `_POST_ROUTES` (`app.py:132`) are pure `graph-dict in →
  result out` functions from `emergentflow/server/service.py`, and every request routes
  the payload through `deserialize_graph` (`service.py:95`) so schema-version checks and
  migrations apply uniformly. The *live* graph exists only in the browser's Zustand store.
  An agent has nothing to read and nowhere to write.

### 2.2 Graph sessions (the new server-side document)

Introduce a session document the canvas and agents both talk to:

```python
class GraphSession(BaseModel):
    id: str
    graph: Graph                    # current accepted state
    version: int                    # monotonic; bumps on every accepted change
    proposals: list[GraphMutation]  # pending agent proposals (§3)
    collab: CollaborationState      # gates, decisions, review threads (§4)
```

- New routes on `create_app` (`emergentflow/server/app.py:306`):
  - `POST /sessions` / `GET /sessions/{id}` — create/fetch a session
  - `PUT /sessions/{id}/graph` — canvas pushes accepted state (with `If-Match: version`
    optimistic concurrency)
  - `POST /sessions/{id}/proposals` — agent submits a `GraphMutation`
  - `POST /sessions/{id}/proposals/{pid}/accept|reject` — human decides (canvas calls this)
  - `GET /sessions/{id}/events` — SSE stream of session changes, so the canvas sees agent
    proposals arrive live and the agent can await the human's verdict. The SSE plumbing
    already exists — reuse the `_sse_frame` / queue-bridge machinery from
    `/execute/stream` (`app.py:230`).
- The canvas gains a "shared session" mode: `graphStore` syncs to the session instead of
  being the sole authority. Solo editing (no session) keeps working exactly as today —
  the session layer is opt-in, mirroring how `/execute` stays payload-in/payload-out.
- Storage: in-memory dict for the local single-user server (same tier as the report store
  used by `/reports/{hash}`, `app.py:322`); Redis in the hosted product per ADR 0004.
- Trust boundary: the local server binds `127.0.0.1` (`serve`, `app.py:436`) — fine for
  Phase 0. Before any non-local deployment, session routes need a bearer token; note it
  now so it isn't retrofitted.

### 2.3 Agent surface: HTTP first, MCP second

Phase 0 ships plain HTTP + a Shards persona file that documents the endpoints — a Claude
Code agent drives them with `curl` on day one, no new infra. Phase 1 wraps the same routes
in an MCP server (`fastmcp` or `fastapi-mcp`) exposing:

| Tool | Backing route | Purpose |
|---|---|---|
| `get_graph` | `GET /sessions/{id}` | read current graph + version |
| `get_catalog` | `GET /catalog` (exists) | what node types can I use? |
| `validate_graph` | `POST /validate` (exists) | pre-flight a candidate |
| `propose_mutation` | `POST /sessions/{id}/proposals` | submit a diff |
| `compile_preview` | `POST /compile` (exists) | show the human the code a proposal implies |
| `execute_preview` | `POST /execute` (exists) | dry-run a candidate (cached — Epic 7 store) |

Three of six tools already exist as routes. **The marriage point is precisely here:**
Shards personas stay what they are (Claude Code agents, with their gate hooks and
knowledge ledger intact) and gain a typed, validated artifact to operate on instead of
flat files.

---

## 3. Agent-in-the-Loop Graph Editing

### 3.1 Graph Mutation Protocol

A lightweight protocol describes how an agent proposes graph changes — a pydantic model in
a new `emergentflow/ir/mutation.py`, so it flows through the existing serialization but is
**not** a field on `Graph` (no `schema_version` bump; the wire IR is untouched):

```python
class GraphMutation(IRModel):
    """A proposed change to a graph. Rendered as a diff on the canvas."""
    base_version: int                       # session version this was computed against
    add_nodes: list[Node] = []              # positions optional — canvas auto-layouts
    add_edges: list[Edge] = []
    remove_nodes: list[str] = []            # node ids
    remove_edges: list[str] = []            # edge ids
    set_params: dict[str, dict[str, ParamValue]] = {}  # node_id → {param_name: value}
    description: str                        # why the agent proposes this
    author: str                             # persona slug, e.g. "ml_engineer"
```

Changes from rev 1, with reasons:

- **`base_version`** — the human keeps editing while the agent thinks. A proposal whose
  `base_version` is stale must be rejected or rebased, not silently applied. Without this,
  the first real two-party session corrupts a graph.
- **`set_params` keyed by param name** — rev 1's `dict[IRId, list[Param]]` forced the
  agent to reconstruct full `Param` objects (`type_token`, `default`, …); a partial
  name→value map matches what an agent actually wants to say and what
  `NodeDefinition.validate_node` (`emergentflow/nodes/contract.py:326`) can check.
- **Positions optional** — an LLM choosing x/y coordinates is noise; the canvas already
  owns layout.

Alongside the model, a pure function `apply_mutation(graph: Graph, m: GraphMutation) ->
Graph` — same purity discipline as `migrate_to_current` (`emergentflow/ir/migrate.py:112`):
returns a new graph, never mutates. This is the single function both the server (on
accept) and any test harness use, so accept-semantics can't drift.

**Validate on propose:** when the server receives a proposal it immediately runs
`ef.validate(apply_mutation(session.graph, m))` and stores the resulting `Diagnostics`
with the proposal. The canvas shows the human "this proposal type-checks cleanly" (or the
red/yellow findings) *before* they decide. This — not vibes — is the concrete payoff of
agents operating on typed IR instead of text.

Precedent that this shape works: the Prompt Lab already builds graphs programmatically
from UI code (`ui/src/promptlab/buildEvalGraph.ts`) via the same `toIR` mappers
(`ui/src/store/ir.ts:100`). Agent-proposed construction is the same move, server-side.

### 3.2 Turn Flow

1. Human selects a region of the graph (or the whole thing) in a shared session
2. Human types a natural-language request: *"Normalize these features and add a
   regularization layer"* — or the agent initiates unprompted from a review pass (§5.3)
3. The request reaches the agent (a Shards persona in Claude Code watching the session,
   or a server-side one-shot consult — §5.2)
4. Agent reads the graph + catalog via its tools, returns a `GraphMutation`
5. Server validates the post-mutation graph, attaches `Diagnostics`, emits an SSE event
6. Canvas renders the diff as ghost nodes (dashed outlines, pending state), with the
   proposal's description and validation verdict alongside
7. Human drags connections, tweaks params — edits *convert the proposal into their own
   working state*; or clicks Accept (server applies via `apply_mutation`, bumps
   `version`) or Reject
8. `compile_to_code` and `execute` run on the accepted graph — equivalence holds by
   construction, untouched

### 3.3 Node Advisor Metadata

Rev 1's `agent_strategy: ClassVar[str | None]` survives with a clearer name and a defined
consumer:

```python
class NodeDefinition(ABC):
    ...
    advisor_persona: ClassVar[str | None] = None
    # e.g. "ml_engineer" — which persona to consult to auto-fill
    # this node's params when the human drops it on the canvas
```

- Backward compatible: existing nodes don't set it, nothing changes (`NodeDefinition`,
  `emergentflow/nodes/contract.py:85`).
- Surface it through `to_spec()` (`contract.py:249`) so it rides the existing `/catalog`
  route and the canvas can render a "consult ML Engineer" affordance on the node — the
  spec is the declared canvas↔SDK coupling point; don't invent a second channel.
- The consult itself is a one-shot persona call (§5.2) returning a `GraphMutation` that
  only sets params on that node. Same protocol, no special case.

---

## 4. Shards' Gate Pattern — On the Session, Not the Graph

### 4.1 The Problem Shards Solves

LLMs write code but don't document *why*. Shards forces agents to write decisions to a
`project-specs.md`, read them back, and gate on human confirmation — enforced by Stop /
PreToolUse / UserPromptSubmit hooks and `.shards/gates/state.json`.

### 4.2 The Reification — corrected placement

Gates become structured checkpoints the canvas renders as a timeline — but they live on
the **session's `CollaborationState`**, not as a `gates:` field on `Graph`:

```python
class Gate(BaseModel):
    id: str
    phase: int
    kind: Literal["phase", "confirm", "handoff", "execute", "final"]
    description: str
    status: Literal["open", "closed", "skipped"] = "open"
    decisions: list[Decision] = []   # agent writes decisions here

class CollaborationState(BaseModel):
    gates: list[Gate] = []
    review_threads: list[ReviewThread] = []   # §5.3
```

Why not on `Graph` (this is the load-bearing correction):

- Any new `Graph` field bumps `CURRENT_SCHEMA_VERSION` (`emergentflow/ir/graph.py:30`),
  needs a `register_migration` step (`emergentflow/ir/migrate.py:70`), regeneration of
  `ui/src/generated/ir.schema.json` + TS types, and survives forever in every saved graph
  file. Collaboration history is not part of what a pipeline *is*.
- The IR models are `extra="forbid"` — graphs with gate fields are rejected by every
  deployed older server. High blast radius for workflow metadata.
- Keeping gates off the graph makes "graphs without gates compile instantly, as today"
  (rev 1's own requirement) true by construction rather than by opt-in flag.

### 4.3 Enforcement — at the route, not in the pure functions

`ef.validate` and `compile_to_code` stay pure functions of the graph and know nothing
about gates. The **session-aware server routes** enforce policy: a `/compile` or
`/execute` issued *within a session* that has open gates returns 409 with the open-gate
list. The existing payload-only `/compile` (used by solo canvas and CI) is untouched.

This replaces Shards' hook-based enforcement (Stop, PreToolUse, UserPromptSubmit) with
something structurally simpler for graph work — while a Shards persona *driving the
session* still keeps its own gate hooks for its conversational workflow. The two gate
systems meet at the session: the persona's "await confirmation" step is literally
"proposal sits unaccepted."

### 4.4 The Flow

1. Agent proposes a subgraph (§3) and opens a `Gate` on the session
2. Agent writes `decisions` to the gate (why this approach, what alternatives considered)
3. Canvas shows a "Gate Open" banner — human reads decisions inline
4. Human clicks "Confirm" — gate closes, proposal accepted
5. Session-scoped compile/execute proceed

---

## 5. Shards' Specialist Personas — Two Integration Modes

### 5.1 What a persona is (and isn't)

A Shards persona is a prompt + workflow definition for a Claude Code agent. It is not a
Python object, and it must **not** go through `@register`
(`emergentflow/nodes/registry.py`) — that decorator registers `NodeDefinition` subclasses
carrying the `codegen`/`execute` behavioral contract. A persona registry, if needed, is a
separate flat catalog:

```python
class AgentPersona(BaseModel):          # plain model; own registry; NOT a node
    slug: str                           # "ml_engineer"
    label: str                          # "ML Engineer"
    description: str
    node_families: list[str]            # which families this persona advises on
    system_prompt: str                  # for mode B (one-shot consults)
```

### 5.2 Mode A and Mode B

- **Mode A — full Shards agent (interactive):** the persona runs in Claude Code with its
  gates, knowledge ledger, and cross-agent consultation intact, and operates on the canvas
  through the §2.3 tools. This is the true "marriage": Shards keeps its collaboration
  discipline; emergent-flow supplies the typed artifact. Zero emergent-flow code embeds an
  agent.
- **Mode B — one-shot consult (embedded):** for fast, targeted asks (fill this node's
  params, sanity-check this subgraph), the server calls the persona's `system_prompt`
  through the existing `LLMClient` seam (ADR 0017; `emergentflow/llm/gateway.py`), with
  `ReplayClient` making the flow testable in CI exactly like every other LLM node. Mode B
  is a *flavored LLM call*, and the doc should never pretend it's the Shards agent — it
  has no gates, no ledger, no cross-review.

Start with Mode A (it's mostly prompt-writing once Phase 0 lands) and add Mode B for the
latency-sensitive affordances (§3.3 advisor consults).

### 5.3 Agent reviews the human's work (the missing half of the goal)

The flow rev 1 implied but never specified:

1. Human builds a flow in a session and clicks "Request review" (or a persona watches the
   session and self-triggers on `version` bumps)
2. The persona reads the graph, catalog, and the compiled preview (`POST /compile`)
3. It returns findings as `Diagnostic`-shaped items plus prose comments in a
   `ReviewThread` on `CollaborationState`, each anchored to a `node_id`/`edge_id` —
   the anchoring fields already exist on `Diagnostic`
   (`emergentflow/codegen/validation.py:42`)
4. Canvas renders them exactly like validation findings, with a reply box; replies go
   back to the persona over the session SSE stream
5. Findings that imply a fix carry an attached `GraphMutation` — "here's the problem,
   and here's the one-click fix as a ghost diff"

Required `Diagnostic` extensions (see §9.5): an `info` severity and a `source` field
(`"validator" | persona slug`) so canvas styling can distinguish machine checks from
agent opinions.

### 5.4 Mapping and auto-consultation — made honest about latency

| Shards Persona | Node Families | Contribution | Tier |
|---------------|--------------|----------------|------|
| Data Analyst | `data.*`, `stats.*` | query correctness, schema consistency | async review |
| Data Scientist | `stats.*`, `ml.*` | statistical assumption checking | async review |
| ML Engineer | `ml.*` | hyperparameter proposals | Mode B consult |
| Data Modeller | `data.*`, `clean.*` | entity resolution, grain, join keys | async review |
| Researcher | `stats.*` | methodology validity | async review |
| AI Engineer | `llm.*`, `eval.*` | prompt safety, eval methodology | async review |
| Backend Engineer | — | generated-code review before export | async review |

The structural rule rev 1 buried in "hard things": **deterministic passes stay
synchronous in `ef.validate`; LLM-backed passes are asynchronous, session-scoped, and
never block canvas interaction.** A `stats.ttest` node dropped on the canvas gets its
deterministic checks instantly; the "is the upstream normally distributed?" persona check
arrives seconds later as a review finding, like a CI comment landing on a PR. Cross-agent
review (Shards' differentiator) is then Mode-A personas consulting each other as they
already do — emergent-flow doesn't reimplement it; it gives the consultation a typed
subject.

---

## 6. Knowledge Ledger — Standalone, Workspace-Level

Shards maintains `.shards/knowledge/` as flat markdown, *workspace-scoped*. Rev 1 hedged
between "a field on `Graph`" and "a standalone model" — it must be standalone: knowledge
is shared across graphs (per-graph copies would fork instantly), and per §4.2 the IR
shouldn't carry it.

```python
class KnowledgeEntry(BaseModel):
    slug: str
    description: str
    subgraph: Graph            # the reusable fragment (Graph nests fine as a payload)
    tags: list[str]
    created_by: str | None     # persona slug
    metrics: dict[str, float] | None
```

- Storage per ADR 0004: metadata tier (in-memory/SQLite locally, Redis hosted). Server
  routes `GET/POST /knowledge`, exposed as agent tools (§2.3).
- Discovery: rev 1's "via the type registry" was hand-wavy — concretely it's matching on
  the fragment's dangling port signature (unbound IN-port types → produced OUT-port
  types, computable with `infer_graph_types`, `emergentflow/codegen/inference.py`) plus
  tag search. Good enough; embedding-based retrieval is a later luxury.
- **Auto-harvest / auto-retrieval** survive as rev 1 described, but as persona behaviors
  (Mode A) using the routes — matching how Shards' ledger already works — with the human
  confirming before anything persists.
- Deduplication/versioning/GC remain real costs (§11); start with slug-uniqueness and
  manual curation, not a solved system.

---

## 7. Autonomous Research as Graph Search

Shards' `[AR]` mode becomes a search over graph space, exactly as rev 1 sketched:

```
Input: base graph G, target metric M, budget B
Loop: generate N candidate mutations → execute each → score against M → keep top K
Output: best graph G_best, metric history
```

The candidates are literally `GraphMutation` lists (§3.1) applied via `apply_mutation`, so
the AR loop and the interactive flow share one mutation vocabulary.

Constraints rev 1 skipped, which gate when this can ship:

- **Cost is the budget, not just iterations.** `execute(G_i)` may train models or call
  LLMs. Budget accounting must meter through the client seam; the execution cache
  (Epic 7, `configure_cache` — `emergentflow/server/app.py:466`) makes candidates sharing
  prefixes affordable and should be a hard prerequisite.
- **Epic 6 (sandboxing) is a dependency**, not a neighbor: an autonomous loop executing
  generated candidate graphs unsupervised is exactly what the executor sandbox exists
  for. AR stays human-triggered-per-iteration until Epic 6 lands.
- `ExperimentRun` (base graph + N scored candidate graphs + history) is a large payload —
  artifact tier per ADR 0004, not metadata; the canvas dashboard reads a summary, not the
  full object.

---

## 8. Panel Review as Session-Scoped Async Passes

Shards' Panel Review (`[PR]`) maps onto §5.3 rather than onto "multi-pass compilation" —
rev 1's framing put LLM calls inside the compiler, which breaks both purity and latency.
Corrected shape:

1. A panel is an ordered list of persona review passes: `[(persona_slug, focus), ...]`
2. Each pass reads the session graph and posts `Diagnostic`-shaped findings + an optional
   fix `GraphMutation` to a shared `ReviewThread`
3. The server dedupes/prioritizes (Syn's coalescing role, if Mode A; a cheap merge pass,
   if Mode B)
4. The canvas renders findings inline on nodes/edges — same rendering path as
   `ef.validate` output, distinguished by `source`

Sequencing conflicting fixes (Shards' panel-report speciality) falls out naturally:
conflicting `GraphMutation`s touch overlapping node ids and are detected mechanically —
something flat-file review can't do.

---

## 9. Preserving Emergent Flow's Invariants

### 9.1 ADR 0002 (Equivalence Gate) — Untouched

Agent-proposed mutations produce ordinary graphs; `compile_to_code` and `execute` consume
them unchanged; the equivalence CI gate is unmodified. Agents are additional *producers
of graphs*, never a third consumer path.

### 9.2 Purity — Maintained (correctly this time)

`compile_to_code`, `execute`, `ef.validate`, and the new `apply_mutation` are pure. All
statefulness (sessions, proposals, gates, knowledge) lives behind server routes — the
same quarantine line that already keeps export I/O in `codegen/export.py` and network I/O
in the injected client. Gate policy is route-level (§4.3), so no pure function reads
workflow state.

### 9.3 Canvas Contract — Extended, Versioned

The canvas↔SDK coupling grows two versioned artifacts: the `GraphMutation` schema and the
session-event schema. Both should be emitted into `ui/src/generated/` by the same
schema-generation flow that produces `ir.schema.json`, and validated with the same ajv
pattern (`ui/src/store/validateIR.ts:16`) — no hand-maintained TS mirrors.

### 9.4 Node Contract — Extended Backward-Compatibly

`NodeDefinition` gains the optional `advisor_persona` ClassVar (§3.3), surfaced via
`to_spec()`. `codegen`/`execute` are unchanged. Note the contract has already been
extended this way once — `requires`/`ClientKind` (ADR 0018,
`emergentflow/nodes/contract.py:161`) layered onto the legacy `requires_client` boolean —
so the precedent and pattern exist.

### 9.5 Diagnostics — One Small, Honest Extension

`Severity` today is `error | warning` (`emergentflow/codegen/validation.py:39`); rev 1's
"green for info" assumed an `info` level that doesn't exist. Add `INFO` to the enum, add
`source: str | None` to `Diagnostic`, and mirror both in `ui/src/store/validation.ts`.
Both models are `frozen`/`extra="forbid"`, so this is an additive, defaulted change —
but it does touch the `/validate` response contract; do it once, early (Phase 1), not
piecemeal.

---

## 10. Implementation Phases

### Phase 0: Graph Sessions + Agent Surface *(new — everything depends on it)*

- `GraphSession` + in-memory session store; routes in `emergentflow/server/app.py`
  (`/sessions` CRUD, proposals, SSE events reusing the `_sse_frame` machinery)
- `emergentflow/ir/mutation.py`: `GraphMutation` + pure `apply_mutation`, with
  property-style tests (apply→validate roundtrips) alongside `tests/test_migrate.py`'s
  patterns
- Canvas: opt-in session mode in `graphStore` (poll or SSE subscribe); no proposal UI yet
- A first Shards persona file that drives the routes via `curl` — proves an agent can
  read, validate, and propose against a live canvas
- **Exit criterion:** a Claude Code agent proposes a two-node addition; the human sees it
  land in the canvas (even as raw JSON in a side panel) and accepts it

### Phase 1: Proposal UX + Diagnostics Extension

- Ghost-node rendering of `GraphMutation` diffs (pending visual state in `graphStore`;
  auto-layout for position-less added nodes)
- Validate-on-propose: server attaches `Diagnostics` to every proposal (§3.1)
- Accept / reject / edit-into-own-state flows; `base_version` conflict handling
- `Severity.INFO` + `Diagnostic.source` (§9.5), mirrored in the UI
- MCP wrapper over the agent routes
- **Proves the pattern** without changing the compiler, executor, or equivalence gate

### Phase 2: Personas + Review Flow

- `AgentPersona` catalog (flat registry, *not* the node registry) + Mode B one-shot
  consult endpoint through `LLMClient` (ReplayClient-tested)
- `advisor_persona` on `NodeDefinition`, surfaced via `to_spec()` / `/catalog`
- Agent-reviews-human flow (§5.3): `ReviewThread` on `CollaborationState`, findings
  rendered via the existing diagnostics path, fix-mutations attached
- 2–3 Mode-A persona files (Data Modeller, Researcher) exercising the review loop

### Phase 3: Gates + Knowledge

- `CollaborationState.gates`; session-scoped compile/execute policy (409 on open gates);
  canvas gate timeline + decision viewer
- Standalone knowledge base: routes, port-signature discovery, auto-harvest/auto-retrieval
  as persona behaviors with human confirmation

### Phase 4: Autonomous Research *(gated on Epic 6 + execution cache)*

- Mutation operators (param vary, node swap, step insert) as `GraphMutation` generators
- Scoring + selection loop over `ef.execute` with client-metered budget
- Canvas experiment dashboard (Shards `[AR]` UI pattern), summary-only reads

---

## 11. What Makes This Hard (And Why It's Worth It)

**Hard:**

- **Shared mutable state is the real cost.** The session document introduces concurrency
  (human edits vs. agent proposals) into a codebase whose superpower is that everything
  is pure and stateless. `base_version` + optimistic concurrency contains it, but this is
  the part to design carefully and test adversarially — not the mutation model, which is
  easy.
- Gates require the agent to stop and wait; keeping enforcement at the session routes
  (§4.3) means graphs without sessions compile instantly, as today.
- LLM-backed review latency: solved structurally by the sync/async split (§5.4), but the
  async UX (findings arriving late onto a graph the human already changed) needs the same
  `base_version` anchoring as proposals.
- The knowledge base needs deduplication, versioning, and garbage collection — flat
  markdown files don't have these problems because nobody expects them to.

**Worth it:**

- Every other visual data/ML tool (KNIME, Alteryx, RapidMiner) requires the human to do
  all the work. Emergent Flow would be the first where the *platform itself* collaborates
  with you — in both directions: agent builds / human reviews, and human builds / agent
  reviews.
- The equivalence gate means every agent-suggested graph is structurally validated and
  execution-equivalent by construction — no flat-file agent workflow, including Shards
  today, can offer that.
- The graph IR constrains the agent's search space: a typed, port-checked mutation is a
  categorically better proposal unit than a text diff, and `validate-on-propose` makes
  bad proposals visible before a human spends attention on them.

---

## Appendix A: Relationship to Epic 6 (Sandboxing)

Epic 6 wraps the executor in sandboxing. Agent LLM interactions already go through the
`LLMClient` seam (ADR 0017). Phase 4 (autonomous research) is *dependent on* Epic 6, not
merely adjacent (§7): unattended execution of generated candidate graphs is the sandbox's
core use case. The session routes are ordinary server code and sandbox-neutral.

## Appendix B: Relationship to ADR 0004 (Storage Tiering)

Sessions, `CollaborationState`, and the knowledge base are metadata — Redis hosted,
in-memory/SQLite locally. `ExperimentRun` payloads (full candidate graphs + histories)
are artifact-tier. Knowledge subgraph payloads are small JSON and stay in metadata.

## Appendix C: Relationship to the Validation Pipeline

`ef.validate` (`emergentflow/codegen/validation.py:263`) remains the single deterministic
gate, pure and synchronous. Agent passes add semantic findings (statistical assumptions,
schema consistency, methodology) as *asynchronous, session-scoped* `Diagnostic` items with
the same anchoring fields (`node_id`, `edge_id`, `port_id`) and severity model (plus the
new `info` level), distinguished by `source`. The canvas renders both through one path —
red dots for errors, yellow for warnings, and info-level persona commentary styled as
review comments rather than validation failures.
