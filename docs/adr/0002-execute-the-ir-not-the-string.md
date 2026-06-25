# ADR 0002 — Execute the IR, not the generated string

- **Status:** Accepted
- **Date:** 2026-06-16
- **Deciders:** Emergent Flow core team

## Context

There are two ways to "run" a graph in Emergent Flow. Option (a): generate a Python string from
the IR and `exec()` it. Option (b): interpret the IR directly by calling SDK functions at
runtime.

Option (a) makes "what you see is what runs" trivially true — the same string the user views
in the UI is the string that executes. However, it means production servers routinely call
`exec()` on generated code, which is both a security liability (arbitrary code execution
surface) and a reliability liability (the generated string must be parseable and safe in every
environment where execution is triggered).

Option (b) is safe and testable: production never calls `exec()`, and the execution path is a
direct traversal of a well-typed data structure. The risk is that the *displayed* code (the
string shown to users and exported to Git) can drift from what *actually executed* if
`compile_to_code(ir)` and `execute(ir)` are maintained independently and allowed to diverge.

A clear policy that resolves this trade-off is required before any execution logic is built.

## Decision

We will build two pure functions over the same IR: `compile_to_code(ir)` and `execute(ir)`.
Production will execute the IR directly via `execute(ir)`; the generated Python string
produced by `compile_to_code(ir)` is for display, export, and Git publishing only — it is
never `exec()`-ed in production. The equivalence of these two functions is a hard invariant:
for any valid graph IR, the artifacts produced by `execute(ir)` must equal the artifacts
produced by running the code emitted by `compile_to_code(ir)`.

The sole exception is the "raw Python" escape-hatch node, which allows users to embed
arbitrary Python inside a graph. That node type lives entirely behind the sandbox introduced
in Epic 6 and is explicitly carved out from the equivalence invariant.

## Consequences

**Positive:**

- Production never calls `exec()` on generated code, eliminating the corresponding security
  and reliability liability.
- `execute(ir)` operates on a typed, traversable data structure, making execution logic
  straightforward to unit-test in isolation.
- The "glass-box" promise is preserved: the code users see via `compile_to_code(ir)` is a
  faithful human-readable representation of the graph, even though it is not the execution
  path.

**Negative / obligations:**

- The equivalence of `compile_to_code(ir)` and `execute(ir)` must be continuously enforced.
  This is the project's central trust quality-gate: if the two functions drift, the displayed
  code stops describing what the system actually does. Maintaining that guarantee requires a
  corpus of golden and property-based tests that verify, for a representative set of graphs,
  that the artifacts produced by `execute(ir)` match those produced by running the output of
  `compile_to_code(ir)`. Adding new node types or IR features obligates a corresponding
  expansion of this test corpus.

**Deferred:**

- The raw-Python escape-hatch node and its sandboxing mechanism are explicitly deferred to
  Epic 6. Until that sandbox exists, raw-Python nodes are not supported in production
  execution.
