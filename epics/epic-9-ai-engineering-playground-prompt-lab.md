# Epic 9 — AI Engineering Playground: Prompt Lab (LLM Foundation)

> **Repo ↔ roadmap numbering.** Epic files are numbered by **delivery order in this repo**; the
> [technical roadmap](../planning_docs/technical_roadmap.md) numbers epics **globally**. This file
> is repo **Epic 9**. It delivers the **Prompt Lab / LLM-call foundation** slice of roadmap
> **Epic 11** (*GenAI & Multi-Agent Orchestration*). The *multi-agent orchestration* remainder of
> roadmap Epic 11, and roadmap Epic 12 (the NL→graph canvas agent), are **follow-on epics** — see
> the Program Map below. **Always qualify "repo Epic N" vs "roadmap Epic N"** (see
> [`epics/README.md`](./README.md)).

**Goal (product).** Make Emergent Flow the "must-use" AI-engineering playground. The thing that
earns daily use is the tight loop at the heart of prompt engineering: **write a system + user
prompt, run it across providers/models, compare outputs side by side, label the results, and save
the labeled runs out as a reusable dataset.** This epic ships that loop end to end.

**Lives in:** `emergentflow/` (the LLM client seam, the node families, the eval/label/export
paths) **and** `ui/` (the interactive Prompt Lab panel: compare grid, label buttons, run
history). Per the user's scoping decision this is a **both-trees** epic — bigger than the SDK-first
default, but it puts a usable surface in front of the loop on day one.

**New governing ADR:** [ADR 0017 — LLM/network nodes call an injected client seam](../docs/adr/0017-llm-nodes-injected-effectful-client.md).
Read it before touching anything here; it is how LLM I/O coexists with the ADR-0002 purity/
equivalence invariant that the whole product rests on.

**Dependencies:** Epic 1 (node contract, param schema, registry, `@register`), Epic 2
(`compile_to_code`/`execute` + the golden/equivalence harness — extended here with an injected
client), Epic 3 / roadmap 5 (type tokens + rules-as-data, for the new `LLMResponse`/`PromptSpec`
ports), Epic 4/7 (the local server + streaming — the Prompt Lab panel runs through it), Epic 6
(catalog-as-data export the palette/config panels consume), Epic 7 Story 1–2 (visual payload
extensions + Inspector Results tab the compare grid builds on). One new **optional** runtime
dependency: a unified LLM gateway (see Story 1). Bare `import emergentflow` stays light (ADR 0007).

**Blocks:** repo Epic 10 (Agents/multi-step orchestration — reuses this epic's `LLMClient` seam,
`PromptSpec`, and cost tracking), repo Epic 11 (RAG — grounded generation is an LLM call over
retrieved context), and the quality ceiling of roadmap Epic 12 (NL→graph agent).

---

## Program Map — the three-epic arc (this epic is #1)

The user named six capabilities: prompt authoring/testing, agentic flows, RAG, multi-provider
integration, labeling/feedback, and dataset export. That is a **program**, not one epic. It
decomposes into three sequenced epics, each shippable on its own, each reusing the last one's
seam:

| Repo epic | Name | Delivers | Reuses |
| :-- | :-- | :-- | :-- |
| **Epic 9 (this doc)** | **Prompt Lab** | LLM-call node (completion + structured output), prompt-template node, multi-provider gateway, compare/eval-run, labeling, JSONL dataset export, canvas Prompt Lab panel | — |
| **Epic 10** | **Agentic Flows** | Multi-step agent graphs via the DECLARATIVE/LangGraph seam (ADR 0003): tool nodes, router/conditional nodes, state passing, loops, tool-use/function-calling, live message/token viz | Epic 9's `LLMClient`, `PromptSpec`, cost tracking |
| **Epic 11** | **RAG** | Document loaders/chunkers, embedding + vector-store nodes, retriever node, grounded generation, retrieval eval | Epic 9's LLM call + eval/label loop; Epic 10's agent seam for agentic RAG |

**Where the six capabilities land:** *prompts* → Epic 9. *multi-provider* → Epic 9 (Story 1).
*labeling/feedback* + *dataset export* → Epic 9 (Stories 6–7). *agentic flows* → Epic 10.
*RAG* → Epic 11.

**Scope decisions carried into this epic (from the design interview):**
- **Wedge:** Prompt Lab first.
- **Purity/equivalence:** injected client + record/replay (ADR 0017 — I own it).
- **Providers:** one unified-gateway node (`provider`/`model` params), Anthropic models as the
  default examples (`claude-opus-4-8`, `claude-sonnet-5`, `claude-haiku-4-5-20251001`).
