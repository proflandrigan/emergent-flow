# ADR 0011 — Nominal type model with an optional subtype relation and three-valued compatibility

- **Status:** Accepted
- **Date:** 2026-06-20
- **Deciders:** Colony Mind core team

## Context

Epic 1 gave the IR the *shape* of a type system but none of its *substance*. Every port
carries a `data_type` token (`colonymind/ir/port.py`) — but it is an opaque free string
defaulting to `"any"`, and tokens like `DataFrame`, `ClassifierResult`, `AnovaResult`,
`HTML`, and `Tensor` are used ad hoc across the reference nodes in
`colonymind/nodes/examples/` with no registry to give them meaning. Every edge carries a
`type_compatible: bool | None` field (`colonymind/ir/edge.py`), but nothing ever fills it
in — it is permanently `None`. `NodeDefinition.infer_types` (`colonymind/nodes/contract.py`)
exists, but its default merely echoes each OUT port's declared `data_type`, and nothing calls
it across a graph. `Graph._validate_structure` checks node/port existence and OUT→IN
direction, but never type compatibility and never cardinality. The codebase is littered with
`# … is Epic 5` placeholders marking exactly these gaps.

The result: an invalid graph — wiring an `HTML` output into a `DataFrame` input — is caught,
if at all, only as a runtime crash deep inside `execute`, with no machine-readable reason and
no way for a future canvas to mark the edge red before the user runs anything.

Before building the registry, the rules engine, the inference pass, and `cm.validate`, we
must fix the foundational choices those stories all depend on and that are expensive to
retrofit: what *kind* of type system this is, when two types are compatible, how strict the
checker is, and how this relates to the tensor-shape work deferred to roadmap Epic 10. These
choices mirror the §A foundational ADRs (Epic 1 Story 1) and the codegen ADRs 0008–0010
(Epic 2 Story 1) — decided and written down before implementation. This ADR records four such
decisions together; its sibling, ADR 0012, records the fifth (portability of the rules as
data).

## Decision

### 1. Nominal typing with an explicit, optional subtype relation

Compatibility is **nominal**, not structural. A type is an identifier — a token — and two
types relate only through declared facts: token equality, or a subtype edge explicitly
registered between them. We will **not** infer compatibility by inspecting the internal
structure of the values a token stands for.

The type system is therefore a small directed graph: a **catalog** of known type tokens plus
an **optional subtype relation** (a set of `(subtype, supertype)` edges) over them. The
subtype relation is optional in the sense that the system is fully usable with zero subtype
edges — exact-match-plus-wildcard is a complete, useful checker on its own; subtyping is an
additive refinement, not a prerequisite.

`"any"` is the explicit **top type** (the wildcard). It is a real, registered member of the
catalog with documented semantics, not a magic absent value: every type is implicitly a
subtype of `"any"`, and `"any"` connects to and from anything.

This is chosen over structural typing because it is simple, it matches the existing
free-string tokens (no value introspection, no schema for "the shape of a `DataFrame`"), and
— decisively — it serializes cleanly to plain data that the frontend can evaluate with no
Python present (the constraint ADR 0012 makes concrete). A structural system would require
shipping and evaluating type *structure* client-side and would couple the rules to Python
runtime types, defeating both portability and the future sandboxing of Epic 6.

The wire format is unchanged: `data_type` stays a `str` on `Port` (no IR schema break). The
registry validates tokens against the catalog *during the validation pass*, not at
construction — exploratory, half-typed graphs must still be constructible (see decision 3).

### 2. Three-valued, reason-bearing compatibility semantics

An OUT-port type `S` may connect to an IN-port type `T` according to a pure function whose
result is one of three values:

- **COMPATIBLE** iff any of:
  - `T == "any"` or `S == "any"` — wildcard on either side;
  - `S == T` — exact match;
  - `S` is a registered subtype of `T` (transitively, following subtype edges).
- **UNKNOWN** iff `S` or `T` is a token **not present in the registry**. The system cannot
  reason about a token it has never been told about, so it declines to judge rather than
  guessing — this is a *warning*, not a rejection (see decision 3).
- **INCOMPATIBLE** otherwise — both tokens are known, and none of the COMPATIBLE conditions
  holds.

Every result carries a **human-readable reason** that names the expected-vs-actual tokens
(e.g. "port expects `DataFrame`, upstream produces `HTML`"). This is not cosmetic: it is
required for the golden-diagnostics corpus to assert on stable messages, and it is the
substance behind the canvas's future "explain why this edge is red" affordance.

The function is **pure and deterministic** — no I/O, no global state, output a function of
inputs alone — so the same logic can be shipped to and evaluated by the frontend (ADR 0012),
golden-tested, and later run inside Epic 6's sandbox without modification.

### 3. Strictness: hard-block structural mismatches and cardinality; warn on runtime-only-knowables

