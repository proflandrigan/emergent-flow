# Epic 3 — Type-Safe Graph & Connection Validation

> **Repo ↔ roadmap numbering.** This file is repo **Epic 3** (third epic delivered here) =
> roadmap **Epic 5**. The roadmap's literal **Epic 3** is the *Frontend Canvas Engine*
> (React/TS) and is **not** delivered in this repo — it ships in the separate
> `colony-mind-canvas` repo and consumes this epic's rules-as-data. Cross-references in the
> prose below use **roadmap** numbers. See [`epics/README.md`](./README.md) for the full
> mapping; the per-epic "Numbering note" just below expands the rationale.

> Prevent invalid graphs before execution. Edges carry types (`DataFrame`,
> `ClassifierResult`, `Tensor`, `HTML`, …); incompatible connections are caught with a
> clear, machine-readable reason. Epic 1 gave every port a `data_type` token and every edge
> a `type_compatible: bool | None` field, but **nothing fills them in** — the token is an
> opaque string, `type_compatible` is permanently `None`, `infer_types` only echoes declared
> OUT types, and `Graph` validates *structure* (node/port existence, OUT→IN direction) but
> never *type compatibility* or *cardinality*. This epic builds the general type system and
> the connection-validation pass over the existing IR, and makes invalid wiring a first-class,
> explainable diagnostic rather than a runtime crash.
>
> **Numbering note.** This is the **third epic delivered in this repo**, but it is the
> roadmap's **Epic 5** (*Type-Safe Graph & Connection Validation*). The roadmap's literal
> Epic 3 — the *Frontend Canvas Engine* (React Flow / TypeScript) — is **out of scope here**:
> it is a separate frontend repo that consumes this repo's published IR schema and codegen
> output, never `import colonymind`. This Python SDK repo owns the type *system* and the
> *rules*; the canvas consumes them. See "Notes / Risks" for the repo-split rationale.

**Phase:** 1 (Foundation) — structural typing only.
**Dependencies:** Epic 1 (IR: `Port.data_type`, `Edge.type_compatible`, `PortSpec`, `NodeDefinition.infer_types`), Epic 2 (codegen/execute gate the validation hooks into).
**Blocks:** the Frontend Canvas (roadmap Epic 3, separate repo — consumes the rules-as-data and diagnostics surface), Epic 10 (tensor *dimension* inference specializes the general framework built here), Epic 12 (the NL→graph agent emits IR validated by this layer).

---

## Definition of Done (epic-level)

- [ ] A formal **type-token system** replaces the opaque `data_type` string: known types are registered, `"any"` is the explicit wildcard/top type, and the catalog is serializable (the frontend needs it with no Python present).
- [ ] A pure, deterministic **compatibility function** decides whether an OUT-port type may feed an IN-port type, returning one of *compatible / incompatible / unknown* (with a reason), and is expressible as **data shippable to the client** so the canvas gives instant feedback without a round-trip.
- [ ] A **whole-graph type-inference pass** propagates resolved types from sources downstream (generalizing per-node `infer_types`), so compatibility checks run against *resolved* types, not just declared ones.
- [ ] A **graph validation pass** (`cm.validate(graph)`) checks every edge for type compatibility **and cardinality**, populates `Edge.type_compatible`, and returns structured **diagnostics** (severity + edge/port + human-readable reason, expected-vs-actual type) — without blocking construction of exploratory graphs.
- [ ] **Strictness policy is implemented and documented:** structural type mismatches and cardinality violations hard-fail; things only knowable at runtime warn-don't-block.
- [ ] `compile_to_code` and `execute` **share a single validation gate** (mirroring `_prepare_declarative`) so both paradigms accept/reject identically; a hard structural mismatch raises a clear error before any code is emitted or run.
- [ ] A **golden diagnostics corpus** covers compatible, incompatible, unknown, dangling-required-IN, and cardinality-violation graphs; it is wired into CI alongside the existing equivalence gate.
- [ ] Tensor **dimension** inference is explicitly **not** built — only structural type compatibility (`Tensor`→`Tensor` is fine here); per-dimension shape resolution is deferred to roadmap Epic 10, which specializes this framework.
- [ ] The many `# … is Epic 5` placeholders across `colonymind/` and `docs/` are resolved (this epic *is* that work) and the docs describe the real type system.

