# Epic 16 — Data Gathering, Transform, Analytics & Research Depth

> **Repo <-> roadmap numbering.** Epic files are numbered by **delivery order in this repo**; the
> [technical roadmap](../planning_docs/technical_roadmap.md) numbers epics **globally**. This file
> is repo **Epic 16**. It broadens the four horizontal capabilities that every persona (data
> modeller, data scientist, ml engineer, researcher) leans on — **getting data in**, **reshaping
> it**, **analyzing it**, and **turning the result into a defensible research artifact** — closing
> the highest-leverage gaps in each. It follows the same wrapper-routing + inspectable-representation
> + generated-catalog strategy proven by repo Epics 8/12/13/15, so ADR-0002 equivalence and the
> `@public_op` inspectable contract hold by construction for every new node.
> **Always qualify "repo Epic N" vs "roadmap Epic N"** — see [`epics/README.md`](./README.md).

> **Why one epic across four surfaces instead of four small ones.** The gaps are not independent:
> a `pivot`/`derive_column` transform is worthless without a source that produces messy real data
> (HTTP/cloud), an experiment-analysis node is worthless without the effect-size plumbing a
> non-parametric test also needs, and a "research artifact" (multi-section report + lineage +
> reproducibility) only pays off once all three upstream stages exist. Delivering them together
> keeps one acceptance story — *ingest a real API → reshape → run an experiment analysis → emit a
> reproducible report with lineage* — as the north star, so each story group is pulled by a concrete
> end-to-end flow rather than shipped as disconnected nodes.

> **Three structural bets, each mirroring an existing precedent.**
>
> 1. **New ingestion is effectful → it goes through the injected-client seam, never inline
>    I/O (ADR 0017 / ADR 0018).** The HTTP/REST source, cloud-object-storage, and Google-Sheets
>    loaders are `requires_client = True` nodes: a live adapter makes the real call, a
>    content-hash-keyed **replay adapter** is the default in tests and the equivalence gate, so CI
>    stays offline and value-exact. This is the *same seam* the warehouse (Epic 13) and LLM (Epic 9)
>    families already use — no new impurity is introduced into `compile_to_code`/`execute`.
> 2. **New transforms and analytics are pure functions in existing families → they extend the
>    catalog, not the architecture.** Reshape/derive/dedup/date/string ops land in
>    `emergentflow/clean/`; new tests land in `emergentflow/stats/`. They are ordinary
>    `@public_op` functions wrapped by ordinary nodes; the only novelty is breadth.
> 3. **"Research artifact" is a first-class output, not a `markdown_note`.** The multi-section
>    report builder, data-lineage surfacing, reproducibility capture, and data-quality gate are the
>    genuinely new *product* surface here. Lineage is nearly free because the IR **is** a DAG; the
>    report builder composes existing inspectable artifacts (figures, tidy frames, model summaries)
>    rather than re-rendering them.

