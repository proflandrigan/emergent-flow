# Epic 11 — RAG (Retrieval-Augmented Generation)  ·  *stub*

> **Status: STUB.** Scaffolding only — not decomposed to implementation depth yet. Drafted
> alongside [Epic 9](./epic-9-ai-engineering-playground-prompt-lab.md) to pin the arc (see Epic
> 9's *Program Map*). Flesh it out after Epic 9 (LLM seam) and ideally Epic 10 (agent seam) land.

> **Repo ↔ roadmap numbering.** Repo **Epic 11**. Delivers the **RAG** facet of the GenAI stack
> promised in the proposal ("develop RAG applications") — part of roadmap **Epic 11**'s GenAI
> surface, adjacent to but distinct from the multi-agent orchestration in repo Epic 10. **Always
> qualify "repo Epic N" vs "roadmap Epic N"** (see [`epics/README.md`](./README.md)).

**Goal (product).** Let users build **RAG applications** on the canvas: ingest documents →
chunk → embed → index in a vector store → retrieve relevant context → generate a grounded answer,
with the whole pipeline visible and exportable as clean Python. The third wedge in the
AI-engineering-playground arc.

**Paradigm:** mostly **FUNCTIONAL** (ADR 0003) — RAG is a pipeline of deterministic transforms
(`load → chunk → embed → index → retrieve → ground`), each node one call returning an inspectable
object, exactly the shape the functional paradigm already nails. *Agentic* RAG (retrieve-then-
reason loops) composes with Epic 10's declarative agent seam.

**Reuses:** Epic 9's `ef.llm.call` for grounded generation, the injected-client seam + record/
replay ([ADR 0017](../docs/adr/0017-llm-nodes-injected-effectful-client.md)), and the eval/label/
export loop (retrieval + answer quality are evaluated with the same harness). Epic 10's agent seam
for agentic RAG.

**Lives in:** `emergentflow/` (the `ef.rag.*` node family + any embedding/vector-store adapters)
**and** `ui/` (a retrieval inspector — show which chunks were retrieved for an answer).

---

## New governing decisions this epic must make (ADRs to write)

- **ADR (proposed) — Embeddings under the injected-client seam.** Embedding calls are also
  non-deterministic network I/O. Extend ADR 0017 with an `EmbeddingClient` protocol (or a shared
  client surface) so embed calls are record/replayable and the ADR-0002 gate stays value-exact
  with no network in CI. Retrieval over stored vectors is then **deterministic**.
- **ADR (proposed) — Vector store as a pluggable, purity-respecting adapter.** Start with an
  in-memory store (numpy cosine — zero new deps, deterministic, CI-friendly); make the store a
  pluggable adapter so a real backend (e.g. Chroma/FAISS/pgvector, all optional
  `emergentflow[rag]`) can be swapped without changing nodes. Index build/query must fit the pure
  `execute`/`compile_to_code` model or ride the injected-adapter edge like the LLM client.

---

## Where things stand entering this epic (assumed)

- Epic 9 shipped the LLM call + injected-client seam + eval/label/export loop.
- Epic 10 (ideally) shipped the agent seam, enabling agentic RAG; if not, non-agentic RAG stands
  alone on the functional paradigm.
- No embedding or vector-store dependency exists yet; both arrive here, **optional** and
  license-checked.

---

## Definition of Done (epic-level, provisional)

- [ ] A user can wire `load → chunk → embed → index → retrieve → ground` on the canvas, run it, and
      get a grounded answer with the retrieved chunks shown — no code.
- [ ] Loaders + chunkers are **pure deterministic** functional nodes (golden + equivalence tests);
      embeddings ride the injected-client seam so the whole pipeline is CI-reproducible under
      replay with **no network access**.
- [ ] The vector store is a pluggable adapter; the default in-memory store adds **no** new hard
      dep; real backends are optional `emergentflow[rag]`, license-checked.
- [ ] Grounded generation reuses `ef.llm.call` (Epic 9) over retrieved context — no bespoke LLM
      path.
- [ ] Retrieval + answer quality are evaluable via Epic 9's eval/label loop (e.g. hit-rate,
      groundedness), and datasets export as JSONL.
- [ ] Both `execute` and `compile_to_code` stay pure given injected clients/adapters; all file and
      network I/O stays at the edge (ADR 0002 / ADR 0017).

---

## Story skeleton (to expand)

1. **ADRs + the embedding/vector-store seams** — `EmbeddingClient` protocol (record/replay);
   pluggable vector-store adapter with an in-memory default.
2. **Loader + chunker nodes** — `ef.rag.load_documents`, `ef.rag.chunk` (pure, deterministic;
   configurable strategy/size/overlap).
3. **Embed + index nodes** — `ef.rag.embed` (via the injected client), `ef.rag.index` (build the
   store).
4. **Retriever node** — `ef.rag.retrieve` (top-k over the store; deterministic given embeddings).
5. **Grounded generation** — wire retrieved chunks into a `PromptSpec` → `ef.llm.call`.
6. **Retrieval inspector + RAG eval** (`ui/` + eval loop) — show retrieved chunks per answer;
   evaluate/label retrieval + groundedness; export JSONL.
7. **(Optional) Agentic RAG** — retrieve-then-reason loops on Epic 10's agent seam.

---

## Notes / Risks

- **Determinism hinges on the embedding seam.** If embeddings aren't replayable, RAG tests become
  flaky and the ADR-0002 gate can't hold — do the `EmbeddingClient` ADR first, exactly as Epic 9
  did for completions.
- **Keep the default dep-free.** The in-memory numpy store keeps a bare RAG pipeline runnable and
  CI-friendly with zero new hard deps; real vector stores stay optional (ADR 0007). Resist making
  a heavyweight backend a hard dependency.
- **Chunking is where quality lives but also where determinism is easy** — keep chunkers pure and
  well-tested; they're the cheap, high-leverage part of RAG quality.
- **Sequencing:** non-agentic RAG can ship on the functional paradigm without Epic 10; only
  *agentic* RAG (Story 7) needs the agent seam.
