# ADR 0012 — Ship the type rules as versioned data, with the SDK as authoritative re-validator

- **Status:** Accepted
- **Date:** 2026-06-20
- **Deciders:** Emergent Flow core team

## Context

The roadmap's Epic 5 requirement is not only that invalid graphs be caught, but that the
validation rules be *expressible in and shippable to the client*. The visual canvas — roadmap
Epic 3, a React Flow / TypeScript app in a **separate repo** (`emergent-flow-canvas`), never
`import emergentflow` — must give instant red-edge feedback as the user drags a connection,
with **no Python present and no server round-trip**. This is the same constraint that drove
serializing the IR itself: the boundary between this SDK and the frontend is the IR schema,
the generated-code string, and (now) the rules-as-data artifact — never a shared Python import
(ADR 0001's one-way source-of-truth contract, ADR 0007's open-core split).

ADR 0011 fixes *what* the rules are: a nominal type model — a catalog of tokens, an optional
subtype relation, `"any"` as top — checked by a pure, three-valued compatibility function.
What remains is *how those rules cross the repo boundary* so the frontend can evaluate them
itself. Two broad shapes are available: ship the rules as **data the client evaluates**, or
ship a **precomputed result for every type pair** the client merely looks up. This must be
decided now because it dictates what Story 7 emits and what contract the canvas codes against.

## Decision

We will export the type rules as **data, not a precomputed matrix**: a single **versioned
JSON artifact** containing the type catalog, the subtype relation, and the compatibility
semantics. The frontend loads this artifact and implements the small exact/subtype/wildcard
check (the algorithm fixed in ADR 0011) against it. The shape is:

```json
{
  "version": 1,
  "types": ["any", "DataFrame", "ClassifierResult", "AnovaResult", "Tensor", "HTML"],
  "top": "any",
  "subtypes": [["ClassifierResult", "any"]],
  "semantics": { "wildcard": "any", "exact": true, "subtype": true, "unknown": "warn" }
}
```

(`subtypes` is the declared edge list — `[subtype, supertype]` pairs; the example is
illustrative, not the final catalog, which Story 2 inventories.)

**Rules-as-data is chosen over a precomputed compatibility matrix** because:

- It is **compact and human-readable** — O(types + subtype-edges), not O(types²). A
  precomputed matrix enumerates every ordered pair and grows quadratically as the catalog
  expands and as out-of-core plugins register new tokens.
- It has **no regeneration coupling** — adding a type or a subtype edge changes a short list,
  not an N² table that must be fully recomputed and re-shipped on every catalog change.
- It mirrors **how the IR is already shipped**: declarative data the consumer interprets, not
  baked-in answers. The check the frontend must implement is tiny (the three COMPATIBLE
  conditions of ADR 0011) and is the same logic the SDK runs, keeping a single conceptual
  source of truth.
- A matrix's only advantage — O(1) client lookup with zero client logic — is not worth the
  size and the regeneration coupling for a rule this simple.

**Authority model.** The shipped artifact gives the frontend *instant, best-effort* feedback.
This SDK remains the **authoritative re-validator**: server-side validation (Epic 6) re-runs
`ef.validate` and its verdict is final. The frontend's job is fast UX, not correctness of
record; if the two ever disagree (e.g. a stale artifact), the SDK wins.

**Versioning.** The artifact carries a `version` and is versioned **alongside the IR schema
version** so the frontend can detect drift between the rules it shipped with and the rules the
current SDK enforces. This ties into the migration story (Epic 14): a version bump signals the
canvas to refresh its rules artifact.

This ADR fixes the export *shape and contract*. The emitter that produces the artifact, the
`Diagnostics` JSON-schema export the canvas renders against, and the documented authority/drift
handling are **Story 7** work, built on this decision.

## Consequences

**Positive:**

- The frontend gets instant, offline edge validation from a small, readable file — no Python,
  no network — fulfilling the roadmap's "rules shippable to the client" requirement.
- Purity pays off twice: the same pure rules (ADR 0011) that let Epic 6 sandbox the executor
  are exactly what makes them safe to ship and evaluate client-side. No I/O or global state may
  enter the compatibility engine without breaking both.
- The artifact stays small and cheap to regenerate as the type catalog grows and as plugins
  register tokens (ADR 0006 extensibility), because it scales with the number of types, not
  their square.
- A versioned artifact aligned with the IR schema gives the canvas a concrete drift signal,
  feeding the Epic 14 migration story.

**Negative / obligations:**

- The compatibility algorithm now lives in **two places** — the Python rules engine (Story 3)
  and the frontend's evaluator. They must stay in lockstep; the SDK-as-authority model bounds
  the damage (the SDK's verdict is final), but the algorithm is deliberately kept tiny (ADR
  0011) precisely to make the reimplementation trivial and auditable.
- The artifact must be regenerated and re-versioned whenever the catalog or subtype relation
  changes; Story 7 must wire this into the build so a stale artifact cannot ship silently.

**Deferred:**

- The artifact emitter/serializer, the `Diagnostics` schema export, and the documented
  authority + drift-detection model — Epic 3 Story 7.
- The type catalog's actual contents and the registry that produces them — Epic 3 Story 2.
- The pure compatibility function whose semantics this artifact encodes — Epic 3 Story 3
  (decided in [ADR 0011](./0011-type-model-and-compatibility.md)).