- **Node scope:** completion **+ structured/JSON-schema output**. Streaming and tool-use are
  **deferred** (streaming → server/UI concern; tool-use → Epic 10).
- **Dataset outputs:** **eval sets (JSONL)** and **fine-tuning datasets (messages JSONL)**.
- **Delivery layer:** SDK **and** the canvas Prompt Lab UI, in this epic.

---

## Where things stand entering this epic

- The SDK proves the functional paradigm end to end: data → clean → stats → ML, all through the
  `codegen`/`execute` twin behaviours, with an ADR-0002 equivalence gate in CI.
- Every node so far is a **pure, deterministic** function of its inputs. **No node touches the
  network, secrets, or wall-clock non-determinism.** LLM nodes are the first that must — hence
  ADR 0017.
- ADR 0003 already reserved the DECLARATIVE paradigm for agent graphs (LangGraph). This epic uses
  the **FUNCTIONAL** paradigm only: an LLM call is one node → one inspectable `LLMResponse`.
  Agent-graph structure is Epic 10.
- The server (Epic 4/7) runs `ef.*` in-process with streaming progress and an Inspector Results
  tab — the surface the Prompt Lab panel plugs into.
- `@public_op` enforces that every public return is serializable + inspectable. A live provider
  SDK response object would violate that; `LLMResponse` (Story 2) is the inspectable carrier.

---

## Definition of Done (epic-level)

- [ ] **ADR 0017 accepted**, and `execute`/`compile_to_code` thread an injected `LLMClient`; graphs
      with no LLM nodes are byte-for-byte unchanged (back-compat gate).
- [ ] **ADR-0002 equivalence holds for LLM graphs by construction:** the equivalence harness runs
      both `execute` and the compiled module against the **same `ReplayClient`**, proving
      value-equivalent artifacts. **CI never hits the network.**
- [ ] **Both functions stay pure** given a pure (replay) client — no node imports a provider SDK,
      reads `os.environ`, or opens a socket; the only effect is the injected `GatewayClient`, and
      it lives at the edge alongside `export.py` (ADR 0002).
- [ ] **`@public_op` inspectable contract respected:** LLM results ride inside `LLMResponse`
      (text / parsed structured output + `usage` + `cost_usd` + `latency_ms` + `finish_reason`),
      all JSON-native / tidy-DataFrame. No live SDK object ever enters a response.
- [ ] **Provider-agnostic:** one `ef.llm.call` node reaches ≥3 providers through the gateway;
      Anthropic is the documented default. Provider/model are params, not separate node types.
- [ ] **Secrets never in the IR or emitted code:** keys are referenced by env-var **name**;
      the graph JSON and generated Python contain **no** literal key. A test asserts this.
- [ ] **The loop is real in the canvas:** a user can, in the Prompt Lab panel, edit a system+user
      prompt with variables, run it across N model variants over a small input set, see a
      side-by-side compare grid with per-cell cost/tokens/latency, label cells, and export the
      labeled runs as JSONL — without writing code.
- [ ] **Golden + equivalence tests** for every new node; **eval-set JSONL and fine-tune JSONL
      exports** each have a schema-validated fixture test.
- [ ] Every new runtime dep is **optional** (`emergentflow[llm]`), license-checked
      (Apache-2.0-compatible), and documented in `docs/licensing-and-dependencies.md`; bare
      install stays light.

---

## Story 1 — The `LLMClient` seam + unified gateway (ADR 0017)

Establish the injected-client boundary that every later story depends on.

- Write **ADR 0017** (status → Accepted on review).
- Define the `LLMClient` protocol: `complete(request: LLMRequest) -> LLMResponse`. `LLMRequest`
  is a pure, JSON-native dataclass (provider, model, messages `[{role, content}]`, params:
  `temperature` default `0`, `max_tokens`, optional `response_schema`). `LLMResponse` is the
  inspectable dataclass (Story 2).
- Ship two implementations:
  - `ReplayClient` — pure; replays a recorded `LLMResponse` keyed by a **stable content hash** of
    the `LLMRequest`; raises `FixtureMissError` on a miss (with a copy-pasteable re-record hint).
  - `GatewayClient` — effectful; routes to the provider through a **unified gateway** (LiteLLM,
    MIT — Apache-2.0-compatible — added as optional `emergentflow[llm]`). Resolves the API key
    from the env-var **name** carried in the request/config; never from the IR.
- Thread the client through the seams: `execute(graph, *, client: LLMClient | None = None)` and a
  compiled entry point that accepts `client`. When a graph has **no** LLM nodes, `client` is
  unused and behaviour is unchanged.
- Fixtures are content-addressed and checked in; a documented `--record` path (re-records against
  a live provider, gated behind an env flag) regenerates them.

