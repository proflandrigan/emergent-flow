# ADR 0009 — The whole-graph compiler supplies variable names to nodes via a CodegenContext

- **Status:** Accepted
- **Date:** 2026-06-18
- **Deciders:** Emergent Flow core team

## Context

Every node's `codegen` today hardcodes its variable names directly into `CodeFragment.body`.
`emergentflow/nodes/examples/load_csv.py` emits `frame = ef.data.load_csv(...)`, naming its
output literally `frame`. `emergentflow/nodes/examples/anova.py` emits
`result = ef.stats.anova(frame, ...)`, reading its input as literally `frame` and naming its
output literally `result`. `emergentflow/nodes/examples/train.py` emits
`result = ef.ml.train_classifier(frame, ...)`, also naming its output literally `result`. The
contract these nodes implement, `codegen(self, node: Node) -> CodeFragment` (see
`emergentflow/nodes/contract.py`), gives a node no way to learn which names it is actually
supposed to use — it can only guess, and the guess is baked into the template.

Two concrete failures follow from this. First, a node cannot be wired into a real graph: its
input variable must be whatever name the *upstream* node bound its output to, but a hardcoded
`frame` only works if the predecessor happens to have named its output `frame` too. Nothing in
the contract carries an upstream binding down to a downstream input. Second, names silently
collide. `stats.anova` and `ml.train_classifier` both emit `result = …`; placing both in one
graph means the second assignment overwrites the first with no error raised anywhere — a live
correctness bug, not a hypothetical one.

This blocks real multi-node graphs from compiling correctly and must be resolved before Epic 2
can wire nodes together rather than compile them one at a time.

## Decision

We will pass a `CodegenContext` into every node's codegen, evolving the contract to
`codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment`. The concrete signature change
and the migration of the five reference nodes is Story 4 work; what is fixed here is the
decision and the shape of the contract.

The context supplies, for the node currently being compiled, the input variable name bound to
each IN port and the output variable name allocated to each OUT port. Input names are resolved
by the whole-graph compiler from the upstream `(node, OUT port)` that feeds each IN port — the
wiring map itself is Story 2. Output names are minted once by a whole-graph namer so that names
are deterministic, readable, and collision-free across the entire graph — the naming algorithm
itself is Story 3. This ADR does not specify either algorithm; it fixes only that a node asks
the context for names rather than inventing them.

A node therefore no longer invents identifiers. It asks the context for them. The intended
shape is illustrative only — for example `ctx.in_var(port_name)` and `ctx.out_var(port_name)`,
used to emit something like `ctx.out_var("result") = ef.stats.anova(ctx.in_var("frame"), …)`.
These method names are a sketch of the interface, not a commitment; Story 4 fixes the final
API when the contract change actually lands.

Single-node preview is preserved. `CodeFragment` (imports plus body) remains the unit produced
by `codegen`, and `CodeFragment.render()` keeps working for the canvas "show code" panel
(Epic 3). A single-node preview constructs a trivial default `CodegenContext` that falls back
to port names, so `data.load_csv` previewed alone still renders as
`frame = ef.data.load_csv(...)`. No node loses its standalone preview as a result of this
change.

This is the central, riskiest contract change of the epic: it touches the `NodeDefinition`
base (ADR 0005) and every node built against it. Recording the decision here, ahead of the
implementation, lets Story 4 execute it deliberately rather than discover it mid-migration, and
the per-node `version` field that ADR 0005 already defines is the mechanism by which migrated
nodes signal the break. This ADR is one of three decisions made together for Epic 2 Story 1,
alongside sibling ADRs 0008 (templating) and 0010 (package placement / entry points).

## Consequences

**Positive:**

- Real graph wiring becomes possible: an input can finally receive whatever name its upstream
  node was actually given, instead of a name the downstream node guessed.
- The `result`/`result` clobbering bug is eliminated by construction, not by convention — a
  node can no longer choose a colliding name because it no longer chooses names at all.
- Names become deterministic and readable across an entire compiled graph, which is friendly to
  golden-file tests (ADR 0002's equivalence invariant depends on stable output) and to future
  CRDT-based collaborative editing, where stable naming reduces spurious diffs.
- Separation of concerns is restored: a node's codegen describes *what call to make*; the
  compiler — not the node — owns *naming*.

**Negative / obligations:**

- This is a breaking change to the `codegen` contract. Every in-tree node and any third-party
  node built against `NodeDefinition` must migrate to the new signature (Story 4).
- Each migrated node's `version` must bump, per the versioning mechanism ADR 0005 already
  establishes, so the registry can distinguish pre- and post-migration node behaviour.
- `docs/node-contract-spec.md` and `docs/authoring-a-node.md` must be updated once the concrete
  `codegen(node, ctx)` signature lands, so node authors are not working from a stale contract.

**Deferred:**

- The concrete `CodegenContext` type and the final `codegen(node, ctx)` signature, plus the
  migration of the five reference nodes, are Story 4.
- The naming algorithm that allocates output variable names is Story 3.
- The wiring map that resolves input variable names from upstream output bindings is Story 2.
- Package placement and entry-point wiring for the compiler that constructs `CodegenContext`
  are covered by ADR 0010, not here.
