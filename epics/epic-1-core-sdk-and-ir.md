# Epic 1 — Core SDK & Graph Intermediate Representation (IR)

> The spine of OmniCanvas AI / Colony Mind. A versioned, open-source Python SDK plus a
> canonical graph schema (the IR) that every other layer reads and writes. Nothing else
> can be built reliably until this is right — and the IR schema is the single hardest
> thing to change later.

**Phase:** 1 (Foundation)
**Dependencies:** None — this is the root.
**Blocks:** Epics 2 (codegen), 3 (canvas), 5 (typing), and everything downstream.

---

## Definition of Done (epic-level)

- [ ] A serializable IR schema (nodes, ports, edges, params, sub-graphs) is published and versioned.
- [ ] A node-definition contract exists that every node family conforms to.
- [ ] A node registry lets new nodes be added declaratively, without core changes.
- [ ] Graphs round-trip losslessly through serialize → deserialize.
- [ ] The SDK is packaged, version-pinned, and installable, with public API conventions documented.
- [ ] An end-to-end vertical slice of node families (load → clean → one stats test → one model → HTML report) exists as real SDK functions.
- [ ] Schema versioning + migration scaffolding is in place (v1 graphs must open in v2 later).
- [ ] The open-core boundary (what is SDK vs. platform-only) is decided and documented.

---

## Story 1 — Lock the foundational architectural decisions (§A)

> These decisions are upstream of the schema itself. Decide and write them down *before*
> finalizing the IR, because retrofitting any of them is expensive.

- [x] **A1 — Graph is the single source of truth; code is a one-way compiled artifact.** Document that exported `.py` does not sync back to the canvas; defer any Python→graph parser.
- [x] **A2 — Execute the IR, not a generated string.** Commit to two pure functions over one IR: `compile_to_code(ir)` and `execute(ir)`, with equivalence as a hard invariant.
- [x] **A3 — SDK supports two paradigms from day one.** (1) functional pipeline (DE/stats/classical ML/reporting); (2) declarative module/graph (DL via PyTorch, agents via LangGraph). Confirm the IR can represent both.
- [x] **A4 — Storage tiering.** Record that Redis holds metadata/hashes/small results only; large artifacts go to a disk/object store (Arrow/Parquet/safetensors). (Implementation is Epic 7, but the IR must reference artifact *locations*, not bytes.)
- [x] Write a short architecture-decision record (ADR) for each of the four, linked from the repo README.

---

## Story 2 — Design the IR schema

> The canonical, serializable graph representation. Declarative data (JSON/Protobuf-able),
> not a runtime-only Python object graph — the frontend must produce valid IR with no Python present.

- [ ] Define the **node** model (id, type/family, label, params, position, group membership).
- [ ] Define the **port** model (id, direction in/out, declared data type, cardinality).
- [ ] Define the **edge** model (source port → target port, with type-compatibility metadata).
- [ ] Define **params** typing (typed, defaulted, serializable parameter values per node).
- [ ] Define **sub-graphs / groups / nesting** (collapsible composite nodes).
- [ ] Model the **two paradigms** in the schema (functional-pipeline vs. declarative-module graphs) per A3.
- [ ] Embed a **schema version** field on every serialized graph.
- [ ] Choose the serialization format (recommend JSON-first, Protobuf-able later) and document the choice.
- [ ] Make the IR **CRDT-friendly** in shape (stable IDs, mergeable structure) so multiplayer (Epic 13) can be added without a rewrite.
- [ ] Publish the schema as a formal spec (JSON Schema / Pydantic models) with examples.

---

## Story 3 — Define the node-definition contract

> Every node declares what it is, in one consistent way, so the registry, codegen,
> executor, and UI can all consume it uniformly.

- [ ] Specify the contract: each node declares its **ports**, **typed params**, **codegen template**, **executor**, and (where relevant) a **shape/type-inference function**.
- [ ] Define how a node declares **defaults and validation hints** (consumed later by Epic 4 config UI).
- [ ] Define the **per-node version** field (catalog-level versioning, distinct from schema version).
- [ ] Provide a base class / interface + at least two reference implementations conforming to it.
- [ ] Document the contract with a "how to author a node" guide.

---

## Story 4 — Node registry / plugin architecture

> The difference between a fixed tool and a platform: nodes are registered declaratively
> and the catalog can grow (eventually community-extensible) without touching core.