**Phase:** Follows repo Epic 12 (the `ef.stats`/`ef.viz` model + chart-adapter + `PlotSpec`
precedent this epic's analytics and report stories reuse), repo Epic 13 (the `WarehouseClient`
seam + connection-profile store + replay-adapter discipline this epic's ingestion stories mirror),
and repo Epic 9 (the `ef.llm` client seam consumed by the Google-Sheets/HTTP-auth and
research-summary paths). Sequenced after these so ingestion can reuse the connection-profile store,
analytics can reuse `FittedStatsModel`/`PlotSpec`, and the report builder can compose already-
inspectable artifacts.
**Lives in:** `emergentflow/` — the SDK tree owns the new wrappers (`emergentflow/data/` ingestion
seams, `emergentflow/clean/` transform verbs, `emergentflow/stats/` tests, a new
`emergentflow/research/` for reports/lineage/reproducibility/quality), the new node archetypes
(`emergentflow/nodes/examples/`), the generated catalog entries, and the new type tokens. The
canvas palette + config panels (`ui/`, repo Epic 5) **only consume** the generated catalog — new
**Report** and **Lineage** inspector renderers in `ui/` are the sole hand-written UI here.
**Dependencies:** Epic 1 (node contract, param schema, registry, `@register`), Epic 2
(`compile_to_code`/`execute` + golden/equivalence harness), Epic 3 / roadmap 5 (type tokens +
rules-as-data for new ports), Epic 9 (LLM client seam — consumed), Epic 12 (`FittedStatsModel`,
`PlotSpec`, chart catalog — consumed/extended), Epic 13 (connection-profile store + replay-adapter
pattern — reused). `pandas`, `numpy`, `scipy`, `scikit-learn`, `statsmodels` are **already**
runtime deps. New **hard** deps: **none**. New **optional extras** (all `importorskip`-gated,
typed-error on absence): `[excel]` (openpyxl), `[cloud]` (fsspec + s3fs/gcsfs), `[fuzzy]`
(rapidfuzz), `[umap]` (umap-learn), `[causal]` (econml/dowhy — stretch), `[report-pdf]`
(weasyprint), `[pii]` (presidio — stretch; regex-based redaction ships in base).
**Blocks / raises the ceiling of:** the roadmap Epic 12 NL→graph agent (every story widens the node
surface it can target), repo Epic 11 (RAG — this epic ships the document-ingestion *loader* half and
explicitly **defers retrieval/vector-store** to Epic 11 rather than duplicating it), and any future
"published research / notebook export" epic.

> **Deliberate scope boundary with Epic 11 (RAG).** Document/PDF ingestion appears here **only** as
> a `DataFrame`-producing loader (chunked text + metadata columns), so the transform/analytics/LLM
> nodes can operate on document corpora. **Embedding indexing, vector stores, and retrieval stay in
> Epic 11** — this epic does not build a retriever. Where a research flow needs retrieval, it wires
> the loader here into the Epic 11 surface.

---

## Definition of Done (epic-level)

### Data gathering
- [x] **HTTP/REST source is a first-class node.** A `data.http_fetch` node fetches from a URL
  (headers/auth resolved from a connection profile env-var name, **never** a literal secret in the
  IR), supports cursor/offset pagination and JSON-path extraction, and returns a tidy DataFrame. It
  is `requires_client = True`, routes through an `HttpClient` seam with a content-hash-keyed replay
  adapter, and **never touches the network in CI**.
- [x] **Cloud object storage + multi-file ingestion.** `load_csv`/`load_parquet`/`load_json` accept
  `s3://`/`gs://`/`az://` URIs and **glob patterns** (`data/*.csv`), row-concatenating matches with
  an optional `source_file` provenance column. Remote reads run behind the `[cloud]` extra
  (fsspec); base install keeps local + glob. Missing extra raises a typed
  `MissingOptionalDependencyError`.
- [x] **Spreadsheet loaders.** `load_excel` (sheet selection, header row, `[excel]` extra) and a
  Google-Sheets source (connection-profile auth, client seam + replay) are reachable as nodes.
- [x] **Schema-on-load validation.** Every loader accepts an optional expected-column/dtype
  contract that fails fast with a typed `DataLoadError` listing the mismatch — the foundation the
  data-quality gate (below) reuses.
- [x] **Expanded bundled samples.** `load_sample` gains a realistic time series, a text corpus, and
  a transactions/events table (permissively licensed) so demos and personas have material.

### Transform
- [ ] **Reshape verbs.** `reshape` node covers `pivot` (long→wide) and `melt` (wide→long), the
  single biggest missing transform.
- [ ] **Derive / case-when.** A `derive_column` node adds computed and conditional (case-when)
  columns via a safe expression grammar — no drop to `custom_code` for the common case.
- [ ] **Row-combining verbs.** `concat` (row-wise union of ≥2 frames, schema-aligned), `deduplicate`
  (subset + keep), and `sort` nodes ship.
- [ ] **String & date verbs.** A `clean_text` node (trim, case-normalize, regex extract/replace,
  split) and a `parse_dates` node (string→datetime + extract year/month/dow/quarter) close the
  "impossible without custom code" gap.
- [ ] **Sampling & fuzzy join.** A `sample_rows` node (random/stratified/top-n, **seed captured**)
  and a `fuzzy_join` node (string-similarity keyed merge, `[fuzzy]` extra) ship.
- [ ] **Every transform is non-mutating.** New transforms return an augmented/new frame and guard
  against silently overwriting existing columns (the `ef.timeseries` discipline), with a typed
  `CleanError` on collision.

### Analytics
- [ ] **Non-parametric tests + inference plumbing.** Mann-Whitney, Wilcoxon, Kruskal-Wallis, and
  chi-square/Fisher ship as `ef.stats` ops; existing `ttest`/`anova` gain **effect sizes** (Cohen's
  d, η²) and **confidence intervals** as first-class output columns, plus a shared
  **multiple-comparison correction** (Bonferroni/BH) utility.
- [ ] **Experiment analysis + power.** A `test_proportions` node (two-proportion z-test / uplift
  with CI) and a `power_analysis` node (sample-size / MDE) ship — the study-design pair researchers
  ask for constantly.
- [ ] **Crosstab.** A `crosstab` node (counts + margins + chi-square), distinct from
  `group_by_aggregate`.
- [ ] **Dimensionality reduction.** A `reduce_dimensions` transform (PCA/t-SNE on hard deps; UMAP
  behind `[umap]`) plus a projection scatter viz, feeding exploration/clustering/embeddings.
- [ ] **Causal inference (stretch, gated).** Diff-in-diff + propensity-score matching on statsmodels
  (already a dep); CATE/uplift behind `[causal]`. Ships as a **parallel seam** to `stats` (like
  `recommend` is to `ml`), or is explicitly deferred to a follow-up epic if descoped.
- [ ] **Product analytics.** `cohort_retention` and `funnel` analysis nodes ship over event frames.

### Research & reproducibility
- [ ] **Multi-section report builder.** A `build_report` node composes markdown notes + figures
  (`PlotSpec`) + tidy tables + model summaries into one parametrized document, exporting HTML (base)
  and PDF (`[report-pdf]`). Replaces the single-purpose `reports.generate_html_summary` with a
  composable builder.
- [ ] **Data lineage / provenance is surfaced.** Because the IR is a DAG, a pure
  `trace_lineage(graph, node_id)` function returns the upstream source→transform chain behind any
  artifact; the canvas renders it in a **Lineage** inspector tab, and the report builder embeds it.
- [ ] **Reproducibility capture.** A `capture_run` utility records seeds, source content-hashes, and
  resolved dependency versions; exported reports and compiled modules embed this block so a run is
  re-runnable. Seed capture threads through `sample_rows`, `train_test_split`, and any stochastic
  op.
- [ ] **Data-quality gate.** An `assert_data` node runs declarative expectations (non-null, range,
  uniqueness, allowed-values, row-count delta) and **fails the graph loudly** with a typed
  `DataQualityError` + a tidy violations frame. Builds on schema-on-load; complements Epic 14 gates.
- [ ] **Document ingestion loader (RAG-adjacent, retrieval deferred).** A `load_documents` node
  chunks PDF/text/markdown into a tidy `(doc_id, chunk_id, text, metadata)` frame. **No embedding or
  retrieval** — that is Epic 11; this only produces the frame those consume.
- [ ] **Data dictionary / codebook.** A `data_dictionary` node auto-emits a documented schema
  (types, ranges, distributions, null rates, notes) per dataset, pairing with `auto_eda`.
- [ ] **PII handling.** A `redact_pii` node detects + masks common PII (regex-based in base; presidio
  behind `[pii]`), positioned to run immediately after ingestion.

### Invariants (hold for every node in this epic)
- [ ] **The inspectable contract holds everywhere.** Every new `@public_op` returns a
  JSON-native / Pydantic / dataclass / tidy-DataFrame value (or container thereof); no bare object,
  live driver handle, or live model is ever dumped into a result payload. New tokens (`Report`,
  `Lineage`, `DocumentFrame`) degrade their live fields on the result-payload contract.
- [ ] **ADR-0002 holds by construction.** `codegen` and `execute` for every node route through the
  same `ef.*` wrapper; both stay **pure** (I/O only via the injected client seam for ingestion).
  A **parametrized equivalence harness** covers the new node matrix, keyed on the inspectable output,
  gated in CI alongside the existing gate. Determinism pinned with fixed seeds.
- [ ] **New type tokens registered** (`Report`, `Lineage`, `DocumentFrame`) with Epic 3 compatibility
  rules; ingestion/transform/analytics reuse the existing `DataFrame`/`FittedStatsModel`/`PlotSpec`
  tokens.
- [ ] **No new hard deps; every heavy path is an optional extra** with `importorskip` tests and a
  typed "install the `[extra]`" error. **License hygiene: no GPL** (openpyxl MIT, fsspec/s3fs BSD,
  rapidfuzz MIT, umap-learn BSD, weasyprint BSD, presidio MIT).
- [x] **Contract artifacts regenerated + UI boundary intact** (`scripts/export_ui_contracts.py`,
  `scripts/check_ui_boundary.py`) — `ui/` still imports zero `emergentflow`.
- [ ] **Acceptance demos (Story 25)** build on the canvas, compile to `.py`, and execute end-to-end.
- [ ] **Explicitly out of scope:** streaming/CDC ingestion, real-time/online transforms, a vector
  store or retriever (Epic 11), full survey/psychometric analysis, GPU-only analytics, hosted secret
  management, and multi-user report collaboration.

---

## Story group A — Data gathering (ingestion seams) — ✅ **COMPLETE** (Stories 1-4)

> **Group A status.** All four stories are delivered, with contract artifacts regenerated
> (`scripts/export_ui_contracts.py`, `npm run gen:types`) and the `ui/` boundary verified clean.
> Gates at completion: `ruff check` / `ruff format --check` clean, `mypy emergentflow` clean,
> **2714 passed / 23 skipped / 0 failed**, ADR-0002 equivalence gate **261 passed**, and the UI
> gates (`npm run lint` / `typecheck` / `test`) green at **612 passed**.
>
> **New surface:** three new nodes (`data.http_fetch`, `data.load_excel`,
> `data.load_google_sheet`), two new optional extras (`[cloud]`, `[excel]`), a third injected
> client seam (`ClientKind.HTTP`), and the shared schema-on-load validator that Story 19's
> `assert_data` gate will reuse. **No new hard dependencies.**
>
> Story group B (transform verbs) is the next increment and is not started.

## Story 1 — HTTP/REST source node (`data.http_fetch`) — ✅ done
- [x] **Decide the seam up front.** `http_fetch` is `requires_client = True`; it never calls the
  network inline. Define an `HttpClient` protocol (`emergentflow/data/http/protocol.py`) mirroring
  `WarehouseClient`: a live `RequestsHttpClient` (stdlib `urllib` or optional `httpx`) and a
  content-hash-keyed `ReplayHttpClient` (default in tests/equivalence) recording `(method, url,
  headers-sans-secret, body) → response`.
- [x] **Auth via connection profile only.** The node carries a profile name or an
  `api_key_env`/`token_env` **name**; the client resolves the value at call time. Credentials never
  enter the IR (reuse `emergentflow/connections/` + the `secrets`/env resolution from Epic 9/13).
- [x] **Shape the response into a frame.** Params: `json_path` (record selector), `pagination`
  (`none|cursor|offset|page`, with cursor/param field names + a max-pages cap), `flatten` for nested
  records. Output: tidy DataFrame. Typed `DataLoadError` on non-2xx / parse failure.
- [x] **Wrapper + node + catalog.** `ef.data.http_fetch` wrapper; `http_fetch` reference node routing
  both `codegen` and `execute` through it; generated catalog entry.
- [x] Golden `ast.parse` + `ruff check` on a representative paginated fetch; equivalence via the
  Story 24 harness using `ReplayHttpClient` fixtures.

> **Delivered as:** `emergentflow/data/errors.py` (typed `DataError`/`DataLoadError`/
> `SchemaContractError`/`MissingOptionalDependencyError`); `emergentflow/data/http/`
> (`protocol.py` seam types, `replay.py` content-addressed offline client, `live.py`
> stdlib-`urllib` adapter with an `http`/`https` scheme allow-list, `fetch.py` the
> `ef.data.http_fetch` wrapper); `ClientKind.HTTP` + the `http` seam on the `Clients` bundle,
> threaded through `compile_to_code`; and the `data.http_fetch` reference node. Catalog
> regeneration is batched into Story group A's final task.

## Story 2 — Cloud object storage + multi-file / glob ingestion — ✅ done
- [x] **Glob + concat in base install.** Extend `load_csv`/`load_parquet`/`load_json` to accept a
  glob; row-concat matches, aligning schemas, with an optional `source_file` column. Deterministic
  file ordering (sorted) for stable golden output.
- [x] **Remote URIs behind `[cloud]`.** Route `s3://`/`gs://`/`az://` through fsspec (lazy import).
  Missing extra → typed `MissingOptionalDependencyError`. Object-store auth uses a connection
  profile (env-var names), not literals.
- [x] **Reads stay pure via the seam where credentialed.** Local + public remote reads go through
  `emergentflow/codegen/export.py`-style edge I/O; credentialed remote reads route through an
  injected storage client with a replay adapter so CI is offline.
- [x] Node param + catalog updates; goldens for a glob load and a mocked `s3://` load.

> **Delivered as:** `_is_glob`/`_resolve_glob`/`_concat_files` (sorted, schema-aligned,
> `RangeIndex`-reset row concat with an optional `source_file` provenance column and a
> collision guard) plus `REMOTE_URI_SCHEMES`/`_open_remote`/`_resolve_remote_glob` in
> `emergentflow/data/__init__.py`; the new `[cloud]` extra (fsspec/s3fs/gcsfs/adlfs, all
> BSD-3-Clause) with an `importlib.util.find_spec` gate that raises
> `MissingOptionalDependencyError` before any fsspec import; and `source_file`/`connection`
> params on all three loader nodes (versions bumped, goldens + glob equivalence tests).
>
> **Deviation from the written story, decided in planning:** the third bullet's *"injected
> storage client with a replay adapter"* was **not** built as a second client seam. Credentialed
> remote reads instead resolve `storage_options` from a connection profile's env-var **names** at
> the loader edge (`_resolve_storage_options`), and the offline test lane drives the real remote
> code path through fsspec's in-memory filesystem (`memory://`, a documented test seam in
> `REMOTE_URI_SCHEMES`) rather than recorded fixtures. The invariants the bullet exists to protect
> — credentials never in the IR, CI never touching the network — both hold. A full
> `StorageClient` seam mirroring `WarehouseClient` remains available if a later story needs
> content-hash-keyed replay for object storage.

