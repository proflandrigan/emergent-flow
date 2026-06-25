# Epic 6 — Node Library & Configuration UX

> **Repo ↔ roadmap numbering.** Epic files are numbered by **delivery order in this repo**; the
> [technical roadmap](../planning_docs/technical_roadmap.md) numbers epics **globally**. This
> file is repo **Epic 6** = roadmap **Epic 4** (Node Library & Configuration UX). It is *not*
> roadmap Epic 6 (that's the backend runtime, already partly delivered as repo Epic 4). **Always
> qualify "repo Epic N" vs "roadmap Epic N"** — see [`epics/README.md`](./README.md).

> The catalog widening that turns the app from "runs a hardcoded 5-node demo" into "does real
> data work." The execution machinery is already done — `cm.execute` runs real pandas /
> scikit-learn / statsmodels in-process, and the local server (repo Epic 4) serves it. What is
> missing is **breadth**: today each family (`cm.data`, `cm.clean`, `cm.stats`, `cm.ml`,
> `cm.reports`) ships exactly **one** reference node, the proposal's vertical slice
> (`load_csv → impute_missing → anova → train_classifier → generate_html_summary`). Those nodes
> exist to *prove the contract by construction*, not to be a usable palette. This epic widens
> each family by the **demo narrative**, ships the per-node metadata (defaults, help, validation
> hints) the canvas's schema-driven panels need, and exports a **catalog-as-data** artifact so
> the palette is data-driven — the fourth leg of the SDK→canvas contract.

**Phase:** 1 (initial slice already exists) → ongoing/continuous (roadmap §A6, Epic 4 is unbounded).
**Lives in:** `colonymind/` (the SDK tree owns the node catalog, defaults, and the export artifact). The config-panel *surface* and palette are the `ui/` tree (already built as repo Epic 5 Stories 3–4) and only *consume* this epic's outputs — they are not re-built here.
**Dependencies:** Epic 1 (node contract, param schema, registry), Epic 2 (`compile_to_code` / `execute` + the golden/equivalence harness every new node must pass), repo Epic 3 / roadmap 5 (type tokens + rules-as-data, so new ports validate). Integrates with repo Epic 4 (`/execute`, `/compile`) and repo Epic 5 (the canvas palette + config panels that render the catalog).
**Blocks:** roadmap Epic 8 (richer result types arrive as the catalog emits them), roadmap Epic 12 (the NL→graph agent's quality ceiling is the catalog's breadth and metadata).

---

## Definition of Done (epic-level)

- [ ] Each existing family is widened from one node to a **small, deliberate, demo-driven set** — enough to build a genuinely useful pipeline end-to-end, *not* an exhaustive catalog (roadmap Epic 4: "narrow but end-to-end," treat as continuous).
- [ ] Every node declares **defaults, help text, and param-level validation hints** on its param schema (Epic 1 contract), so the canvas panels are generated, never hand-coded per node.
- [ ] A versioned **catalog-as-data** artifact (`cm.export_catalog()` or equivalent) is published for the palette — its own version, decoupled from `Graph.schema_version`, with a golden test.
- [ ] **Every new node ships a golden + ADR-0002 equivalence test**, not just a unit test (per `CLAUDE.md` / ADR 0002) — `codegen` and `execute` routed through the same `cm.*` wrapper by construction.
- [ ] New node families reuse the **already-present, permissively-licensed** deps (pandas / scikit-learn / statsmodels; scipy is transitively available) — **no new GPL deps** (see `docs/licensing-and-dependencies.md`; pingouin was already rejected for this reason).
- [ ] A non-trivial pipeline (beyond the original 5 nodes) builds on the canvas, compiles, and executes end-to-end — the acceptance demo (Story 7).
- [ ] **Explicitly out of scope:** DL nodes (roadmap Epic 10), GenAI nodes (roadmap Epic 11), credentialed/remote connectors (roadmap Epic 9 — local-file loaders only here), and the raw-code escape-hatch node (decided in Story 1, deferred).

---

## Story 1 — Lock catalog decisions

> Mirror how Epics 1–5 fixed their decisions before building. Cheap to decide, expensive to
> retrofit across a catalog.

- [ ] **Breadth policy: demo-narrative-driven, not exhaustive.** The vertical slice already
  exists; widen only by what a demoable pipeline needs. Record DL/GenAI/connectors as
  out-of-scope here (roadmap Epics 10/11/9). Treat the catalog as *continuous*, never "done."
- [ ] **Escape-hatch (raw-Python / raw-SQL) policy — decide now, defer the node.** It is the one
  decision the roadmap flags as load-bearing. Recommend **deferring** it: it breaks the ADR-0001
  "no arbitrary code" purity and the ADR-0002 codegen↔execute equivalence (an arbitrary string
  can't be validated or proven-equivalent), and the local Jupyter trust model is the *only* thing
  that would make it safe — but it is **off the happy path to a functioning app**. Record the
  decision; revisit when a design partner actually hits the ceiling.
- [ ] **Catalog-as-data is the fourth contract artifact.** Decide its shape (palette entries:
  `type`, `version`, `family`, `label`, `category`, `description`, ports, and per-param
  `{type, default, help, hints}`) and that it carries **its own version**, decoupled from the IR
  `schema_version` to avoid spurious migrations (mirror the rules-as-data decision, repo Epic 3 / Story 3 of Epic 4).
- [ ] **Confirm the Epic 1 contract already carries defaults/help/hints** on params; extend the
  `NodeDefinition` param schema *minimally* only if a field is missing. Do not redesign the contract.
- [ ] **Restate per-node `version` discipline:** bump a node's contract `version` on any
  codegen/param change (distinct from `schema_version`) — the catalog artifact surfaces it.

---

## Story 2 — Catalog metadata on the contract + the export artifact

> The palette can only show what the SDK exports. Build the data path once, before widening the
> catalog, so every node added in Stories 3–6 lights up the palette for free.

- [ ] Ensure each param declares `default`, `help`, and `validation hints`; each node declares a
  human `label`, `category`, and one-line `description` for the palette (extend the Epic 1
  contract minimally per Story 1).
- [ ] `cm.export_catalog()` (in the `cm.codegen`/export namespace, alongside the rules export)
  emits the catalog-as-data artifact from the live registry — pure, deterministic, JSON-native.
- [ ] **Golden test** on the artifact (stable ordering); version the payload shape and document
  it in `docs/` next to the rules-as-data and result-payload contracts.
- [ ] Backfill the metadata on the **five existing reference nodes** so they render identically
  to the new ones (no two-tier palette).

---

## Story 3 — Widen the `cm.data` ingest family (local files only)

> Ingest is the front of every pipeline. Keep these **dumb local-file loaders** — the connector
> framework, credentials, and SQL sources are roadmap Epic 9, explicitly *not* here.

- [ ] `data.load_parquet` and `data.load_json` as thin pandas wrappers, mirroring `load_csv`'s
  contract (path param + a couple of sensible options, defaults + help text).
- [ ] A `data.load_sample` builtin-dataset node (ships a tiny bundled frame) so a brand-new
  canvas has something to run with zero filesystem setup — the fastest "it works" demo.
- [ ] Golden + equivalence test per node. **Deferred:** encoding/dialect edge cases, large-file
  streaming, anything credentialed (Epic 9).

---

## Story 4 — Widen the `cm.clean` transform family

> The middle of the pipeline. Pick the **few highest-value** pandas transforms; resist shipping a
> wrapper for every DataFrame method.

- [ ] A small set of transform nodes: `clean.drop_missing`, `clean.select_columns`,
  `clean.filter_rows`, `clean.cast_types` (names indicative). Each a thin, total pandas wrapper
  with defaults + help.
- [ ] Each emits/consumes the existing `DataFrame` type token so edges validate (repo Epic 3) for
  free — no new type tokens needed.
- [ ] Golden + equivalence test per node. **Deferred:** complex multi-column expression DSLs,
  groupby/window transforms (add only when a demo needs them).

---

## Story 5 — Widen the `cm.stats` family

> One canonical test already exists (`anova`). Add the two or three a real exploratory analysis
> reaches for — no more.

- [ ] `stats.ttest` (two-sample), `stats.correlation`, and `stats.describe` (summary statistics)
  as thin statsmodels / pandas wrappers (scipy is transitively available if cleaner — keep it
  permissively licensed; **no pingouin/GPL**).
- [ ] Results returned as the **inspectable** payload the `@public_op` contract already enforces
  (JSON-native / tidy DataFrame), so they render in-node via the Epic 4 result contract.
- [ ] Golden + equivalence test per node. **Deferred:** assumption-checking, multiple-comparison
  correction, effect sizes — methodology depth is a Researcher concern, not the happy path.

---

## Story 6 — Widen the `cm.ml` classical-ML family

> The biggest real gap. Today `train_classifier` does split + fit + score *inside one node* — fine
> as a demo, useless as a pipeline. Add the **separable** pieces so a user can compose
> train → predict → evaluate, while keeping the all-in-one node for the quick path.

- [ ] `ml.train_test_split`, `ml.train_regressor` (LinearRegression), a tree-based estimator
  (RandomForest classifier/regressor), `ml.predict`, and `ml.evaluate` (metrics) — thin
  scikit-learn wrappers.
- [ ] Introduce/confirm a `Model` type token on the relevant ports (repo Epic 3) so a fitted
  model wires only into `predict`/`evaluate`, not into a DataFrame input — structural validation
  for free.
- [ ] Respect the `@public_op` inspectable contract: a fitted estimator is **not** JSON-native, so
  model-bearing ports must round-trip as the contract allows (handle/reference, not a live object
  dumped into a response) — decide the representation here, it pairs with repo Epic 4 Story 3.
- [ ] Golden + equivalence test per node. **Deferred:** hyperparameter search, pipelines/CV,
  calibration, persistence to disk (Epic 9/14) — out of the happy path.

---

## Story 7 — Wire the catalog into the canvas + the acceptance demo

> The payoff: the widened catalog actually drives the palette, and a real pipeline runs
> end-to-end. This is the integration + the demo, not new SDK nodes.

- [ ] The canvas palette (repo Epic 5 Story 3) consumes `cm.export_catalog()`; the config panels
  (repo Epic 5 Story 4) render every new node's defaults/help/hints with **zero per-node UI code**.
- [ ] Confirm new nodes round-trip canvas → IR → `/compile` → downloadable `.py` and `/execute`
  with per-node status (the repo Epic 5 Story 8 loop) — including a `Model`-bearing edge.
- [ ] **Acceptance demo:** build a pipeline beyond the original five nodes — e.g.
  `load_sample → drop_missing → select_columns → train_test_split → train_regressor → evaluate`
  alongside a `stats.describe` branch and an HTML report — and run it to results on the canvas.
- [ ] Document the demo as the "what the app can do today" reference (supersedes the hardcoded
  5-node slice).

---

## Notes / Risks (carry into planning)

- **The catalog is unbounded — prioritize ruthlessly by the demo.** Roadmap Epic 4 is explicitly
  "continuous, not done." The failure mode is widening for completeness; ship the smallest set
  that makes a compelling pipeline, then stop. Every node added is forever-maintained surface.
- **Every node is two behaviors that must stay equivalent (ADR 0002).** A unit test is not enough —
  golden + equivalence is the gate, and routing both `codegen` and `execute` through the same
  `cm.*` wrapper keeps them true by construction. Do not add a node that only has `execute`.
- **Don't drift into adjacent epics.** Connectors/credentials are Epic 9 (local-file loaders only
  here); rich result rendering is Epic 8 (return the inspectable payload, let the UI render it);
  sandboxing is the hosted tier (Epic 6 hosted). The raw-code node is *decided* in Story 1 and
  *deferred*.
- **License hygiene is a real constraint.** New wrappers must stay Apache-compatible (pandas /
  sklearn / statsmodels / scipy — all BSD). The pingouin→statsmodels swap is the precedent; do
  not reintroduce a GPL dep for a marginally nicer API.
- **`Model`-bearing ports stress the `@public_op` inspectable contract.** A live estimator is not
  JSON-native — settle its representation in Story 6 *before* widening the ML family, or the
  result-payload contract (repo Epic 4 Story 3) churns.
- **Metadata before breadth.** Story 2 (the data path) lands before Stories 3–6 so each new node
  lights up the palette and panels for free — otherwise the catalog and the UI drift.

---

*How to use this file: tick each `- [ ]` to `- [x]` as work completes. A story is done when all
its tasks are checked; the epic is done when the Definition of Done checklist is complete.*
</content>
</invoke>