Validation is **two-tiered** by what is knowable statically:

- **Hard-block (error severity)** — things provably wrong from the IR alone: an INCOMPATIBLE
  edge (two known, non-relatable types), and a **cardinality violation** (a second inbound
  edge into a `Cardinality.ONE` IN port). These produce error-severity diagnostics and, when
  they reach the codegen/execute gate (Epic 3 Story 6), raise a clear, node/edge-naming error
  *before* any code is emitted or any node runs — exactly as the declarative seam already
  raises `CodegenError` early in `colonymind/codegen/declarative.py`.
- **Warn-don't-block (warning severity)** — things only knowable at runtime, or not knowable
  at all from a static catalog: UNKNOWN results (unregistered tokens), dynamically-shaped
  frames, and similar. These surface as warnings on the diagnostics object but never block
  construction, compilation, or execution.

Crucially, **type/cardinality validation never blocks graph construction.** This is a
deliberate split from `Graph._validate_structure`, which hard-rejects malformed *structure*
(missing nodes/ports, wrong edge direction) at build time. Type and cardinality checking lives
in a *separate* `cm.validate(graph)` call (Epic 3 Story 5) so the canvas can hold half-wired,
exploratory graphs and still inspect them. The two layers stay distinct: structure is a build
invariant; types and cardinality are an inspectable, non-blocking analysis.

This split is a UX judgement call — too strict frustrates exploration, too loose lets crashes
through — and should be revisited with the first design partner. The default recorded here
errs toward letting exploratory work proceed while still catching the provably-broken.

### 4. Relationship to Epic 10 (tensor dimensions)

This epic builds the **general, structural** type framework only. `Tensor` is one nominal
token among others; a `Tensor`→`Tensor` edge is COMPATIBLE here, full stop. Whether the
*dimensions* line up is **not** decided by this framework.

Per-dimension shape inference is **roadmap Epic 10**, which *specializes* this framework for
`Tensor`-typed ports specifically — layering dimension resolution on top of the structural
check, so deep-learning graphs get structural validation "for free" and Epic 10 adds only the
dimension reasoning. We will **not** build dimension inference here. Doing so would depend on
PyTorch meta-tensor / FakeTensor tracing and reintroduce a `torch` dependency this repo
deliberately avoids (tests use `pytest.importorskip("torch")`); conflating structural and
dimensional typing would entangle the portable, pure rules with a heavy runtime dependency.

## Consequences

**Positive:**

- The whole later epic has a fixed spine: Story 2 (registry) implements the catalog +
  subtype relation; Story 3 (rules engine) implements the three-valued function; Story 5
  (`cm.validate`) applies it and populates the long-dormant `Edge.type_compatible`.
- Nominal-plus-optional-subtype is the simplest model that is both expressive enough
  (wildcard, exact, subtype) and serializable as plain data, satisfying the frontend-portability
  constraint without a Python round-trip.
- Purity is preserved end-to-end: the same rules run in the SDK, ship to the canvas (ADR
  0012), feed golden tests, and later run inside Epic 6's sandbox unchanged.
- Three-valued results (vs. a bare bool) let the checker distinguish "provably wrong" from
  "can't tell yet," which is exactly the distinction the strictness policy needs.
- Deep learning gets structural validation immediately; Epic 10 has a clean, narrow surface
  (dimensions on `Tensor` ports) to extend rather than a from-scratch type system.

**Negative / obligations:**

- Nominal typing means new compatibility facts must be *declared* — a node author who invents
  a new token gets no compatibility with anything except `"any"` until subtype edges are
  registered. The registry must therefore be declaratively extensible (Story 2), and
  `docs/authoring-a-node.md` must teach token choice and `infer_types` (Story 8).
- The strictness split is a policy, not a theorem; it is expected to be re-tuned with a
  design partner, and the warn-vs-block boundary may move.
- Both pure functions must reject the same graphs for the same reasons (ADR 0002 equivalence
  extends to rejection), which obliges the single shared gate and negative-equivalence tests
  of Story 6.

**Deferred:**

- The type registry, the `"any"` semantics in code, and token inventory/registration — Epic 3
  Story 2.
- The pure `is_compatible(...)` rules engine and the cardinality rule — Epic 3 Story 3.
- The whole-graph type-inference pass that resolves types before checking — Epic 3 Story 4.
- `cm.validate(graph)`, the `Diagnostics` shape, and populating `Edge.type_compatible` — Epic
  3 Story 5.
- The shared codegen/execute validation gate and negative-equivalence corpus — Epic 3 Story 6.
- **Portability** — exporting the catalog + subtype table + semantics as shippable data — is
  the sibling decision in [ADR 0012](./0012-rules-as-portable-data.md).
- **Tensor dimension inference** — roadmap Epic 10, layered on this framework.