---

## Story 1 — Lock the type-system architectural decisions

> These choices shape every later story and are expensive to retrofit. Decide and write
> them down before building, mirroring Epic 1 Story 1 (§A) and Epic 2 Story 1.

- [x] **Type model: nominal vs. structural.** Decide whether compatibility is nominal (token equality + a declared subtype graph) or structural. Recommend **nominal with an explicit, optional subtype relation** and `"any"` as the top type — it is simple, serializable, and matches the existing free-string tokens. Record an ADR. → ADR 0011
- [x] **Compatibility semantics.** Define exactly when OUT type `S` may connect to IN type `T`: `T == "any"` or `S == "any"` (wildcard), `S == T` (exact), or `S` is a registered subtype of `T`. Define the third outcome — *unknown* — for tokens not in the registry (warn, don't block). Record in the same ADR.
- [x] **Strictness policy.** Hard-block structural mismatches and cardinality violations; **warn-don't-block** for anything only knowable at runtime (e.g. unregistered tokens, dynamic frames). Mirror how the declarative seam already raises `CodegenError` early. → folded into ADR 0011
- [x] **Where validation runs / portability.** The rules must be expressible as **plain data** (a serialized type catalog + subtype table) shippable to the frontend for instant feedback, with this SDK as the authoritative re-validator. Decide the export shape. Record an ADR. → ADR 0012
- [x] **Relationship to Epic 10.** State that this epic builds the *general* structural framework and that tensor **dimension** inference (roadmap Epic 10) layers on top, only for `Tensor`-typed ports — so DL gets structural validation "for free" and only adds dimension inference later. → folded into ADR 0011

---

## Story 2 — Formalize the type-token system & registry

> Today `data_type` is a bare `str` defaulting to `"any"`, with tokens like `DataFrame`,
> `ClassifierResult`, `AnovaResult`, `HTML`, `Tensor` used ad hoc across the reference nodes.
> Give them a registry so compatibility can be reasoned about and shipped as data.

- [x] Implement a **type registry** (e.g. `colonymind/types/` or `colonymind/ir/types.py`) cataloguing known data types and an optional **subtype relation** between them.
- [x] Make `"any"` the explicit **top/wildcard** type with documented semantics (connects to/from anything, warns nowhere).
- [x] **Inventory and register** every token currently in use (`DataFrame`, `ClassifierResult`, `AnovaResult`, `HTML`, `Tensor`, `any`) from `colonymind/nodes/examples/*.py`; keep `data_type` a `str` on the wire (no IR schema break) but validate it against the registry during the validation pass, not at construction.
- [x] Make the registry **declaratively extensible** (an out-of-core node can register a new type token), consistent with the node registry/plugin pattern (ADR 0006) — and add a stub demonstrating it, like `examples/plugin_stub`.
- [x] Ensure the registry + subtype table **serialize to JSON** (the frontend consumes them with no Python present, same constraint that drove the IR).
- [x] Unit-test: registration, duplicate/conflict detection, subtype transitivity, `"any"` semantics.

---

## Story 3 — Connection-compatibility rules engine

> The pure core both the validation pass and the (separate) frontend rely on.

- [ ] Implement a **pure** `is_compatible(source_type, target_type) -> Compatibility` returning `COMPATIBLE | INCOMPATIBLE | UNKNOWN` plus a human-readable reason (no I/O, no global state — so Epic 6 sandboxing and client-side shipping both stay trivial).
- [ ] Implement the **cardinality rule**: a `Cardinality.ONE` IN port rejects a second inbound edge; `MANY` permits fan-in. (This is a real gap today — `Graph._validate_structure` checks direction and existence but never cardinality, and no reference node uses `MANY` yet.)
- [ ] Keep results **deterministic and reason-bearing** (expected-vs-actual token in the message), required for golden tests and for the canvas's "explain why this edge is red" affordance.
- [ ] Guarantee the rules are **expressible as data** (Story 1 ADR 0012): a serialized compatibility table the frontend can evaluate without calling Python.
- [ ] Unit-test the matrix: exact match, subtype, `"any"` either side, unregistered token (→ UNKNOWN/warn), and ONE-vs-MANY cardinality.

---

## Story 4 — Whole-graph type inference

> `NodeDefinition.infer_types` exists but its default just echoes each OUT port's *declared*
> `data_type`, and nothing calls it across a graph. Resolve types end-to-end so compatibility
> checks see real, propagated types.

- [ ] Implement a **graph inference pass** that walks the IR in topological order (reuse Epic 2's `traversal.py`), threading each node's resolved OUT types into downstream IN ports and calling each node's `infer_types(node, input_types)`.
- [ ] Define behaviour when an upstream type is **unknown/unbound** (dangling IN port) — surface as a diagnostic, don't crash; reuse Epic 2's documented dangling-IN-port behaviour.
- [ ] Return a **resolved-type map** keyed by `(node_id, port_id)` that the validation pass (Story 5) consumes.
- [ ] Keep the pass **pure** and deterministic so it can run client-side-equivalently and feed golden tests.
- [ ] Unit-test inference over linear chains, fan-out/fan-in (diamond), and a node whose OUT type depends on inputs (add or use a fixture node that overrides `infer_types`).

---

## Story 5 — Graph validation pass & diagnostics (`cm.validate`)

> The headline deliverable: one call that tells you everything wrong with a graph's wiring,
> structured for both humans and the canvas.

- [ ] Implement `cm.validate(graph) -> Diagnostics` (a `@public_op`, serializable + inspectable) that runs inference (Story 4) then checks every edge with the rules engine (Story 3).
- [ ] Emit structured **diagnostics**: each carries `severity` (error/warning), the offending edge/port ids, a human-readable message, and expected-vs-actual type. Make `Diagnostics` JSON-native so the frontend renders it directly.
- [ ] **Do not block construction.** Unlike `Graph._validate_structure` (which hard-rejects malformed structure at build time), type/cardinality validation is a *separate* call so exploratory, half-wired graphs can exist on the canvas and still be inspected. Document this split explicitly.
- [ ] **Populate `Edge.type_compatible`** (currently always `None`) as a side-output of validation, fulfilling the field Epic 1 reserved.
- [ ] Cover structural connection checks here too: **required IN port with no edge** → error; **cardinality violation** → error; **unregistered token** → warning.
- [ ] Unit-test diagnostics shape and severities across crafted invalid graphs.

---

## Story 6 — Gate codegen & execution on validation

> Equivalence (ADR 0002) means both pure functions must reject the same graphs for the same
> reasons. Wire validation in as a shared gate, exactly as `_prepare_declarative` is the single
> validation seam shared by both the compiler and executor today.

- [ ] Add a **single shared validation gate** that `compile_to_code` and `execute` both call before doing any work, so the two paradigms and the two pure functions accept/reject identically.
- [ ] On a hard structural mismatch (error-severity diagnostic), raise a **clear, node/edge-naming error** before any code is emitted or any node runs — consistent with the existing `CodegenError` pattern for the declarative seam.
- [ ] Let warnings **pass through** (warn-don't-block) so exploratory runs still execute; surface them on the result/diagnostics object.
- [ ] Extend the **equivalence corpus** so a known-invalid graph is rejected by *both* `compile_to_code` and `execute` with equivalent errors (negative equivalence).
- [ ] Confirm purity is preserved — the gate adds no I/O or global state (Epic 6 still wraps the executor cleanly).

---

## Story 7 — Rules & catalog as a portable artifact (frontend handoff)

> The roadmap's Epic-5 requirement that validation rules be "expressible in / shippable to the
> client." This repo owns the rules; the separate canvas repo consumes them.

- [ ] Export the **type catalog + subtype table + compatibility semantics** as a versioned, serialized artifact (JSON) the frontend can evaluate for instant edge feedback without a Python round-trip.
- [ ] Export the **`Diagnostics` schema** (JSON Schema / Pydantic) so the canvas can render highlights and "why" tooltips against a stable contract.
- [ ] Document the **authority model**: the frontend gives instant, best-effort feedback from the shipped rules; this SDK is the authoritative re-validator (server-side, Epic 6).
- [ ] Version the exported rules artifact alongside the IR schema version so the frontend can detect drift (ties into Epic 14 migrations).

---

## Story 8 — Tests, fixtures, docs & resolving the "Epic 5" placeholders

> "Codegen quality is the marketing claim" — and a graph that says *why* a connection is
> invalid is the same trust surface. Make the diagnostics first-class, not an afterthought.

- [ ] Assemble a **fixture corpus**: compatible chain, incompatible edge (e.g. `HTML`→a `DataFrame` IN), `"any"` wildcard, subtype acceptance, unregistered token (warn), dangling required IN, and ONE-vs-MANY cardinality violation.
- [ ] Add **golden (snapshot) tests** of the `Diagnostics` output so regressions in messages/severities are caught, mirroring Epic 2's golden corpus.
- [ ] Wire the validation/diagnostics gate into **CI** alongside the existing equivalence and golden gates.
- [ ] Write a **type-system spec doc** (`docs/type-system-spec.md`) and a "connection validation" guide; link from the README, mirroring Epic 1/2 docs discipline.
- [ ] **Resolve the `Epic 5` placeholders** in `colonymind/ir/port.py`, `params.py`, `edge.py`, `nodes/contract.py`, `nodes/spec.py`, `docs/ir-spec.md`, `docs/node-contract-spec.md`, `docs/authoring-a-node.md`, `docs/node-registry.md`, and ADRs 0005/0006 — pointing them at the now-real type system (and at Epic 10 for tensor dimensions specifically).
- [ ] Update `docs/authoring-a-node.md` so a node author learns how to choose/register a `data_type` token and override `infer_types`.

---

## Notes / Risks (carry into planning)

- **The roadmap's literal Epic 3 (Frontend Canvas) does not belong in this repo.** It is a React Flow / TypeScript app with its own toolchain (`npm`/Vite/Vitest) and lives in a separate repo (e.g. `colony-mind-canvas`); a third repo (`colony-mind-server`) will host the FastAPI/execution backend (Epic 6). The boundary between them is the **IR schema + generated-code string + the rules-as-data artifact (Story 7)**, never a shared Python import — exactly the one-way, IR-is-source-of-truth contract of ADR 0001 and the open-core split of ADR 0007. This epic is what gives that future canvas its instant, explainable connection validation.
- **Don't build tensor dimension inference.** That is roadmap Epic 10 and depends on PyTorch meta-tensor / FakeTensor tracing. This epic stops at *structural* typing: `Tensor`→`Tensor` is compatible here; whether the *dims* line up is Epic 10's job, layered on this framework. Conflating the two re-introduces a torch dependency the repo deliberately avoids (`pytest.importorskip("torch")`).
- **Validation must not block construction.** `Graph._validate_structure` hard-rejects malformed structure at build time; type/cardinality validation is deliberately a *separate* `cm.validate` call so the canvas can hold half-wired, exploratory graphs and still inspect them. Keep the two layers distinct.
- **Equivalence (ADR 0002) extends to rejection.** Both `compile_to_code` and `execute` must reject the same invalid graphs for the same reasons — add *negative* equivalence tests, and route both through one shared gate (the `_prepare_declarative` pattern), or the two pure functions will drift on error handling.
- **Strictness is a UX judgement call.** Too strict frustrates exploratory work; too loose lets crashes through. The recommended split — hard-block structural/cardinality, warn on runtime-only-knowables — should be revisited with the first design partner.
- **Keep the rules pure and serializable.** The same purity that lets Epic 6 sandbox the executor lets the frontend ship the rules client-side. Any I/O or global state in the compatibility engine breaks both.

---

*How to use this file: tick each `- [ ]` to `- [x]` as work completes. A story is done when all
its tasks are checked; the epic is done when the Definition of Done checklist is complete.*