**Acceptance:** a trivial graph with one LLM node runs under `ReplayClient` in `execute` and in
the compiled module, producing identical `LLMResponse`; the equivalence harness passes with **no
network access**; `GatewayClient` reaches a real provider in a manual (non-CI) smoke test.

---

## Story 2 — `ef.llm.call` node: completion + structured output

The core node. FUNCTIONAL paradigm: one call → one inspectable `LLMResponse`.

- Params: `provider`, `model`, `temperature` (default `0`), `max_tokens`, `response_format`
  (`"text"` | `"json"`), optional `response_schema` (JSON Schema; when set, output is parsed +
  validated and rides as a dict).
- IN ports: `messages` **or** the wired output of a `ef.llm.prompt` node (`PromptSpec`, Story 3).
  OUT port: `LLMResponse`.
- `LLMResponse` (inspectable dataclass): `text: str | None`, `data: dict | None` (parsed
  structured output), `model`, `usage: {input_tokens, output_tokens}`, `cost_usd`, `latency_ms`,
  `finish_reason`. JSON-native — satisfies `@public_op`. A live SDK object is **never** exposed.
- `codegen` emits an `ef.llm.call(...)` invocation that takes `client` from the compiled entry
  point; `execute` calls the same wrapper with the injected client. Same seam → ADR-0002
  equivalence by construction (the sklearn-adapter trick, applied to the LLM call).
- Cost is computed from a small per-model price table (pure function of `usage`); latency is
  reported by the client, so it stays out of the pure request-building path.

**Acceptance:** golden test on the emitted module; equivalence test under `ReplayClient` for both
`text` and `json` output; a JSON-schema-validated structured-output fixture; a test asserting the
IR JSON and emitted code contain no API key.

---

## Story 3 — `ef.llm.prompt` template node (system + user, variables)

Author reusable prompts with typed variables — the "write prompts" half of the loop.

- Params: `system` (template str), `user` (template str), declared `variables` (name → type).
- Templating is **pure, deterministic, and non-executing**: a constrained `{{var}}` substitution
  (no arbitrary code, no I/O). Jinja2 is noted as a possible later upgrade but is **not** pulled
  in for the MVP (keeps purity + dependency surface minimal).
- IN port: a `variables` binding (a dict / one row of a dataset). OUT port: `PromptSpec` (a
  JSON-native `{system, user, messages}` dataclass) that feeds `ef.llm.call`.
- Missing/extra variables raise a validation error at `execute`/compile time (shared gate), so the
  canvas can surface it before a run.

**Acceptance:** golden + equivalence tests; a variable-substitution unit test incl. the
missing-variable error; wiring test `prompt → call`.

---

## Story 4 — Cost / token / latency as first-class inspectables

Table-stakes for a "must-use" lab: every run shows what it cost.

- Surface `usage`, `cost_usd`, `latency_ms` on `LLMResponse` (Story 2) and aggregate them across
  an eval run (Story 5) into a tidy summary DataFrame (total cost, tokens, p50/p95 latency).
- Add a per-model price table (`emergentflow/llm/pricing.py`) as plain data, easy to update; cost
  is a **pure** function of `(model, usage)`.
- Optional `budget_usd` guard on the eval run: a `BudgetClient` decorator around any `LLMClient`
  that raises before exceeding a ceiling (keeps the guard at the client edge, not in nodes).

**Acceptance:** cost/token aggregation test with fixed fixtures; budget-guard test that trips at
the ceiling.

---

## Story 5 — Compare / eval-run harness (`ef.eval.run`)

The engine behind side-by-side comparison — run one prompt over N inputs × M model variants.

- `ef.eval.run` takes: a `PromptSpec` (or prompt node), a **dataset** (list of variable-binding
  rows), and one or more **variants** (`{provider, model, params}`). Produces a **tidy DataFrame**:
  one row per `(input_row, variant)` with `input`, `output` (text or structured), `usage`,
  `cost_usd`, `latency_ms`.
- Deterministic under `ReplayClient` (fixtures keyed by request hash), so the compare grid is
  reproducible and CI-safe.
- Pure: the harness builds requests and delegates every call to the injected client; no I/O of its
  own.

**Acceptance:** golden + equivalence tests over a 2-input × 2-variant matrix; the result DataFrame
is inspectable per `@public_op`; determinism proven by re-running under the same replay client.

---

## Story 6 — Labeling / feedback capture (`ef.eval.label`)

Turn runs into judged data — the "provide feedback" capability, kept pure.

- Human labels are **input data**, not interactive I/O inside `execute`: `ef.eval.label` merges a
  labels frame (`row_id`, `variant`, `label`, optional `score`, optional `rubric`/`note`) into the
  eval-run DataFrame. The interactivity lives in the UI (Story 8); the node is a pure join.
