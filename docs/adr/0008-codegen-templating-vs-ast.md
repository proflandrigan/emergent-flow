# ADR 0008 — Codegen uses string templates for functional pipelines and AST construction for the declarative paradigm

- **Status:** Accepted
- **Date:** 2026-06-18
- **Deciders:** Emergent Flow core team

## Context

ADR 0003 commits the SDK to two first-class paradigms: a functional pipeline (a flat DAG of
calls) and a declarative module/graph definition (e.g. an `nn.Module` subclass with `__init__`
and `forward`, compiled from a node's subgraph). `compile_to_code(ir)` (ADR 0002) must emit
correct, idiomatic Python for both, and that Python must satisfy the equivalence invariant
against `execute(ir)`.

The two paradigms do not have the same generation problem. A functional pipeline compiles to a
flat sequence of `out_var = ef.<family>.<fn>(in_var, **params)` statements — one logical
statement per node, with no nesting and no shared indentation context. This is exactly what
`CodeFragment` in `emergentflow/nodes/contract.py` already models today: a structured pair of
`imports` and `body` strings that the whole-graph compiler concatenates in topological order.
The declarative paradigm has the opposite shape: a class body, method bodies inside it, and
indentation that depends on where a fragment lands in that structure. Assembling that by string
concatenation invites exactly the bugs string-based codegen is prone to — misaligned
indentation, broken scoping, fragile escaping — at the point where the generated code is most
structurally complex.

A single emission strategy forced onto both shapes would either over-engineer the simple case
(building a syntax tree for a flat statement list) or under-engineer the complex one (string-
splicing a class body). A decision on how each paradigm is emitted, and how the resulting code
is normalized into one consistent visual style, is needed before the codegen compiler is built.

## Decision

We will dispatch codegen on the graph/node `paradigm` (`emergentflow.ir.common.Paradigm`,
`FUNCTIONAL` vs `DECLARATIVE`) and use a different emission strategy on each branch.

For `Paradigm.FUNCTIONAL`, the compiler emits string templates. Each node contributes a
`CodeFragment` (`imports` + `body`); the compiler de-duplicates imports and concatenates bodies
in topological order. For a flat statement sequence with no nested scope, a string template is
the most readable, most diff-friendly, lowest-ceremony representation — there is no nested
structure to justify the cost of building and rendering a syntax tree. This branch ships in this
epic, Story 5.

For `Paradigm.DECLARATIVE`, the compiler builds a concrete syntax tree with `libcst` and renders
it. The declarative paradigm has genuine nested structure — a class body, method bodies, and
indentation that depends on context — and assembling that by string concatenation is fragile and
error-prone. We choose `libcst` over the standard-library `ast` module because `libcst` is
purpose-built for code generation and codemods: it preserves a faithful concrete syntax
(formatting, comments) and round-trips cleanly, which matters for the glass-box "code you can
read and export" promise (ADR 0002). This branch is proven as a seam in Story 8; its full node
catalog lands later (see Deferred).

Independently of which branch produced the code, the compiler runs a single **`ruff format`**
pass over the assembled module before returning it. Templates and AST construction decide *what
code* is produced; the `ruff format` pass decides its *final shape*. Routing both paths through
one formatting pass guarantees PEP8-clean, visually uniform output regardless of which emission
strategy produced it, and means neither the per-node templates nor the AST generator has to
hand-manage whitespace or line length. We choose `ruff format` over adding `black` because the
repo already standardizes on `ruff` (`[tool.ruff]` in `pyproject.toml`); a second formatter would
be redundant tooling for the same job.

## Consequences

**Positive:**

- Functional-pipeline output stays readable and diff-friendly — each node is one line, changes
  to a graph produce minimal, reviewable diffs.
- Declarative output is assembled as a real syntax tree, so nested class/method structure is
  correct by construction rather than by careful string bookkeeping.
- A single `ruff format` pass guarantees uniform, PEP8-clean output no matter which emission
  strategy produced the code, and removes whitespace/line-length concerns from both generators.
- No second formatter dependency is introduced; the repo's existing `ruff` standardization
  covers codegen output too.
- The emission seam matches ADR 0003's two-paradigm commitment exactly, so the codegen compiler
  has a single, principled branch point rather than ad hoc special-casing.

**Negative / obligations:**

- Two emission code paths must be built, tested, and maintained — a template-based path and an
  AST-based path — rather than one.
- `libcst` becomes a project dependency. It is not needed until the declarative generator lands
  (Story 8 in this epic), but the dependency decision is made now alongside the rest of the
  paradigm-dispatch design.
- Both paths must independently satisfy the ADR 0002 equivalence invariant: for any valid graph,
  the code emitted on either branch must produce artifacts equal to what `execute(ir)` produces.
  Adding the `ruff format` normalization step must not be allowed to change program behavior,
  only its surface formatting.

**Deferred:**

- The `libcst`-based declarative generator is only a *seam* in this epic — proven on a narrow
  slice in Story 8, not a complete generator. The full PyTorch layer catalog and tensor-shape
  codegen are Epic 10; LangGraph/agent codegen is Epic 11.

## Cross-links

- [ADR 0002 — Execute the IR, not the generated string](0002-execute-the-ir-not-the-string.md):
  defines the `compile_to_code`/`execute` equivalence invariant that both emission paths here
  must satisfy.
- [ADR 0003 — The SDK supports two paradigms from day one](0003-sdk-supports-two-paradigms.md):
  establishes the functional/declarative split that this ADR dispatches on.
- ADR 0009 (binding model) and ADR 0010 (package placement) cover the remaining decisions in
  this Story 1 set: how generated variables are named and bound, and where codegen lives in the
  package layout, respectively.
