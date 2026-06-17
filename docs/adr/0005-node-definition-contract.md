# ADR 0005 — Node-definition contract: a serializable spec plus Python behaviour

- **Status:** Accepted
- **Date:** 2026-06-16
- **Deciders:** Colony Mind core team

## Context

The IR (Story 2) models a node *instance* on the canvas: it carries a `type` string
(e.g. `"data.load_csv"`) but says nothing about what that type *is* — its ports, its
configurable params, how it compiles to code, how it executes, or how its output type is
inferred. Four very different consumers need that information in one consistent form:

- the **registry** (Story 4) — to index and look up node types;
- **codegen** (Epic 2) — to emit the Python a node contributes;
- the **executor** (Epic 2) — to run the node directly over the IR;
- the **config UI** (Epic 4) — to render a node's configuration panel.

These consumers split along a hard line. The UI runs in the browser and, by the same
constraint that shaped the IR, must work *with no Python present* — so the metadata it needs
(ports, params, defaults, validation hints, version) has to be plain serializable data.
Codegen, execution and type-inference, by contrast, are inherently Python behaviour —
callables that cannot and should not serialize.

A single class that mixed both would either drag Python into the wire format or force the UI
to depend on importing executor code. We need one contract that serves all four consumers
without doing either.

## Decision

We will define the node-definition contract as **two halves bound by one base class**:

1. A **serializable spec** (`colonymind.nodes.spec`): `NodeSpec` — with `PortSpec`,
   `ParamSpec`, and `ValidationHints` — is a pure, JSON-able descriptor (Pydantic models,
   same `IRModel` base as the IR). It carries the type key, per-node `version`, family,
   label, paradigm, declared ports, and declared typed params with their defaults and
   validation hints. This is everything the registry indexes and the config UI renders; it
   contains no Python behaviour.

2. A **behaviour-bearing base class** (`colonymind.nodes.contract.NodeDefinition`, an ABC):
   it declares the same metadata as class attributes and adds the Python behaviour —
   `codegen(node) -> CodeFragment` (the codegen template), `execute(node, inputs) -> dict`
   (the executor), and `infer_types(...)` (shape/type-inference, with a default that returns
   the declared OUT-port types, making it "where relevant" rather than mandatory). It exposes
   `to_spec()` to emit the serializable half, `instantiate()` to mint a valid IR `Node` from
   the declaration, and `validate_node()` to check an instance against the declared
   params + hints.

A node type's catalog identity is its `type` string, which equals the IR `Node.type` and is
the registry key. Each definition also carries a **per-node `version`** integer, bumped on
any contract-affecting change to that node. This is deliberately **distinct from
`Graph.schema_version`**: the schema version tracks the IR wire format for an entire graph;
the per-node version tracks one node type's contract. Story 9 migrations key off both axes.

`codegen` returns a structured `CodeFragment` (`imports` + `body`) rather than a bare string,
so the whole-graph compiler can de-duplicate imports across the graph and concatenate bodies
in order.

## Consequences

**Positive:**

- The frontend consumes `NodeSpec` as plain JSON; it never imports or runs node behaviour.
- Codegen and execution live behind a uniform interface, so the registry, compiler and
  executor treat every node family identically — new families add no core branching.
- `to_spec()` derives the serializable descriptor from the single declared source, so the
  spec and the behaviour cannot describe different ports/params.
- The reference nodes route `execute` and `codegen` through the same runtime helper, making
  the ADR 0002 equivalence invariant testable at node granularity (and tested).

**Negative / obligations:**

- Authors maintain two surfaces (declarative metadata and behaviour) on one class; the
  "how to author a node" guide and `validate_node` exist to keep them honest.
- Every contract-affecting node change obligates a `version` bump and, eventually, a
  migration step (Story 9). The contract makes the obligation explicit but does not enforce
  it automatically yet.

**Deferred:**

- **Discovery and registration** of definitions (the registry / plugin architecture) is
  Story 4; this ADR defines only the contract a registered node conforms to.
- **Real type/shape inference** is Epic 5; `infer_types` here is a token-level placeholder.
- The **production wrapped node families** (pandas, statsmodels, scikit-learn, …) are Story 8,
  built on this base class; the nodes in `colonymind.nodes.examples` are minimal references.