- Supports the label shapes the export formats need: pass/fail + score (eval sets) and
  chosen/rejected picks over a variant pair (kept available for a later preference-pairs export,
  though only eval-set + fine-tune JSONL are in-scope exports for this epic).

**Acceptance:** join/merge unit tests incl. partial labels; inspectable labeled DataFrame;
equivalence test (pure over its inputs).

---

## Story 7 — Dataset export (eval-set JSONL + fine-tune JSONL)

The "save out datasets" payoff. **All file I/O lives in `export.py`** (ADR 0002) — never in a
node's `execute`/`codegen`.

- `ef.export_eval_set(df, path)` → JSONL rows `{input, output, label, score?, rubric?}` for
  regression-testing prompts/agents over time.
- `ef.export_finetune(df, path)` → provider-shaped messages JSONL:
  `{"messages": [{"role":"system",...},{"role":"user",...},{"role":"assistant",...}]}`.
- Both validate against a documented schema before writing; both are exposed as `@public_op`
  operations that return a small manifest (path, row count, byte size) — inspectable, no raw file
  handle.

**Acceptance:** schema-validated fixture tests for both formats; round-trip test (export → re-load
→ shape check); a test asserting exports carry no secret/key fields.

---

## Story 8 — Canvas Prompt Lab panel (`ui/`)

Put the loop in front of the user without code. Consumes the catalog + the server run endpoint
(Epic 7 streaming); runs go through the server-injected `GatewayClient`.

- **Prompt editor:** system + user fields with `{{variable}}` highlighting; a variable table.
- **Variant picker:** multi-select provider/model rows to compare (Anthropic models default).
- **Input set:** a small editable table of variable-binding rows (or "single run" mode).
- **Run:** streams progress; renders a **side-by-side compare grid** (rows = inputs, columns =
  variants), each cell showing the output + a cost/tokens/latency badge (Epic 7 Story 1 payloads).
- **Label controls:** per-cell pass/fail + score (and chosen/rejected across a pair), writing back
  through `ef.eval.label`.
- **Run history:** past runs reproducible via the replay fixtures.
- **Save dataset:** one click → `ef.export_eval_set` / `ef.export_finetune`, downloaded as JSONL.

**Acceptance:** an end-to-end UI test (against a stubbed/replay server client) driving edit → run →
compare → label → export; the panel reads provider/model choices from the catalog-as-data (no
hard-coded model list).

---

## Story 9 — Secrets & provider configuration

Make BYO-key safe and obvious, consistent with ADR 0017.

- Keys are referenced by **env-var name** in the node/graph config (e.g.
  `api_key_env="ANTHROPIC_API_KEY"`), resolved by `GatewayClient` at call time. The IR and emitted
  code carry only the name.
- The server/CLI validates that the named env var is present **before** a run and returns a clear,
  actionable error if not (never echoing the value).
- Docs: a short "bring your own key" guide; the compiled module's docstring shows the exact
  `export ANTHROPIC_API_KEY=...` a user needs to run the emitted script themselves.

**Acceptance:** a test proving no literal key appears in IR JSON or emitted code; a missing-key
error-path test; docs updated.

---

## Notes / Risks

- **The equivalence gate is about the pure core, not the provider.** Under `ReplayClient`,
  `execute ≡ compiled` value-exactly. We deliberately do **not** assert anything about live,
  non-deterministic provider output — that would be a category error. This is the whole point of
  ADR 0017; reviewers should not "fix" the gate to call the network.
- **Fixture maintenance.** Prompt/param changes invalidate recorded fixtures. Mitigate with the
  documented `--record` mode and content-addressed fixture files so churn is visible in diffs.
- **Gateway vs. native features.** The unified-gateway choice trades some provider-specific power
  (e.g. Anthropic prompt caching, provider-unique params) for breadth. Acceptable for the wedge;
  a native Anthropic path can be added later behind the same `LLMClient` protocol without
  reworking nodes.
- **Streaming & tool-use are deferred on purpose.** Streaming is a server/UI concern that doesn't
  change the equivalence story (the gate compares the assembled final response). Tool-use loops
  back into the graph and is the heart of Epic 10; pulling it forward would complicate the
  day-one purity story for little wedge value.
- **Cost table drift.** The per-model price table is plain data and will go stale; keep it
  editable and out of the equivalence-critical path (cost is a derived inspectable, not an artifact
  the gate compares byte-for-byte).
- **Both-trees scope.** Bundling the UI (Story 8) makes this epic larger and couples SDK + `ui/`;
  Stories 1–7 (SDK) can land and gate green independently, with Story 8 following — sequence them
  so CI stays green throughout.
