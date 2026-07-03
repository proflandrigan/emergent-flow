# Epic 10 — Agentic Flows (Multi-Step Orchestration)  ·  *stub*

> **Status: STUB.** Scaffolding only — this epic is not decomposed to implementation depth yet.
> It is drafted alongside [Epic 9](./epic-9-ai-engineering-playground-prompt-lab.md) to pin the
> arc (see Epic 9's *Program Map*). Flesh it out when Epic 9 lands and its `LLMClient` seam is
> proven.

> **Repo ↔ roadmap numbering.** Repo **Epic 10**. Delivers the **multi-agent orchestration**
> remainder of roadmap **Epic 11** (*GenAI & Multi-Agent Orchestration*) that Epic 9 left to a
> follow-on, and raises the quality ceiling of roadmap **Epic 12** (NL→graph agent). **Always
> qualify "repo Epic N" vs "roadmap Epic N"** (see [`epics/README.md`](./README.md)).

**Goal (product).** Let users build **agentic flows** on the canvas — multi-step LLM programs that
call tools, branch on model output, pass state between steps, and loop — and get idiomatic,
exportable Python for them. This is the second wedge in the AI-engineering-playground arc: once
you can write and test a *prompt* (Epic 9), you compose prompts + tools + control flow into an
*agent*.

**Paradigm:** **DECLARATIVE** (ADR 0003). An agent graph is a stateful, cyclic-ish control-flow
object, not a flat DAG of calls — the same class of thing as the `nn.Module` seam, compiled into a
graph object (LangGraph) rather than a chain of statements. ADR 0003 explicitly reserved this and
today's declarative seam raises `CodegenError` pointing here; **this epic lifts that.**

**Reuses from Epic 9:** the injected `LLMClient` seam and record/replay ([ADR 0017](../docs/adr/0017-llm-nodes-injected-effectful-client.md)),
`PromptSpec`, `LLMResponse`, cost/token tracking, and the eval/label/export loop (agents are
evaluated with the same harness). **Adds:** tool/function-calling (deferred out of Epic 9 on
purpose), router/conditional nodes, state passing, and bounded loops.

**Lives in:** `emergentflow/` (agent node family + declarative/LangGraph codegen + execute) **and**
`ui/` (live message/token viz down graph edges, per the roadmap's Epic 11 promise).

---

## New governing decisions this epic must make (ADRs to write)

- **ADR (proposed) — Agent-graph codegen & execution.** How an agent graph compiles to a
  LangGraph object via AST (extending ADR 0008's declarative branch), how `_prepare_declarative`
  (the single validation gate shared by compiler + executor) accepts agent graphs, and how the
  executor runs the same graph in-process for the ADR-0002 equivalence gate.
- **ADR (proposed) — The `LLMClient` seam under multi-turn + tool loops.** Extend ADR 0017 so a
  tool-calling loop (model → tool call → tool result → model) is fully record/replayable: tool
  invocations and their results become fixtures too, keeping `execute ≡ compiled` value-exact in
  CI with **no** network access.
- **Cyclic control flow in the IR.** `traversal.py` does cycle detection for the FUNCTIONAL
  paradigm; agent graphs allow **controlled** cycles (loops with a bound / termination
  condition). The IR must model a loop/branch construct without reopening arbitrary-cycle support
  for functional graphs.

---

## Where things stand entering this epic (assumed)

- Epic 9 shipped: `ef.llm.call` (completion + structured output), `ef.llm.prompt`, the injected
  client seam, cost tracking, the eval/label/export loop, and the Prompt Lab panel.
- ADR 0003's declarative paradigm plumbing exists but is wired only for `nn.Module` linear chains;
  agent/LangGraph targets still raise `CodegenError`.
- Tool-use and streaming were deferred by Epic 9 and are picked up here.

---

## Definition of Done (epic-level, provisional)

- [ ] Agent graphs compile to **idiomatic LangGraph** Python (declarative paradigm, ADR 0003) and
      run in-process under `execute`, with the ADR-0002 equivalence gate green under a shared
      `ReplayClient` — **CI never hits the network**, including tool loops.
- [ ] Both `execute` and `compile_to_code` stay pure given the injected client; the only effect is
      the client at the edge (ADR 0017 extended to tool loops).
- [ ] A user can, on the canvas, wire prompt + tool + router/conditional nodes into a bounded
      multi-step agent, run it, and watch messages/tokens flow down edges (live viz).
- [ ] Tool/function-calling is first-class: tool nodes declare a schema; the model's tool calls are
      validated, dispatched, and fed back; loops terminate on a bound or condition.
- [ ] Agents are evaluated + labeled + exported through Epic 9's harness (an agent is just a
      callable under `ef.eval.run`).
- [ ] Golden + equivalence tests for the new node types; new deps optional + license-checked
      (LangGraph is MIT — Apache-2.0-compatible).

---

## Story skeleton (to expand)

1. **ADRs + the declarative agent-graph seam** — lift the `CodegenError`; extend
   `_prepare_declarative`, the AST/libcst codegen branch, and the in-process executor to agent
   graphs; extend record/replay to tool loops.
2. **Agent + tool nodes** — an agent node owning a subgraph; tool nodes with declared
   input/output schemas dispatched from model tool calls.
3. **Router / conditional + state** — branch on model output; pass typed state between steps;
   bounded loops with a termination condition.
4. **Tool-use / function-calling** (the piece Epic 9 deferred) — end-to-end model→tool→model
   round-trip, fully replayable.
5. **Live message/token viz** (`ui/`) — stream messages down edges during a run (server/UI;
   doesn't change the equivalence story — the gate compares assembled final state).
6. **Agent eval + export** — reuse Epic 9's eval/label/JSONL loop for agent trajectories.

---

## Notes / Risks

- **This is the big declarative build.** Expanding the declarative seam from linear `nn.Module`
  chains to cyclic agent graphs is the largest single lift in the arc; scope it as its own epic,
  not a Prompt Lab add-on.
- **Tool loops and purity.** Keeping tool-calling loops value-exact under replay is the hard part
  — tool *side effects* (a tool that hits the network) must themselves go through an injectable
  seam or be marked effectful, mirroring ADR 0017. Design this in the ADR before coding.
- **Cyclic IR must not leak into functional graphs.** Keep the loop/branch construct scoped to the
  declarative paradigm so `traversal.py`'s functional cycle-detection invariant is untouched.