## Story 3 — Spreadsheet loaders (Excel + Google Sheets) — ✅ done
- [x] **`load_excel`** (`[excel]`/openpyxl): sheet name/index, header row, usecols, dtype contract.
  Typed error on missing extra or missing sheet. Reference node + catalog.
- [x] **Google Sheets source**: `requires_client = True` over the same HTTP/client seam as Story 1,
  auth via connection profile; returns a tidy frame. Replay fixtures in tests.
- [x] Goldens + equivalence for both (Excel via a checked-in fixture workbook; Sheets via replay).

> **Delivered as:** `ef.data.load_excel` behind the new `[excel]` extra (openpyxl, MIT), reusing
> the Story 2 glob/remote/`source_file` machinery, with a guard against
> `sheet=None` (which would return pandas' dict-of-frames and break the inspectable contract) and
> a typed `DataLoadError` on a missing sheet; the `data.load_excel` node, whose `sheet` param
> coerces an all-digit string to `int` inside the shared `_args` so `codegen` and `execute` pass
> identical *types*; `ef.data.load_google_sheet` in `emergentflow/data/http/sheets.py` over the
> Story 1 `HttpClient` seam; and the `data.load_google_sheet` node with replay-fixture equivalence.
>
> **Two deviations, both deliberate.** (1) The **dtype contract** named in the first bullet is not
> implemented here — schema-on-load is Story 4's shared validator and is wired into *every* loader
> there, including `load_excel`, rather than being built twice. (2) Excel goldens build their
> fixture workbooks **in-test** with pandas instead of checking a binary `.xlsx` into the repo,
> which keeps the diff reviewable and the fixture regenerable. The Google Sheets source reads the
> **CSV-export endpoint** (`/gviz/tq?tqx=out:csv`) rather than the Sheets REST API — a plain GET
> over the existing seam, so it adds no Google SDK dependency and no OAuth flow; a private sheet is
> reached with whatever credential the injected client is configured to send.

## Story 4 — Schema-on-load validation + expanded samples — ✅ done
- [x] **Optional load contract.** Every loader accepts `expect_columns` / `expect_dtypes`; mismatch
  raises `DataLoadError` naming missing/extra/mistyped columns. Shared validator reused by the
  Story 20 quality gate.
- [x] **Expand `load_sample`.** Add a small permissively-licensed time series, text corpus, and
  transactions/events dataset; register names in `SAMPLE_DATASETS`; document licenses.
- [x] Unit + golden coverage for contract failure paths and each new sample.

> **Delivered as:** `emergentflow/data/contract.py::validate_schema` — one shared gate wired into
> all five loaders (`load_csv`/`load_parquet`/`load_json`/`load_excel`/`load_google_sheet`) and
> their nodes. It **collects** missing, extra, and mistyped columns across all three checks and
> raises a single `SchemaContractError` (a `DataLoadError` subclass) describing everything at once,
> rather than failing on the first problem. Dtypes are compared as strings (`str(series.dtype)`)
> so the contract stays JSON-native and survives a trip through the IR. Validation runs **once on
> the final frame, after glob concatenation** — covered by a regression test where two files each
> satisfy the contract only in aggregate. `load_sample` gains `web_traffic` (daily time series),
> `reviews` (text corpus), and `transactions` (retail events, ~79 repeat customers so cohort and
> funnel analysis are meaningful).
>
> **Deviation:** the three new samples are **generated deterministically in-process** from a fixed
> seed rather than vendored as data files — no upstream license question, no binary files in the
> repo, and byte-identical output across calls *and* processes (proven by a subprocess digest
> test), which is what keeps goldens and the ADR-0002 gate stable. `docs/licensing-and-dependencies.md`
> records the split: sklearn BSD-3-Clause for the original three, no upstream license for the
> synthetic three, with an explicit note that they are not real-world data.

---

## Story group B — Transform verbs (reshape, derive, combine, clean)

## Story 5 — Reshape (`pivot` / `melt`)
- [ ] `ef.clean.reshape` wrapper with `mode="pivot"|"melt"` and the pandas-mapped params
  (index/columns/values/aggfunc for pivot; id_vars/value_vars/var_name/value_name for melt).
  Non-mutating; typed `CleanError` on duplicate-index-without-aggfunc.
- [ ] `reshape` reference node + catalog; goldens for both modes; equivalence via Story 24.

## Story 6 — Derive column / case-when (`derive_column`)
- [ ] **Safe expression grammar.** A restricted, `ast`-validated expression evaluator (arithmetic,
  comparisons, string ops, `where`/case-when over existing columns) — **no arbitrary eval**, no
  `custom_code` trust level. Reuse the `emergentflow/script/` AST-renaming discipline for wiring.
- [ ] Params: ordered list of `(new_column, expression)` or `(new_column, [when/then], else)`.
  Column-overwrite guard.
- [ ] `derive_column` node + catalog; goldens covering arithmetic, string, and multi-branch
  case-when; equivalence.

## Story 7 — Combine & order (`concat`, `deduplicate`, `sort`)
- [ ] `ef.clean.concat` (≥2 DataFrame inputs, schema-align, optional `keys`/`source` column);
  variadic-input node archetype. `ef.clean.deduplicate` (subset, keep first/last). `ef.clean.sort`
  (multi-key, asc/desc, na_position).
- [ ] Three reference nodes + catalog entries; goldens + equivalence each.

## Story 8 — String & date cleaning (`clean_text`, `parse_dates`)
- [ ] `ef.clean.clean_text`: per-column pipeline of trim / lower-upper / regex extract / regex
  replace / split-to-list. Non-mutating.
- [ ] `ef.clean.parse_dates`: string→datetime (format or inferred) + extract components
  (year/month/day/dow/quarter/hour) into new columns. Overwrite guard.
- [ ] Two nodes + catalog; goldens + equivalence.

## Story 9 — Sampling & fuzzy join (`sample_rows`, `fuzzy_join`)
- [ ] `ef.clean.sample_rows`: `mode="random"|"stratified"|"top_n"`, `n`/`frac`, `by` for strata,
  **explicit `seed` captured** and threaded into the reproducibility block (Story 19).
- [ ] `ef.clean.fuzzy_join` (`[fuzzy]`/rapidfuzz): left/right key, similarity metric + threshold,
  one-to-one vs one-to-many. Typed error on missing extra.
- [ ] Two nodes + catalog; goldens + equivalence (fuzzy under a `[fuzzy]`-available lane; seed makes
  sampling deterministic).

---

## Story group C — Analytics depth

## Story 10 — Non-parametric tests + inference plumbing
- [ ] `ef.stats` gains `mann_whitney`, `wilcoxon`, `kruskal`, `chi_square` (+ Fisher exact for 2×2),
  each returning a tidy result frame (statistic, p, df, effect size where defined).
- [ ] **Effect sizes + CIs on existing tests.** Extend `ttest`/`anova` output with Cohen's d / η²
  and confidence intervals. Shared `emergentflow/stats/` helper.
- [ ] **Multiple-comparison correction** utility (Bonferroni/Benjamini-Hochberg) applicable to any
  p-value frame.
- [ ] Reference nodes (`mann_whitney`, `wilcoxon`, `kruskal`, `chi_square`) + catalog; goldens +
  equivalence; extend the existing ttest/anova goldens.

## Story 11 — Experiment analysis + power (`test_proportions`, `power_analysis`)
- [ ] `ef.stats.test_proportions`: two-proportion z-test / uplift with CI + relative lift, tidy
  output. `ef.stats.power_analysis`: sample size / MDE / achieved power (statsmodels power).
- [ ] Two nodes + catalog; goldens + equivalence.

## Story 12 — Crosstab (`crosstab`)
- [ ] `ef.stats.crosstab`: rows × cols counts, margins, normalized options, chi-square of
  independence. Distinct from `group_by_aggregate`. Node + catalog; goldens + equivalence.

## Story 13 — Dimensionality reduction (`reduce_dimensions` + projection viz)
- [ ] `ef.ml.reduce_dimensions` (or `ef.stats`): PCA + t-SNE on hard deps, UMAP behind `[umap]`;
  returns the reduced-coordinate frame (+ explained-variance frame for PCA). Non-mutating; seed
  captured.
- [ ] A projection scatter **`PlotSpec`** viz node (reuse Epic 12 chart adapter) colored by a label
  column.
- [ ] Two nodes + catalog; goldens + equivalence (UMAP under its extra lane).

## Story 14 — Product analytics (`cohort_retention`, `funnel`)
- [ ] `ef.stats.cohort_retention`: cohort key + period → retention matrix (tidy + wide). `funnel`:
  ordered step columns/events → per-step conversion + drop-off frame.
- [ ] Two nodes + catalog; goldens + equivalence on deterministic event fixtures.

## Story 15 — Causal inference *(stretch; gated)*
- [ ] **Base (statsmodels, already a dep):** difference-in-differences and propensity-score matching
  as `ef.stats` ops returning tidy effect frames with CIs.
- [ ] **Optional (`[causal]`/econml or dowhy):** CATE / uplift estimation, typed error on missing
  extra.
- [ ] Ships as a parallel `emergentflow/causal/` seam **or** is explicitly deferred to a follow-up
  epic and struck from this epic's DoD — decide in planning. Nodes + catalog + goldens if kept.

---

## Story group D — Research & reproducibility (the genuinely new product surface)

## Story 16 — Multi-section report builder (`build_report`)
- [ ] **New `emergentflow/research/report.py`.** A composable builder: ordered sections, each a
  markdown block, a `PlotSpec` figure, a tidy table, or a model summary. Pure function
  `build_report(sections, meta) -> Report`; HTML render in base, PDF via `[report-pdf]`.
- [ ] **New `Report` type token** (Epic 3), degrading its rendered-bytes field on the result
  payload; a **Report** inspector renderer in `ui/`.
- [ ] `build_report` node with a variadic section-input archetype; export path via
  `emergentflow/codegen/export.py` (I/O at the edge). Deprecate/absorb
  `reports.generate_html_summary`.
- [ ] Goldens + equivalence keyed on the structured report model (not rendered bytes).

## Story 17 — Data lineage / provenance (`trace_lineage`)
- [ ] **Pure `trace_lineage(graph, node_id) -> Lineage`** in `emergentflow/research/lineage.py`:
  walks the IR DAG to return the source→transform→artifact chain (nodes, ports, op types) behind a
  target. No new schema field — computed from the existing graph (mirrors the Epic 14 "state beside
  the graph" discipline).
- [ ] **`Lineage` type token** + a **Lineage** inspector tab in `ui/` (consume via generated
  catalog/contract, no `emergentflow` import). Report builder can embed a lineage section.
- [ ] Server route to compute lineage for a node (stateless, carries the graph); tests for
  branching/merging DAGs.

## Story 18 — Reproducibility capture (`capture_run`)
- [ ] **`capture_run`** records: seeds (from `sample_rows`/`train_test_split`/stochastic ops),
  source content-hashes (reuse the LLM/warehouse content-hash keying), and resolved dep versions.
  Pure over provided inputs; version/env read quarantined to the edge.
- [ ] Thread a captured `seed` through every stochastic op added in this epic; embed the
  reproducibility block into `build_report` output and as a header comment in compiled modules.
- [ ] Tests: same graph + same seeds ⇒ identical capture block.

## Story 19 — Data-quality gate (`assert_data`)
- [ ] **`assert_data`** node: declarative expectation list (non-null, min/max range, uniqueness,
  allowed-values, regex-match, row-count delta vs upstream). Passing → passthrough frame; failing →
  typed `DataQualityError` **and** a tidy violations frame (so the canvas shows *what* failed).
  Reuse the Story 4 schema validator.
- [ ] Node + catalog; goldens + equivalence for pass and fail paths.

## Story 20 — Document ingestion loader (`load_documents`) *(RAG loader half only)*
- [ ] **`load_documents`**: PDF/text/markdown → tidy `(doc_id, chunk_id, text, metadata...)` frame,
  with configurable chunking (size/overlap). PDF parsing behind an optional extra
  (`[docs]`/pypdf, MIT); typed error on absence. **New `DocumentFrame` conceptual shape** (a tagged
  `DataFrame`, not embeddings).
- [ ] **Explicitly no embedding/retrieval** — cross-reference Epic 11; add a note in the node doc
  pointing there.
- [ ] Node + catalog; goldens on a checked-in tiny PDF/markdown fixture.

## Story 21 — Data dictionary / codebook (`data_dictionary`) + PII redaction (`redact_pii`)
- [ ] **`data_dictionary`**: per-column type, null rate, cardinality, range/top-values, optional
  user notes → tidy frame + a report-ready section. Pairs with `auto_eda`.
- [ ] **`redact_pii`**: regex-based detection + masking (email, phone, SSN-like, credit-card-like) in
  base; presidio behind `[pii]` for NER-based detection. Positioned to run right after ingestion.
- [ ] Two nodes + catalog; goldens + equivalence.

---

## Story group E — Cross-cutting, testing & the payoff

## Story 22 — Type tokens, catalog & contract regeneration
- [ ] Register `Report`, `Lineage`, `DocumentFrame` tokens with Epic 3 compatibility rules (a
  `Report` wires into an export/inspect node but not a `DataFrame` consumer; a `Lineage` is
  inspect-only; a `DocumentFrame` wires where a `DataFrame` does plus into `load_documents`
  consumers).
- [ ] Regenerate `ui/src/generated/*` (`scripts/export_ui_contracts.py`), `ui/src/generated/ir.ts`
  (`npm run gen:types`), and verify `scripts/check_ui_boundary.py`.

## Story 23 — `ui/` inspector renderers (Report + Lineage)
- [ ] A **Report** renderer (renders the composed HTML) and a **Lineage** tab (renders the
  source→artifact chain) in the Inspector Results area, consuming only generated contracts. Vitest
  coverage; eslint/tsc gates.

## Story 24 — Equivalence & golden testing at scale
- [ ] Extend the parametrized equivalence harness to cover the full new node matrix, keyed on each
  node's **inspectable** output (frames/reports/lineage), with fixed seeds and replay fixtures for
  every `requires_client` ingestion node. Gate in CI beside the existing `-m equivalence` gate.
- [ ] Ensure the offline discipline: no ingestion node touches the network in CI; every optional
  extra has an `importorskip` lane and a base-install typed-error test.

## Story 25 — Wire into the canvas + acceptance demos
- [ ] **North-star demo:** `http_fetch (replay) → parse_dates → derive_column → assert_data →
  test_proportions → build_report (with lineage + reproducibility block)` builds on the canvas,
  compiles to `.py`, and executes end-to-end.
- [ ] **Transform demo:** `load (glob) → clean_text → reshape (melt) → group_by_aggregate →
  crosstab → viz` end-to-end.
- [ ] **Research demo:** `load_documents → data_dictionary → redact_pii → build_report (PDF)`
  end-to-end (under the relevant optional-extra lanes).

---

## Notes / Risks (carry into planning)

- **Scope is large by design — sequence by story group, ship incrementally.** Groups A and B are
  the load-bearing, low-risk breadth (pure transforms + the already-proven client seam) and should
  land first. Group D (reports/lineage/reproducibility/quality) is the real product novelty and the
  differentiator; it depends on A/B/C producing artifacts worth reporting on. Group C's causal story
  (Story 15) is the most likely descope candidate.
- **Don't re-litigate the client seam.** HTTP/cloud/Sheets ingestion must reuse the ADR-0017/0018
  `requires_client` + replay-adapter pattern verbatim; any temptation to do inline `requests.get`
  inside `execute` breaks ADR-0002 purity and the offline-CI invariant.
- **Lineage is nearly free — resist over-building.** It is a pure walk of the existing DAG; do **not**
  add a `Graph` schema field or a persistence layer for it (mirror Epic 14's "state beside the
  graph").
- **The `derive_column` expression grammar is a security surface.** It must be `ast`-restricted, not
  `eval`; `custom_code` already occupies the "unsandboxed, user-trusted" niche and this must **not**
  become a second one.
- **RAG boundary discipline.** `load_documents` produces a frame and stops. Every reviewer should
  confirm no embedding/vector-store/retriever code creeps in — that surface belongs to Epic 11.
- **Optional-extra sprawl.** This epic adds several extras; keep each genuinely optional, each with a
  typed error + `importorskip` lane, and audit that a bare `pip install emergentflow` gains **zero**
  new hard deps and that `emergentflow/research/` and the ingestion adapters are never eagerly
  imported.
