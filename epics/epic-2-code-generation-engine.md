# Epic 2 — Code Generation Engine

> Deterministic IR → idiomatic, PEP8-clean, runnable Python. The "glass-box"
> promise made real. Epic 1 gave every node a per-node `codegen(node) -> CodeFragment`
> (`colonymind/nodes/contract.py`) and a per-node `execute(node, inputs)`, but there is
> **no whole-graph compiler** and **no whole-graph executor** yet. This epic builds the
> two pure functions ADR 0002 commits to — `compile_to_code(ir)` and `execute(ir)` — over
> the existing IR, and makes their equivalence a hard, CI-enforced invariant.

**Phase:** 1 (Foundation)
**Dependencies:** Epic 1 (IR, node contract, registry, serialization).
**Blocks:** Epic 3 (canvas "show code" panel), Epic 6 (execution runtime wraps the reference executor), Epic 10/11 (declarative codegen specializes the seam built here), Epic 14 (Git export of generated code).

---

## Definition of Done (epic-level)

- [ ] A pure `compile_to_code(graph) -> str` turns any valid functional-pipeline IR into idiomatic, PEP8-clean, runnable Python.
- [ ] Imports are collected, de-duplicated, and ordered once for the whole graph (not per node).
- [ ] Variable names are deterministic, readable (derived from node labels), and collision-free — no `df_step_3_v2_final` and no silent variable clobbering.
- [ ] Statements are emitted in a deterministic topological order; cyclic functional graphs are rejected with a clear error.
- [x] A pure, in-process `execute(graph) -> results` reference interpreter walks the IR and calls each node's `execute` (the productionized, sandboxed runtime is Epic 6).
- [x] The A2 equivalence invariant holds: across a fixture corpus, artifacts from `execute(ir)` equal artifacts from running `compile_to_code(ir)`, enforced as a CI golden/property gate.
- [x] Generated code passes `ruff` lint and is importable/runnable; a golden-file corpus covers every reference node type and common compositions (fan-in, fan-out, subgraphs).
- [x] The two-paradigm seam exists: the compiler dispatches on `paradigm`, with a working proof for the declarative `nn.Module` example; full DL/agent codegen is deferred to Epic 10/11.
- [ ] The vertical-slice graph (`examples/vertical_slice/pipeline.json`) compiles to code that reads like the hand-written `examples/vertical_slice/demo.py` and runs to the same artifacts.
- [ ] Bidirectional (code → graph) parsing is explicitly **not** built (deferred per A1/ADR 0001).

---

## Story 1 — Lock the codegen architectural decisions

> These choices shape every later story and are expensive to retrofit. Decide and write
> them down before building the compiler, mirroring how Epic 1 Story 1 fixed §A.

- [x] **Templating vs. AST construction.** Decide the hybrid: string/template emission for flat functional pipelines (already how `CodeFragment.body` works in `contract.py`), AST/`libcst` for the declarative paradigm where nested structure matters (per roadmap Epic 2 key decisions). Record an ADR. → [ADR 0008](../docs/adr/0008-codegen-templating-vs-ast.md)
- [x] **Variable-binding model.** Decide how the whole-graph compiler supplies each node with the *input* variable names (per IN port, from upstream bindings) and *output* variable names (per OUT port). This is the central contract change — today nodes hardcode `frame`/`result`/`html` in their `body` (see `colonymind/nodes/examples/*.py`), which cannot wire a real graph. Record an ADR (a `CodegenContext` passed into `codegen`). → [ADR 0009](../docs/adr/0009-codegen-binding-context.md)
- [x] **Package placement.** Decide the home for the engine (e.g. `colonymind/codegen/`) and the public entry points `cm.compile_to_code` / `cm.execute`, consistent with `docs/public-api-conventions.md`. → [ADR 0010](../docs/adr/0010-codegen-package-placement.md)
- [x] **Formatting toolchain.** Choose the post-generation formatter; the repo already standardizes on `ruff` (`[tool.ruff]` in `pyproject.toml`), so prefer `ruff format` over adding `black`. → folded into [ADR 0008](../docs/adr/0008-codegen-templating-vs-ast.md)
- [x] **Restate the equivalence invariant** (ADR 0002): `execute(ir)` and running `compile_to_code(ir)` must produce equivalent artifacts; link the new ADRs back to `docs/adr/0002-execute-the-ir-not-the-string.md`. → folded into [ADR 0010](../docs/adr/0010-codegen-package-placement.md)

---

