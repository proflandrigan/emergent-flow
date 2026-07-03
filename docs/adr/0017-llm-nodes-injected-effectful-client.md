# ADR 0017 — LLM/network nodes call an injected client seam; the effect lives at the edge

- **Status:** Accepted
- **Date:** 2026-07-02
- **Deciders:** SDK maintainers (proflandrigan)

## Context

Repo Epic 9 (the Prompt Lab / "AI Engineering Playground" wedge) introduces the first nodes
whose behaviour is **non-deterministic network I/O**: an LLM call node that sends a prompt to a
provider (via a unified gateway) and returns a completion. Every prior node family has been a
pure, deterministic function over its inputs. LLM nodes are not — the same inputs can yield
different text, they touch the network, they cost money, and they depend on secrets.

This collides head-on with the two invariants the whole product rests on:

- **ADR 0002** requires that running the code from `compile_to_code(ir)` produce artifacts
  **equivalent** to `execute(ir)`, and that **both functions stay pure** — no I/O, no global
  state — so Epic 6 can later wrap `execute` in a sandbox. This equivalence is a CI gate.
- **ADR 0001** keeps the graph IR the single source of truth, and the IR must stay
  serializable and shareable — it cannot embed a live network client or a literal API key.

The technical roadmap already anticipated the friction ("LLM nodes break the deterministic
cache — needs a cache-with-care path"). The forces to reconcile:

1. **Purity** — `execute` and `compile_to_code` must remain pure functions of the IR.
2. **Equivalence** — the ADR-0002 gate must still be able to prove `execute ≡ compiled` for
   graphs containing LLM nodes, without hitting the network in CI.
3. **Real usage** — in production the compiled module and a live `execute` must actually call
   the provider.
4. **Secrets** — API keys must never be written into the IR or the emitted code as literals.

The rejected alternative was a new "effectful" node tier **exempt** from the equivalence gate,
with equivalence weakened to "same request shape" rather than value equality. That punches a
permanent hole in the invariant the product rests on and forks the node contract. We keep the
invariant intact instead.

## Decision

**We will quarantine the effect behind an injected client seam, so the pure core stays pure and
the equivalence gate stays value-exact.**

1. **A `LLMClient` protocol is the single seam.** It has one job: `complete(request) ->
   LLMResponse`, where `request` is a fully-built, deterministic, JSON-native structure
   (model, messages, params) and `LLMResponse` is the inspectable dataclass (text / parsed
   structured output, `usage`, `cost_usd`, `latency_ms`, `finish_reason`). Building the request
   from node inputs is **pure**; sending it is the **only** effect, and it lives entirely
   inside the client.

2. **The client is injected, never constructed inside a node.** `execute(graph, *, client=...)`
   accepts a client; `compile_to_code` emits a module whose entry point accepts a `client`
   parameter (defaulting to a factory the caller wires up). Nodes call `ctx`-resolved
   `client.complete(...)` — they never import a provider SDK, read `os.environ`, or open a
   socket. This mirrors how all filesystem I/O already lives at the edge in `export.py`: the
   effect is pushed to the boundary and the middle stays pure.

3. **Two client implementations ship.** A `ReplayClient` (pure — replays recorded responses
   keyed by a stable hash of the request; raises on a miss) is the default in tests and the
   ADR-0002 equivalence harness. A `GatewayClient` (effectful — the real network call through
   the unified gateway) is what production wires in. Because both `execute` and the compiled
   module are handed the **same `ReplayClient`** in the gate, they build identical requests,
   replay identical responses, and produce **value-equivalent** artifacts — the ADR-0002 gate is
   unchanged, just parametrized with a client.

4. **`execute` and `compile_to_code` remain pure functions of `(ir, client)`.** Given a pure
   client (the replay client), both are pure and deterministic. The impurity is exactly and only
   the client you choose to inject — an explicit, sandboxable boundary, not a property smeared
   through the node graph.

5. **Secrets never enter the IR or the emitted code.** The IR references a key by **env-var
   name** (e.g. `api_key_env="ANTHROPIC_API_KEY"`); the `GatewayClient` resolves it from the
   environment at call time. The compiled module reads `os.environ[...]`; no literal key is ever
   serialized, logged, or committed.

6. **Determinism knobs are first-class.** Requests default to `temperature=0` (and a seed where
   the provider supports it) so recorded fixtures are stable and re-recording is cheap. Fixtures
   are content-addressed by request hash and checked in, so CI never touches the network.

## Consequences

**Easier / positive**

- ADR 0002 survives intact: one equivalence gate, value-exact, now parametrized by an injected
  client. No second-class node tier, no forked contract, no weakened invariant.
- `execute`/`compile_to_code` stay pure and therefore stay sandboxable for Epic 6.
- The IR stays serializable, shareable, and secret-free; a `.ef.json` graph can be committed or
  sent to a teammate without leaking keys.
- Provider-agnosticism falls out for free: swapping `GatewayClient` for a fake, a caching, or a
  budget-guard client is a one-line injection, not a node change.
- Cost/token/latency tracking rides on `LLMResponse` and is inspectable by construction under
  `@public_op`.

**Harder / negative**

- `execute` and the compiled entry point grow a `client` parameter — a small signature change
  that must thread through the server (Epic 7) and the CLI. Back-compat: `client` defaults such
  that graphs with **no** LLM nodes behave exactly as before.
- Recorded fixtures are now test artifacts to maintain; a prompt/param change invalidates a
  fixture and requires a re-record step (a documented `--record` mode mitigates this).
- The equivalence gate proves `execute ≡ compiled` **under a fixed client**; it does *not* prove
  anything about live-provider output (which is non-deterministic by nature). That is correct
  and intended — value-equivalence is a statement about the pure core, not about the provider.

**Deferred**

- Tool-use / function-calling (loops back into the graph) is out of scope here and handled by
  the Agents epic; the `LLMClient` protocol is designed to extend to it without a rewrite.
- Streaming is deferred; `complete` is unary for now. A streaming variant is an additive method
  on the protocol, consumed by the server/UI, and does not change the equivalence story (the
  gate compares the assembled final response).
- Response/prompt caching across runs is a caching `LLMClient` decorator, layered later without
  touching nodes.
