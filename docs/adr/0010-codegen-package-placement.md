# ADR 0010 — The codegen engine lives in emergentflow/codegen with ef.compile_to_code and ef.execute as entry points

- **Status:** Accepted
- **Date:** 2026-06-18
- **Deciders:** Emergent Flow core team

## Context

[ADR 0002](0002-execute-the-ir-not-the-string.md) commits the project to two pure functions
over the same graph IR — `compile_to_code(ir)`, which renders a human-readable Python module
for display, export, and Git publishing, and `execute(ir)`, which production calls directly to
produce results. Neither function exists yet, and neither has a package home or a public entry
point. Before either can be built (Stories 5 and 6), the engine needs a place to live and a
way for SDK users to reach it, consistent with the package conventions already established
elsewhere in the codebase.

Two existing conventions constrain the placement. First, `emergentflow/__init__.py` keeps
`import emergentflow as ef` lightweight by lazily importing its functional families — `data`,
`clean`, `stats`, `ml`, `reports` — through a module-level `__getattr__` over a
`_LAZY_FAMILIES` frozenset; the heavy scientific stack behind each family is only imported on
first access. Second, [`docs/package-layout.md`](../package-layout.md) documents the current
top-level layout — `emergentflow/ir/` for the graph schema and `emergentflow/nodes/` for the node
contract, registry, and examples — alongside the flat `ef.<family>` verb namespaces, and
[`docs/public-api-conventions.md`](../public-api-conventions.md) governs what a public `ef.*`
return value must look like. The compiler and executor are not domain operations like
`ef.stats.anova`; they are whole-graph verbs that operate on an entire IR rather than a single
node family, so they do not obviously fit the existing namespace pattern and need an explicit
decision on where they sit and how they surface.

## Decision

We will house the compiler and executor together in a new top-level package,
`emergentflow/codegen/`. Both functions are two readings of the same IR and share the same graph
traversal and wiring plumbing (Story 2), so co-locating them keeps the equivalence pair — see
below — close together in the source tree rather than split across unrelated packages. The
internal module layout (for illustration only, finalized in Stories 5–6) might look like
`compiler.py` for `compile_to_code` and `executor.py` for `execute`, plus shared traversal and
context helpers; these module names are not commitments, only a sketch of the shape.

We will expose the engine through two public entry points, `ef.compile_to_code(graph) -> str`
and `ef.execute(graph) -> results`, at the top level of the `emergentflow` package rather than
under a family namespace, because they act on a whole graph rather than a single domain
operation. Both are added to `__all__` and surfaced through the same lazy `__getattr__`
mechanism already used for `data`, `clean`, `stats`, `ml`, and `reports`, so `import emergentflow
as ef` stays lightweight and the codegen package is only imported the first time a caller
touches `ef.compile_to_code` or `ef.execute`.

`compile_to_code` returns an inspectable `str` — the generated module source, suitable for
display and export as-is. `execute` returns results keyed by node and port that satisfy the
inspectability contract enforced elsewhere in the SDK (`emergentflow.api.is_inspectable`), per
`docs/public-api-conventions.md`. Both functions are pure: no I/O, no global state, no hidden
side effects beyond what their signatures declare. Purity is a deliberate hook for Epic 6, which
must wrap `execute` in sandboxing, resource limits, and streaming without re-architecting it.

We restate, and explicitly tie to ADR 0002, the project's central trust invariant: for any
valid graph IR, the artifacts produced by `ef.execute(ir)` must equal the artifacts produced by
running the code emitted by `ef.compile_to_code(ir)`. This ADR does not weaken or relitigate
that invariant — it only fixes where the two functions live and how they are reached. Story 6
builds the equivalence harness and Story 9 wires it, together with golden tests, into CI. The
same carve-out from ADR 0002 applies unchanged: the raw-Python escape-hatch node, sandboxed in
Epic 6, is exempt from the equivalence invariant.

This ADR sits alongside ADR 0008 and ADR 0009 as the rest of the Epic 2 Story 1 decision set.

## Consequences

**Positive:**

- The compiler and the executor have a single, discoverable home, and that home keeps the
  ADR-0002 equivalence pair physically close in the source tree.
- The entry points match the existing flat `ef.<verb>` style and reuse the lazy-import pattern
  already proven for the functional families, so adding the engine does not change the cost of
  a bare `import emergentflow as ef`.
- Purity on both functions keeps Epic 6's sandbox wrap a clean addition rather than a rewrite.
- Restating the equivalence invariant here, with an explicit link back to ADR 0002, keeps the
  project's central trust gate visible wherever the engine's placement is documented.

**Negative / obligations:**

- `docs/package-layout.md` will need a new row or section for `emergentflow.codegen` once the
  package lands (Stories 5–6); this ADR does not update that document itself.
- `emergentflow/__init__.py` will need `__all__` and `__getattr__` extended to cover
  `compile_to_code` and `execute`; this ADR does not make that edit.
- The equivalence invariant remains a standing CI obligation: any change to the compiler or the
  executor must be re-verified against the golden/property-based corpus from ADR 0002 (Stories
  6 and 9).

**Deferred:**

- The actual implementations of `compile_to_code` (Story 5) and `execute` (Story 6), and the
  final internal module layout of `emergentflow/codegen/` — the `compiler.py` / `executor.py`
  names above are illustrative only and may change.
- The production sandboxed runtime for the raw-Python escape-hatch node (Epic 6).
- Git and project export of the generated code (Epic 14).