## Story 2 — Graph traversal & compilation foundation

> Shared plumbing both `compile_to_code` and `execute` need. Today `Graph`
> (`colonymind/ir/graph.py`) stores nodes/edges as id→object maps with structural
> validation but offers no traversal helpers.

- [x] Implement a **deterministic topological sort** over `Graph.nodes`/`Graph.edges`, with a stable tie-break (e.g. by node id) so the same graph always orders identically.
- [x] Implement **cycle detection**: functional-pipeline graphs must be acyclic; reject cycles with a clear, node-naming error message.
- [x] Build the **input-wiring map**: for each node's IN port, resolve the upstream `(node_id, OUT port_id)` from `Graph.edges` (`Edge.source` → `Edge.target`).
- [x] Handle **fan-out** (one OUT port feeding many targets) and **fan-in / cardinality** (an IN port's `cardinality`, see `colonymind/ir/port.py`).
- [x] Define behaviour for **dangling IN ports** (no upstream edge) — error vs. leave unbound — and document it.
- [x] Add unit tests over crafted graphs (linear chain, diamond/fan-out, disconnected, cyclic).

---

## Story 3 — Deterministic, readable variable naming

> Directly defuses the proposal's Challenge 2 ("df_step_3_v2_final"). Names must be
> derived from intent, not execution order, and never collide.

- [x] Derive a candidate identifier from each node's `label` (e.g. "Load CSV" → `load_csv`), slugified to a valid Python identifier.
- [x] **Collision handling** that is deterministic and readable (stable suffixing), not order-encoded. Note the live bug this fixes: `stats.anova` and `ml.train_classifier` both hardcode `result =` today and would clobber each other.
- [x] Avoid Python **keywords/builtins** and ensure uniqueness across the whole graph.
- [x] Map every **OUT port** to a bound variable name (supporting multi-output nodes), feeding the binding context from Story 1.
- [x] Guarantee **stability**: the same IR always yields the same names (required for golden tests and CRDT-friendly diffs).
- [x] Unit-test naming over labels with spaces, duplicates, unicode, keyword collisions, and empty/None labels.

---
 ## Story 4 Evolve the node codegen contract for whole-graph compilation

> The existing `NodeDefinition.codegen(node) -> CodeFragment` cannot participate in a real
> compiler because it hardcodes variable names. This story closes that gap while preserving
> single-node preview (`CodeFragment.render()`).

- [x] Extend the contract so `codegen` receives a **binding context** (input var name per IN port, output var name per OUT port) — e.g. `codegen(node, ctx) -> CodeFragment` — per the Story 1 ADR.
- [x] Keep `CodeFragment` (`imports` + `body`) as the unit; confirm `render()` still works for single-node previews and the canvas "show code" panel (Epic 3).
- [x] Migrate all five reference nodes to consume the context instead of literals: `data.load_csv`, `clean.impute_missing`, `stats.anova`, `ml.train_classifier`, `reports.generate_html_summary` (`colonymind/nodes/examples/*.py`).
- [x] Bump each migrated node's `version` (per-node catalog version) since codegen semantics change (see the `version` ClassVar in `contract.py`).
- [x] Update `tests/test_reference_nodes.py` and the node-contract tests to assert codegen wiring against the context.
- [x] Update `docs/node-contract-spec.md` and `docs/authoring-a-node.md` so "how to author a node" reflects the new `codegen` signature.

---

## Story 5 — Functional-pipeline whole-graph compiler (`compile_to_code`)

> The headline deliverable: IR → one runnable Python module.

- [x] Implement `compile_to_code(graph) -> str` composing Stories 2–4: topo order, naming, per-node fragments.
- [x] **Collect, de-duplicate, and sort imports** across all fragments (the job `CodeFragment.render()` explicitly defers to "the real whole-graph compiler" in `contract.py`).
- [x] Emit body statements in topological order with correct upstream→downstream variable wiring.
- [x] Assemble a complete module: header/docstring, import block, then body; decide flat-script vs. `def main()` wrapping and document it.
- [x] Run the **formatting pass** (`ruff format`) so output is PEP8-clean.
- [x] Expose the public entry point (`cm.compile_to_code`) and register it under the public-API conventions; ensure it returns an inspectable `str`.
- [x] Handle edge cases: empty graph, single source node, fan-out, fan-in.

---

## Story 6 — Reference IR executor & the equivalence invariant (A2)

> ADR 0002 mandates two pure functions over one IR with equivalence as a hard invariant.
> Per-node `execute` exists; the whole-graph interpreter does not. The *production* sandboxed
> runtime is Epic 6 — this story builds only the pure, in-process reference executor needed to
> prove equivalence.

- [x] Implement `execute(graph) -> results`: topo-walk the IR, call each node's `execute(node, inputs)`, and thread OUT-port outputs to downstream IN ports via the Story 2 wiring map.
- [x] Return inspectable results keyed by node/port, consistent with `colonymind/api.py` (`is_inspectable`).
- [x] Build the **equivalence harness**: for a corpus of graphs, assert artifacts from `execute(ir)` equal artifacts from running `compile_to_code(ir)`.
- [x] Cover the vertical slice end to end (`examples/vertical_slice/pipeline.json`) plus `examples/functional_pipeline.json`.
- [x] Document the boundary: this executor is the equivalence reference; Epic 6 wraps it with sandboxing, resource limits, and streaming.

---

## Story 7 — Export a runnable script / module

> The "glass-box" payoff: a user can download the exact code that runs.

- [x] Export `compile_to_code(graph)` output as a standalone `.py` that runs outside the canvas.
- [x] Emit a reproducibility reference (pinned SDK version / `requirements`) alongside the script; keep it light here and hand the full project-export format to Epic 14.
- [x] Verify the vertical-slice graph exports to code that reads like the hand-written `examples/vertical_slice/demo.py`.
- [x] Round-trip test: run the exported script and assert it produces the same artifacts as `execute(ir)`.

---

## Story 8 — Declarative-paradigm codegen seam (forward-looking)

> The IR already models the declarative paradigm (ADR 0003; `Node.subgraph`,
> `examples/declarative_module.json`). Establish the architecture now so DL/agents bolt on
> cleanly later, without building the full catalog.

- [x] Add **paradigm dispatch** in the compiler: branch on `Graph.paradigm` / `Node.paradigm` (`FUNCTIONAL` vs `DECLARATIVE`).
- [x] Implement an **AST/`libcst`-based** generator that compiles a `Node.subgraph` into an `nn.Module` class, proven against `examples/declarative_module.json` (the `nn.module` → `nn.linear`/`nn.relu` example).
- [x] Leave a documented seam for the **LangGraph** (agent) target; defer its implementation to Epic 11.
- [x] State explicitly that the full PyTorch layer catalog and tensor-shape codegen land in Epic 10; this story only proves the seam holds.

---

## Story 9 — Codegen quality, fixtures & the CI gate

> "Codegen quality *is* the marketing claim" (roadmap). A messy edge case is a credibility hit,
> so the fixture suite and gate are first-class, not an afterthought.

- [x] Assemble a **fixture corpus** covering every reference node type and common compositions: linear chain, fan-out, fan-in/diamond, and a subgraph/grouped graph.
- [x] Add **golden-file (snapshot) tests** of generated code so regressions in formatting/naming/imports are caught.
- [x] Assert generated code **passes `ruff` lint** and is importable (and runnable where data fixtures allow).
- [x] Wire the **equivalence gate** (Story 6) and golden tests into CI to run on every commit, alongside the existing `tests/` suite.
- [x] Add a "how codegen works" doc (`docs/`) and link it from the README, mirroring Epic 1's docs discipline.

---

## Notes / Risks (carry into planning)

- **The variable-binding contract change (Story 4) is the riskiest item** — it touches the `NodeDefinition` base, every reference node, and the contract docs. Sequence Stories 1–4 before 5, and bump per-node `version` so saved graphs migrate cleanly (Epic 1 Story 9 framework).
- **Equivalence (A2) is the single most important quality gate** in the whole product; under-invest here and trust in the "what you see runs" promise collapses. Treat the Story 6 harness as a hard CI gate, not an optional test.
- **Codegen quality is the marketing claim.** Budget for a broad fixture suite (Story 9); naming and formatting regressions are visible to users.
- **Don't build the Python→graph parser.** Bidirectional sync is deferred per A1/ADR 0001; export is one-way.
- The declarative seam (Story 8) must *exist* now even though its node families arrive in Phase 3 — bolting a second paradigm onto a functional-only compiler later is the exact rewrite ADR 0003 was written to avoid.
- Keep `compile_to_code` and `execute` **pure** (no I/O, no global state) so Epic 6 can wrap the executor in sandboxing without re-architecting it.

---

*How to use this file: tick each `- [ ]` to `- [x]` as work completes. A story is done when all
its tasks are checked; the epic is done when the Definition of Done checklist is complete.*