- [ ] Implement a **registry** that discovers and indexes node definitions.
- [ ] Support **declarative registration** (no core code change to add a node).
- [ ] Expose registry lookup APIs (by family, by type, by port-type) for codegen/UI/validation.
- [ ] Add a registry validation pass (fail fast on malformed/duplicate node definitions).
- [ ] Write a plugin/extension stub demonstrating an out-of-core node being registered.

---

## Story 5 — Graph serialization & deserialization

- [ ] Implement **serialize**: IR object → portable format (with embedded schema version).
- [ ] Implement **deserialize**: format → validated IR object.
- [ ] Enforce **lossless round-tripping** (serialize → deserialize → serialize is identical).
- [ ] Validate on load (reject structurally invalid graphs with clear errors).
- [ ] Add round-trip property/golden tests across a corpus of sample graphs.

---

## Story 6 — SDK packaging, versioning & public API conventions

- [ ] Establish the package layout and namespace (e.g. `import omnicanvas as oc`, `oc.data`, `oc.clean`, `oc.stats`, `oc.ml`, `oc.reports`).
- [ ] **Pin all dependency versions** (deterministic, reproducible installs).
- [ ] Adopt a versioning scheme (semantic versioning) and document the release process.
- [ ] Set up build + publish pipeline to a package index.
- [ ] Document **public API conventions** (naming, signatures, return-object expectations).
- [ ] Stand up CI (lint with `ruff`/`black`, type-check, run tests on each commit).

---

## Story 7 — SDK design philosophy (set and enforce now)

> These conventions are cheap to adopt now and very expensive to retrofit. Enforce them
> as acceptance criteria for every wrapper.

- [ ] Codify rules: **thin wrappers**, **deterministic**, **pure functions where possible**.
- [ ] Require every operation to return a **serializable + inspectable** object.
- [ ] Adopt "returns inspectable structured data" as a **selection criterion for every wrapped library** (the reason Pingouin was chosen — it returns clean DataFrames).
- [ ] Add a lint/test check that flags wrappers returning opaque/non-serializable objects.

---

## Story 8 — First concrete node families (functional-pipeline vertical slice)

> Deliberately narrow but end-to-end: the exact flow from the proposal example
> (load → clean → one stats test → one model → HTML report). Breadth comes later (Epic 4).

- [ ] **Data ingestion** wrapper (Pandas/Polars) — e.g. `oc.data.load_csv(...)`.
- [ ] **Cleaning / imputation** wrapper — e.g. `oc.clean.impute_missing(...)`.
- [ ] **Statistical analytics** wrapper (Pingouin/Statsmodels) — e.g. `oc.stats.anova(...)`.
- [ ] **Classical ML** wrapper (Scikit-Learn) — e.g. `oc.ml.train_classifier(...)`.
- [ ] **Automated reporting** wrapper (YData-Profiling / Sweetviz) — e.g. `oc.reports.generate_html_summary(...)`.
- [ ] Register all of the above as node definitions conforming to Story 3.
- [ ] Author one worked example graph that exercises the full slice end to end.

---

## Story 9 — Schema versioning & migration foundation

> Saved graphs from v1 must open in v2. This is unglamorous and essential; without it,
> every node/SDK change risks bricking saved work. (Full maturity lands in Epic 14.)

- [ ] Define a **migration framework** (versioned IR + explicit, ordered migration steps).
- [ ] Implement a "load old version → migrate → current" path with at least one example migration.
- [ ] Add tests that load fixtures from prior schema versions and assert successful migration.
- [ ] Document the policy: no breaking schema change ships without a migration step.

---

## Story 10 — Open-core licensing boundary

- [ ] Decide which nodes/features are **open-source SDK** vs. **platform-only**.
- [ ] Document the boundary and its rationale (affects packaging from the start).
- [ ] Apply the chosen license(s) to the SDK repo and confirm packaging respects the split.

---

## Notes / Risks (carry into planning)

- The **IR schema is the hardest thing to change later** — over-invest in node/port/type modeling and in the versioning/migration story (Story 9).
- The two decisions that most constrain everything downstream and must be locked first: **the IR schema (this epic)** and **the execute-the-IR-not-the-string equivalence model (A2)**.
- Keep the IR **CRDT-friendly** even though multiplayer (Epic 13) is later — designing it in now avoids a rewrite.
- The functional-pipeline slice is the safe, demonstrable core; the declarative paradigm (DL/agents) must be *representable* in the IR now even though its node families arrive in Phase 3.

---

*How to use this file: tick each `- [ ]` to `- [x]` as work completes. A story is done when all
its tasks are checked; the epic is done when the Definition of Done checklist is complete.*
