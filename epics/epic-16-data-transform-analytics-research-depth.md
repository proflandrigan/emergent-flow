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
- [x] **Reshape verbs.** `reshape` node covers `pivot` (long→wide) and `melt` (wide→long), the
  single biggest missing transform.
- [x] **Derive / case-when.** A `derive_column` node adds computed and conditional (case-when)
  columns via a safe expression grammar — no drop to `custom_code` for the common case.
- [x] **Row-combining verbs.** `concat` (row-wise union of ≥2 frames, schema-aligned), `deduplicate`
  (subset + keep), and `sort` nodes ship.
- [x] **String & date verbs.** A `clean_text` node (trim, case-normalize, regex extract/replace,
  split) and a `parse_dates` node (string→datetime + extract year/month/dow/quarter) close the
  "impossible without custom code" gap.
- [x] **Sampling & fuzzy join.** A `sample_rows` node (random/stratified/top-n, **seed captured**)
  and a `fuzzy_join` node (string-similarity keyed merge, `[fuzzy]` extra) ship.
- [x] **Every transform is non-mutating.** New transforms return an augmented/new frame and guard
  against silently overwriting existing columns (the `ef.timeseries` discipline), with a typed
  `CleanError` on collision. The `CleanError` hierarchy was also **retrofitted onto the nine
  pre-existing `ef.clean` ops**, so the whole family is typed — a non-breaking change, since
  `CleanError` subclasses `ValueError`.

### Analytics
- [x] **Non-parametric tests + inference plumbing.** Mann-Whitney, Wilcoxon, Kruskal-Wallis, and
  chi-square/Fisher ship as `ef.stats` ops; existing `ttest`/`anova` gain **effect sizes** (Cohen's
  d, η²) and **confidence intervals** as first-class output columns, plus a shared
  **multiple-comparison correction** (Bonferroni/BH) utility.
- [x] **Experiment analysis + power.** A `test_proportions` node (two-proportion z-test / uplift
  with CI) and a `power_analysis` node (sample-size / MDE) ship — the study-design pair researchers
  ask for constantly.
- [x] **Crosstab.** A `crosstab` node (counts + margins + chi-square), distinct from
  `group_by_aggregate`.
- [x] **Dimensionality reduction.** A `reduce_dimensions` transform (PCA/t-SNE on hard deps; UMAP
  behind `[umap]`) plus a projection scatter viz, feeding exploration/clustering/embeddings.
- [x] **Product analytics.** `cohort_retention` and `funnel` analysis nodes ship over event frames.
- [ ] **Causal inference (stretch, gated) — descoped.** Diff-in-diff + propensity-score matching on
  statsmodels; CATE/uplift behind `[causal]`. Per the epic's own Notes/Risks ("Story 15 is the most
  likely descope candidate") and the planning decision at Story group C kickoff, this is
  **deliberately deferred to a follow-up epic**, not built here. See Story 15 below.

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
> Story group B (transform verbs) is now complete — see its status blockquote below. Story
> group C (analytics depth) is the next increment and is not started.

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

## Story group B — Transform verbs (reshape, derive, combine, clean) — ✅ **COMPLETE** (Stories 5-9)

> **Group B status.** All five stories are delivered. Gates at completion: `uv run ruff check .`
> clean, `uv run ruff format --check .` clean (500 files), `uv run mypy emergentflow` clean (278
> source files), full suite **3040 passed / 23 skipped / 0 failed** (Group A finished at 2714
> passed / 23 skipped), ADR-0002 equivalence gate **303 passed / 7 skipped** (Group A finished at
> 261), and the UI gates green — `npm run lint` 0 errors, `npm run typecheck` clean, `npm test`
> **612 passed**. `scripts/check_ui_boundary.py` — OK, `ui/` imports zero `emergentflow`.
>
> **New surface:** nine new nodes (`clean.reshape`, `clean.derive_column`, `clean.concat`,
> `clean.deduplicate`, `clean.sort`, `clean.clean_text`, `clean.parse_dates`,
> `clean.sample_rows`, `clean.fuzzy_join`); seven new modules under `emergentflow/clean/`
> (`errors.py`, `reshaping.py`, `expressions.py`, `derive.py`, `combine.py`, `text_dates.py`,
> `sampling.py`); one new optional extra, `[fuzzy]`
> (rapidfuzz, MIT), documented in `docs/licensing-and-dependencies.md`, with **no new hard
> dependencies**; a new typed error hierarchy, `CleanError(ValueError)` with
> `UnknownColumnError`, `ColumnCollisionError`, `MissingOptionalDependencyError`; and a new
> equivalence harness, `tests/test_clean_transform_equivalence.py` — a 31-case matrix across all
> nine nodes, with four sweeps per case (ADR-0002 equivalence, inspectable contract, determinism,
> non-mutation) plus a coverage guard that fails if a new clean node is not added to the matrix.
>
> Story group C (analytics depth) is now complete — see its status blockquote below. Story
> group D (research & reproducibility) is also now complete — see its own status blockquote.
> Story group E (cross-cutting, testing & the payoff) is the next increment and is not started.

## Story 5 — Reshape (`pivot` / `melt`) — ✅ done
- [x] `ef.clean.reshape` wrapper with `mode="pivot"|"melt"` and the pandas-mapped params
  (index/columns/values/aggfunc for pivot; id_vars/value_vars/var_name/value_name for melt).
  Non-mutating; typed `CleanError` on duplicate-index-without-aggfunc.
- [x] `reshape` reference node + catalog; goldens for both modes; equivalence via Story 24.

> **Delivered as:** `emergentflow/clean/reshaping.py`: `reshape` with `mode="pivot"|"melt"`,
> plus `RESHAPE_MODES`/`PIVOT_AGGFUNCS` allow-lists reused as the node's `choices` hints so
> wrapper and node cannot drift. `pivot` dispatches to `DataFrame.pivot` (no `aggfunc`) or
> `pivot_table` (with one), and a duplicate index/columns combination without an `aggfunc` raises
> a typed `CleanError` naming `aggfunc` as the fix. The `clean.reshape` node.
> **Deviation:** the pivot result is **flattened** before return — `MultiIndex` columns are
> joined with `_`, the index is reset, and `columns.name` is cleared — so the output stays a
> flat, tidy, JSON-round-trippable frame rather than the MultiIndex frame pandas returns. A
> consequence worth knowing: with a list-valued `values` (e.g. `values=["amount"]`) pandas keeps
> the value level, so columns come out as `amount_clicks`/`amount_views`, not `clicks`/`views`.

## Story 6 — Derive column / case-when (`derive_column`) — ✅ done
- [x] **Safe expression grammar.** A restricted, `ast`-validated expression evaluator (arithmetic,
  comparisons, string ops, `where`/case-when over existing columns) — **no arbitrary eval**, no
  `custom_code` trust level. Reuse the `emergentflow/script/` AST-renaming discipline for wiring.
- [x] Params: ordered list of `(new_column, expression)` or `(new_column, [when/then], else)`.
  Column-overwrite guard.
- [x] `derive_column` node + catalog; goldens covering arithmetic, string, and multi-branch
  case-when; equivalence.

> **Delivered as:** `emergentflow/clean/expressions.py` (`validate_expression`, an `ast`
> allow-list) plus `emergentflow/clean/derive.py` (`derive_column`, expression and case-when
> forms, ordered so a later spec may reference an earlier derived column, first-match-wins via
> `numpy.select`, column-overwrite guard). The `clean.derive_column` node.
> **Deviation, decided in planning:** the story called for a restricted `ast`-validated
> *evaluator*. What shipped instead delegates **evaluation** to `pandas.DataFrame.eval` (with
> `engine="python"` pinned so numexpr's presence cannot change results and break the ADR-0002
> gate, and `local_dict`/`global_dict` emptied), fronted by an `ast` **pre-screen** that enforces
> the restriction. The pre-screen rejects any node type outside a literal allow-list — notably
> `ast.Call`, `ast.Attribute`, and `ast.Subscript` — and additionally requires every bare name to
> be an existing column. Because pandas' `@name` scope-escape syntax is not valid Python,
> `ast.parse` rejects it for free. The invariant the epic's risk note protects — that this must
> not become a second unsandboxed trust niche alongside `custom_code` — holds: an adversarial
> battery covering `@`-locals, `__import__`, `open()`, `globals()`, dunder/`__subclasses__` reach,
> subscripting, lambdas, and comprehensions is blocked with a typed `CleanError`.

## Story 7 — Combine & order (`concat`, `deduplicate`, `sort`) — ✅ done
- [x] `ef.clean.concat` (≥2 DataFrame inputs, schema-align, optional `keys`/`source` column);
  variadic-input node archetype. `ef.clean.deduplicate` (subset, keep first/last). `ef.clean.sort`
  (multi-key, asc/desc, na_position).
- [x] Three reference nodes + catalog entries; goldens + equivalence each.

> **Delivered as:** `emergentflow/clean/combine.py`: `concat` (≥2 frames, schema-aligned,
> optional `keys`/`source_column` provenance with a collision guard), `deduplicate` (`subset`,
> `keep="first"|"last"|"none"`), `sort` (multi-key, per-key direction, `na_position`). The
> `clean.concat`, `clean.deduplicate`, and `clean.sort` nodes — `concat` is the variadic
> archetype, reusing the `Cardinality.MANY` fan-in already proven by `recommend.compare`, so no
> new codegen machinery was needed.
> **Note on determinism:** `pd.concat(..., sort=False)` and `sort_values(..., kind="stable")` are
> both pinned deliberately. pandas' default sort is quicksort, which is not stable, so ties would
> order non-deterministically and make goldens flaky.

## Story 8 — String & date cleaning (`clean_text`, `parse_dates`) — ✅ done
- [x] `ef.clean.clean_text`: per-column pipeline of trim / lower-upper / regex extract / regex
  replace / split-to-list. Non-mutating.
- [x] `ef.clean.parse_dates`: string→datetime (format or inferred) + extract components
  (year/month/day/dow/quarter/hour) into new columns. Overwrite guard.
- [x] Two nodes + catalog; goldens + equivalence.

> **Delivered as:** `emergentflow/clean/text_dates.py`: `clean_text` (an ordered per-column
> pipeline of trim / lower / upper / title / regex replace / regex extract / split, with an
> optional `suffix` that writes to new columns instead of cleaning in place) and `parse_dates`
> (string→datetime with an optional explicit format, `errors="raise"|"coerce"`, and
> calendar-component extraction into new `<column>_<component>` columns behind a collision
> guard). The `clean.clean_text` and `clean.parse_dates` nodes.
> **Note:** the whole `operations` list is validated **before** any operation touches data, so a
> malformed pipeline cannot leave a half-cleaned frame. Text columns come back as pandas'
> nullable `string` dtype (so missing values stay `<NA>` rather than becoming the literal text
> `"nan"`); `split` is the exception, yielding object cells holding lists, ready for
> `explode_lists`.

## Story 9 — Sampling & fuzzy join (`sample_rows`, `fuzzy_join`) — ✅ done
- [x] `ef.clean.sample_rows`: `mode="random"|"stratified"|"top_n"`, `n`/`frac`, `by` for strata,
  **explicit `seed` captured** and threaded into the reproducibility block (Story 19).
- [x] `ef.clean.fuzzy_join` (`[fuzzy]`/rapidfuzz): left/right key, similarity metric + threshold,
  one-to-one vs one-to-many. Typed error on missing extra.
- [x] Two nodes + catalog; goldens + equivalence (fuzzy under a `[fuzzy]`-available lane; seed makes
  sampling deterministic).

> **Delivered as:** `emergentflow/clean/sampling.py`: `sample_rows` (`mode="random"|"stratified"|
> "top_n"`, `n`/`frac`, `by` for strata) and `fuzzy_join` (single-column string-similarity keyed
> merge, rapidfuzz scorers, threshold, one-to-one vs one-to-many via `limit`,
> `how="inner"|"left"`, similarity written to a `match_score` column). The `[fuzzy]` extra
> (rapidfuzz, MIT) with an `importlib.util.find_spec` gate that raises
> `MissingOptionalDependencyError` **before** any rapidfuzz import and before param validation,
> so a base-install user is told to install the extra rather than being handed an unrelated
> error. The `clean.sample_rows` and `clean.fuzzy_join` nodes.
> **Deviation:** the story's "explicit `seed` captured" is implemented as `seed: int = 0` — a
> concrete default rather than an optional `None`. A `None` seed would draw from the global RNG,
> so `execute` and the compiled module would return different rows and the ADR-0002 gate would
> fail. Reproducibility is therefore the default, not an opt-in. Threading the captured seed into
> a reproducibility block remains Story 18's work, as written.
> Following Story group A's precedent for `[cloud]`/`[excel]`, no dedicated CI job was added for
> `[fuzzy]`; it has an `importorskip` lane plus a monkeypatched base-install typed-error test.

---

## Story group C — Analytics depth — ✅ **COMPLETE** (Stories 10-14; Story 15 descoped)

> **Group C status.** Stories 10-14 are delivered; Story 15 (causal inference, stretch/gated) is
> **descoped** per the epic's own Notes/Risks guidance and a planning decision at kickoff — struck
> from this epic's DoD, left for a follow-up epic. Gates at completion: `uv run ruff check .`
> clean, `uv run ruff format --check .` clean (514 files), `uv run mypy emergentflow` clean (290
> source files), full suite **3155 passed / 23 skipped / 0 failed** (Group B finished at 3040
> passed / 23 skipped), ADR-0002 equivalence gate **303 passed / 7 skipped** (unchanged from
> Group B — the new nodes' `test_codegen_matches_execute` checks live in
> `tests/test_reference_nodes.py`, still real per-node ADR-0002 checks, just not yet folded into
> a `@pytest.mark.equivalence`-tagged matrix file; building that matrix for the whole new surface
> is Story 24's job in Story group E, not repeated here), and the UI gates green — `npm run lint`
> 0 errors (3 pre-existing warnings, unrelated to this work), `npm run typecheck` clean, `npm
> test` **612 passed** (unchanged — no new UI code was needed; every new result type renders via
> the canvas's existing generic DataFrame/dataclass inspector, no bespoke renderer required).
> `scripts/check_ui_boundary.py` — OK, `ui/` imports zero `emergentflow`. Contract artifacts
> regenerated: `schema/rules.json`, `ui/src/generated/{catalog.json,mutation.schema.json,
> session_event.schema.json,ir.ts,mutation.ts,session_event.ts}`.
>
> **New surface:** twelve new nodes (`stats.mann_whitney`, `stats.wilcoxon`, `stats.kruskal`,
> `stats.chi_square`, `stats.correct_pvalues`, `stats.test_proportions`, `stats.power_analysis`,
> `stats.crosstab`, `ml.reduce_dimensions`, `viz.plot_projection`, `stats.cohort_retention`,
> `stats.funnel`); three new type tokens (`CrosstabResult`, `DimensionReductionResult`,
> `CohortRetentionResult`); one new optional extra, `[umap]` (umap-learn, BSD-3-Clause),
> documented in `docs/licensing-and-dependencies.md`, with **no new hard dependencies**; a new
> `MissingOptionalDependencyError` added to `emergentflow/ml/errors.py` (mirroring the existing
> per-family pattern in `emergentflow/clean/errors.py`/`emergentflow/stats/errors.py`); and
> `TTestResult`/`AnovaResult` extended in place with `effect_size`/`ci_low`/`ci_high` fields
> (Cohen's d for `ttest`, a noncentral-F confidence interval on partial η² for `anova`, via
> Steiger's method).

## Story 10 — Non-parametric tests + inference plumbing — ✅ done
- [x] `ef.stats` gains `mann_whitney`, `wilcoxon`, `kruskal`, `chi_square` (+ Fisher exact for 2×2),
  each returning a tidy result frame (statistic, p, df, effect size where defined).
- [x] **Effect sizes + CIs on existing tests.** Extend `ttest`/`anova` output with Cohen's d / η²
  and confidence intervals. Shared `emergentflow/stats/` helper.
- [x] **Multiple-comparison correction** utility (Bonferroni/Benjamini-Hochberg) applicable to any
  p-value frame.
- [x] Reference nodes (`mann_whitney`, `wilcoxon`, `kruskal`, `chi_square`) + catalog; goldens +
  equivalence; extend the existing ttest/anova goldens.

> **Delivered as:** `emergentflow/stats/__init__.py`: `mann_whitney` (rank-biserial `r` effect
> size), `wilcoxon` (paired-sample signed-rank, no effect size — scipy's `wilcoxon` does not
> expose the z-score needed for `r = Z/sqrt(N)` without extra plumbing), `kruskal` (epsilon-squared
> effect size), `chi_square` (Cramér's V, plus Fisher's exact test — p-value and odds ratio — as
> extra columns whenever the contingency table is exactly 2×2), each a thin wrapper over the
> matching `scipy.stats` function returning a one-row tidy `DataFrame`. `TTestResult` gained
> `effect_size` (Cohen's d, pooled-variance form) with a normal-approximation CI (Hedges & Olkin);
> `AnovaResult` gained a CI on its existing partial-η² `effect_size` via a noncentral-F
> root-finding method (Steiger, 2004) — deterministic, no randomness. `correct_pvalues`
> (Bonferroni/Benjamini-Hochberg) delegates to `statsmodels.stats.multitest.multipletests` rather
> than hand-rolling the correction math, appending `p_adjusted`/`reject_null` columns to a copy of
> any p-value-bearing frame, with a column-collision guard. Four new reference nodes
> (`stats.mann_whitney`, `stats.wilcoxon`, `stats.kruskal`, `stats.chi_square`) plus
> `stats.correct_pvalues`.

## Story 11 — Experiment analysis + power (`test_proportions`, `power_analysis`) — ✅ done
- [x] `ef.stats.test_proportions`: two-proportion z-test / uplift with CI + relative lift, tidy
  output. `ef.stats.power_analysis`: sample size / MDE / achieved power (statsmodels power).
- [x] Two nodes + catalog; goldens + equivalence.

> **Delivered as:** `test_proportions` wraps `statsmodels.stats.proportion.proportions_ztest`
> (statistic/p-value) and `confint_proportions_2indep` (CI), reporting `diff`/`ci_low`/`ci_high`/
> `relative_uplift` all as **group B relative to group A** (`p_b - p_a`) — the CI call passes
> group B's counts first so its sign matches `diff` directly, rather than negating a
> group-A-relative CI. `power_analysis` is a zero-input **source** node (mirroring `load_sample`)
> wrapping `statsmodels.stats.power.TTestIndPower.solve_power`: exactly one of `effect_size`
> (MDE)/`nobs`/`power` is left `None` and solved for, the other two plus `alpha` given. The
> `stats.test_proportions` and `stats.power_analysis` nodes.

## Story 12 — Crosstab (`crosstab`) — ✅ done
- [x] `ef.stats.crosstab`: rows × cols counts, margins, normalized options, chi-square of
  independence. Distinct from `group_by_aggregate`. Node + catalog; goldens + equivalence.

> **Delivered as:** `emergentflow/stats/__init__.py::crosstab`, returning a new
> `CrosstabResult` dataclass (`table` + `chi_square`/`p_value`/`dof`/`n`) — unlike Story 10's
> four ops, this needs a real pivoted table alongside scalar test stats, so it follows the
> `AnovaResult`/`ForecastResult` dataclass pattern rather than a plain frame. The chi-square test
> always runs on the **raw**, un-margined, un-normalized contingency table regardless of the
> `normalize`/`margins` params used to shape the returned `table` — verified by a test asserting
> identical `chi_square`/`p_value`/`dof` across every `normalize` setting on the same input. The
> `stats.crosstab` node; the new `CrosstabResult` type token.

## Story 13 — Dimensionality reduction (`reduce_dimensions` + projection viz) — ✅ done
- [x] `ef.ml.reduce_dimensions` (or `ef.stats`): PCA + t-SNE on hard deps, UMAP behind `[umap]`;
  returns the reduced-coordinate frame (+ explained-variance frame for PCA). Non-mutating; seed
  captured.
- [x] A projection scatter **`PlotSpec`** viz node (reuse Epic 12 chart adapter) colored by a label
  column.
- [x] Two nodes + catalog; goldens + equivalence (UMAP under its extra lane).

> **Delivered as:** `emergentflow/ml/__init__.py::reduce_dimensions`, landing in `ef.ml` (the
> epic's first-listed option) as a **self-contained** function — it does not route through the
> `fit_estimator`/`FittedTransformer` curated-estimator seam, calling `sklearn.decomposition.PCA`/
> `sklearn.manifold.TSNE`/`umap.UMAP` directly, the same way `ef.stats.anova` calls `statsmodels`
> directly rather than a generic model-fitting seam. Returns a new `DimensionReductionResult`
> dataclass (`coordinates` + `method`/`n_components`/`seed` + `explained_variance` — populated
> only for PCA). `seed` threads into every method's `random_state` for determinism. The new
> `[umap]` extra (umap-learn, BSD-3-Clause) gates the UMAP branch behind
> `importlib.util.find_spec`, raising a new `emergentflow.ml.errors.MissingOptionalDependencyError`
> (added to that file, mirroring the existing per-family pattern) before any `umap` import.
> `ef.viz.plot_projection` is a thin convenience wrapper delegating to the existing curated
> `ef.viz.plot(chart="scatter", ...)` adapter (Epic 12) — no new chart type registered, literally
> reusing the chart allow-list as the story asks. The `ml.reduce_dimensions` and
> `viz.plot_projection` nodes; the new `DimensionReductionResult` type token.

## Story 14 — Product analytics (`cohort_retention`, `funnel`) — ✅ done
- [x] `ef.stats.cohort_retention`: cohort key + period → retention matrix (tidy + wide). `funnel`:
  ordered step columns/events → per-step conversion + drop-off frame.
- [x] Two nodes + catalog; goldens + equivalence on deterministic event fixtures.

> **Delivered as:** `cohort_retention` assigns each user to the calendar period (day/week/month,
> via `pandas.Period` arithmetic) of their earliest activity, then tracks `period_number` (periods
> elapsed since cohort start) for every period they remain active in; returns a new
> `CohortRetentionResult` dataclass pairing a long-format `tidy` retention table with a `wide`
> cohort × period-number matrix (period columns named `period_0`/`period_1`/... rather than bare
> integers, so the frame stays JSON-round-trippable). `funnel` operates over an **event log**
> (matching the bundled `transactions` sample dataset's shape — `customer_id`/`event`, built for
> exactly this) rather than boolean step columns: for an ordered list of event names, it counts
> distinct users reaching each step. **Deviation, decided in planning:** funnel counts are
> deliberately **not** temporally-ordered per user (a user counts at every step whose event they
> have, regardless of chronological order) — strict per-user event-sequencing would need a
> timestamp column and materially more complex ordering logic; the simpler "reached this step at
> some point" definition is documented explicitly in the docstring. The `stats.cohort_retention`
> and `stats.funnel` nodes; the new `CohortRetentionResult` type token.

## Story 15 — Causal inference *(stretch; gated)* — ⏭️ descoped, deferred to a follow-up epic
- [ ] **Base (statsmodels, already a dep):** difference-in-differences and propensity-score matching
  as `ef.stats` ops returning tidy effect frames with CIs.
- [ ] **Optional (`[causal]`/econml or dowhy):** CATE / uplift estimation, typed error on missing
  extra.
- [x] Ships as a parallel `emergentflow/causal/` seam **or** is explicitly deferred to a follow-up
  epic and struck from this epic's DoD — decide in planning. Nodes + catalog + goldens if kept.

> **Decided in planning:** deferred, not built. The epic's own Notes/Risks section flagged this as
> "the most likely descope candidate," and Story group C's planning discussion confirmed cutting
> it rather than adding a new `emergentflow/causal/` seam — DiD/PSM plus the optional
> econml/dowhy-backed CATE/uplift surface is substantial enough to warrant its own focused epic
> rather than being squeezed into Story group C's scope. No code, tests, or catalog entries were
> added for this story; nothing else in Story group C depends on it.

---

## Story group D — Research & reproducibility (the genuinely new product surface) — ✅ **COMPLETE** (Stories 16-21)

> **Group D status.** All six stories are delivered. Gates at completion: `uv run ruff check .`
> clean, `uv run ruff format --check .` clean (531 files), `uv run mypy emergentflow` clean (303
> source files), full suite **3226 passed / 23 skipped / 0 failed** (Group C finished at 3155
> passed / 23 skipped), ADR-0002 equivalence gate **303 passed / 7 skipped** (unchanged from
> Group C — the new nodes' `test_codegen_matches_execute` checks live in
> `tests/test_reference_nodes.py`, same precedent as Group C), and the UI gates green — `npm run
> lint` 0 errors (3 pre-existing warnings, unrelated to this work), `npm run typecheck` clean,
> `npm test` **612 passed** (one test's hardcoded `data.*` family node count bumped 10 → 11 for
> the new `load_documents` node). `scripts/check_ui_boundary.py` — OK, `ui/` imports zero
> `emergentflow`. Contract artifacts regenerated: `schema/rules.json` (three new type tokens),
> `ui/src/generated/catalog.json` (new nodes).
>
> **New surface:** eight new nodes (`research.build_report`, `research.assert_data`,
> `data.load_documents`, `stats.data_dictionary`, `clean.redact_pii` — plus the pre-existing
> `reports.generate_html_summary` absorbed as a `build_report` section input rather than
> replaced); a new `emergentflow/research/` package (`errors.py`, `lineage.py`, `report.py`,
> `reproducibility.py`, `quality.py`); three new type tokens (`Report`, `Lineage`,
> `DocumentFrame`); two new optional extras, `[docs]` (pypdf, BSD-3-Clause) and `[pii]`
> (presidio-analyzer + presidio-anonymizer, both MIT) — alongside `[report-pdf]` (weasyprint,
> BSD-3-Clause) landed with Story 16 — documented in `docs/licensing-and-dependencies.md`, with
> **no new hard dependencies**; and `emergentflow.research.errors.DataQualityError`/
> `MissingOptionalDependencyError`/`UnknownNodeError` added to that family's typed-error
> hierarchy (mirroring `emergentflow/clean/errors.py`).
>
> **Deviations, decided during implementation:**
> 1. **Report/Lineage inspector renderers in `ui/` were not built here.** Both stories named a
>    hand-written UI renderer as a bullet, but that work is explicitly Story 23's job in Story
>    group E ("`ui/` inspector renderers (Report + Lineage)") — building it here would duplicate
>    it. Group D ships the full backend surface (type tokens, pure functions, nodes, server
>    route) each renderer will consume; the canvas falls back to the existing generic
>    dataclass/DataFrame inspector in the meantime, same as every other new result type in Group
>    C needed no bespoke renderer.
> 2. **The reproducibility header lands in `export_script`'s banner, not `compile_to_code`'s
>    docstring.** `compile_to_code`'s emitted docstring (`"""Generated by Emergent Flow. Do not
>    edit by hand."""`) is asserted **exactly** by multiple existing tests across Epics 1-15
>    (`source.startswith('"""Generated by Emergent Flow. Do not edit by hand."""')`), and nearly
>    every existing golden graph contains a `data.*` loader node, so unconditionally appending a
>    reproducibility block there would have gone stale/broken dozens of unrelated golden and
>    snapshot tests outside this epic's scope. `emergentflow/codegen/export.py::export_script`
>    (the I/O-isolated edge exporter that actually writes a compiled `.py` file to disk) already
>    prepends a one-line banner ahead of the untouched `compile_to_code` output; the
>    reproducibility block is appended there instead, gated on `capture_run(graph)` actually
>    finding seeds/content-hashes, so a script exported for a graph with neither is
>    byte-identical to before. `capture_run` itself also required a real circular-import fix:
>    its lineage-walk originally imported `emergentflow.codegen.traversal` at module level,
>    which transitively pulled in every reference node (including `build_report`, which imports
>    back from `emergentflow.research`) — fixed by deferring that one import to inside
>    `trace_lineage`'s function body, breaking the cycle for both import orders.
> 3. **`load_documents` lives in `emergentflow/data/documents.py`, not `emergentflow/research/`.**
>    It is an ingestion loader parallel to `load_excel`/`load_csv`, so it follows Story
>    group A's precedent (`emergentflow/data/http/`) rather than the research package the epic
>    header's "Lives in" bullet lists for reports/lineage/reproducibility/quality specifically.
>    Its checked-in PDF fixture (`tests/fixtures/documents/sample.pdf`) is a minimal, hand-built
>    single-page PDF (raw PDF syntax, no binary dependency) rather than a vendored file, verified
>    against pypdf's real parser before committing — kept small and diff-reviewable, mirroring
>    Story 3's in-test Excel fixture rationale even though this one is checked in rather than
>    built at test time (a real multi-page PDF would need a PDF-authoring library with no
>    existing project dependency).
> 4. **`data_dictionary` lives in `emergentflow/stats/eda.py`**, alongside `profile`/`auto_eda`
>    (which it reuses directly for the type/null-rate/cardinality/range columns) rather than in
>    `emergentflow/research/` — "pairs with `auto_eda`" was read as same-module placement, not
>    just a cross-reference. `redact_pii` lives in `emergentflow/clean/pii.py`, alongside the
>    rest of the non-mutating transform family.

## Story 16 — Multi-section report builder (`build_report`) — ✅ done
- [x] **New `emergentflow/research/report.py`.** A composable builder: ordered sections, each a
  markdown block, a `PlotSpec` figure, a tidy table, or a model summary. Pure function
  `build_report(sections, meta) -> Report`; HTML render in base, PDF via `[report-pdf]`.
- [x] **New `Report` type token** (Epic 3), degrading its rendered-bytes field on the result
  payload; a **Report** inspector renderer in `ui/`.
- [x] `build_report` node with a variadic section-input archetype; export path via
  `emergentflow/codegen/export.py` (I/O at the edge). Deprecate/absorb
  `reports.generate_html_summary`.
- [x] Goldens + equivalence keyed on the structured report model (not rendered bytes).

> **Delivered as:** `Section`/`ReportMeta`/`Report` dataclasses + `build_report`/
> `section_from_value`/`sections_from_values` in `emergentflow/research/report.py`; PDF
> rendering via `render_pdf=True` (`[report-pdf]`/weasyprint, gated by
> `importlib.util.find_spec` before import). The `Report` type token registered in
> `emergentflow/types/catalog.py`; `pdf_bytes: bytes | None` degrades to
> `{"kind": "unsupported"}` on the result-payload contract automatically (the same
> `FittedStatsModel.results`-style precedent — `is_inspectable` doesn't recurse into dataclass
> fields, only checks the container is a dataclass instance). The `research.build_report` node
> (variadic `sections` IN port, `data_type="any"`, the documented wildcard token, mirroring
> `clean.concat`'s `Cardinality.MANY` archetype); `ef.research.export_report` (a second,
> independent function alongside `export_script` in `emergentflow/codegen/export.py`, importing
> `Report` only under `TYPE_CHECKING` to avoid a circular import). `reports.generate_html_summary`
> was left registered and untouched — its HTML output is auto-detected as a `"html"`-kind
> section by `section_from_value` (any string starting with `<!doctype html`/`<html`), so it
> composes into `build_report` without any code change on its side. Structural (not
> rendered-bytes) equivalence tests in `tests/test_reference_nodes.py::TestBuildReport` and
> pure-function tests in `tests/test_research_report.py`. See the Group D status note above for
> the Report inspector renderer deferral to Story 23.

## Story 17 — Data lineage / provenance (`trace_lineage`) — ✅ done
- [x] **Pure `trace_lineage(graph, node_id) -> Lineage`** in `emergentflow/research/lineage.py`:
  walks the IR DAG to return the source→transform→artifact chain (nodes, ports, op types) behind a
  target. No new schema field — computed from the existing graph (mirrors the Epic 14 "state beside
  the graph" discipline).
- [x] **`Lineage` type token** + a **Lineage** inspector tab in `ui/` (consume via generated
  catalog/contract, no `emergentflow` import). Report builder can embed a lineage section.
- [x] Server route to compute lineage for a node (stateless, carries the graph); tests for
  branching/merging DAGs.

> **Delivered as:** `LineageNode`/`LineageEdge`/`Lineage` dataclasses + `trace_lineage` in
> `emergentflow/research/lineage.py` — a visited-set backward walk over `graph.edges` from the
> target node, ordered via the existing `ef.codegen.topological_sort` (imported lazily inside the
> function body, not at module level — see the Group D status note's circular-import deviation).
> The `Lineage` type token; a stateless `POST /lineage` route (`lineage_for_node` in
> `emergentflow/server/service.py`, registered in `app.py`'s `_POST_ROUTES`, envelope shape
> `{"graph": ..., "node_id": ...}` mirroring `execute_node`). Since `Lineage` is itself a plain
> dataclass, `build_report` embeds it identically to any other model-summary section via
> `section_from_value` — no special-cased "lineage section" was needed. Branching/merging DAG
> tests (a diamond graph: shared ancestor, two branches, a two-IN-port merge node) in
> `tests/test_research_lineage.py`. See the Group D status note above for the Lineage inspector
> tab deferral to Story 23.

## Story 18 — Reproducibility capture (`capture_run`) — ✅ done
- [x] **`capture_run`** records: seeds (from `sample_rows`/`train_test_split`/stochastic ops),
  source content-hashes (reuse the LLM/warehouse content-hash keying), and resolved dep versions.
  Pure over provided inputs; version/env read quarantined to the edge.
- [x] Thread a captured `seed` through every stochastic op added in this epic; embed the
  reproducibility block into `build_report` output and as a header comment in compiled modules.
- [x] Tests: same graph + same seeds ⇒ identical capture block.

> **Delivered as:** `ReproducibilityCapture` + `capture_run(graph, *, dependency_versions=None)`
> in `emergentflow/research/reproducibility.py` — walks `graph.nodes` (sorted for determinism),
> collecting `seed`/`random_state` param values (`SEED_PARAM_NAMES`, since the epic's stochastic
> ops don't share one key) into `seeds`, and a sha256 content-hash of `(type, params)` for every
> `data.*`-typed node into `content_hashes` (the same JSON-native-sorted-keys hashing scheme
> `LLMRequest.content_hash()`/`HttpRequest.content_hash()` use). `dependency_versions` is
> recorded verbatim, never read internally — the impure edge helper
> `resolve_dependency_versions(packages)` (`importlib.metadata.version`, missing packages
> silently omitted) is called first, by the caller, keeping `capture_run` itself pure.
> `build_report` gained a `reproducibility: ReproducibilityCapture | None` param that appends it
> as a `"model_summary"` section when given. The compiled-module header landed in
> `export_script`'s banner, not `compile_to_code` — see the Group D status note's deviation #2
> for why and for the circular-import fix this story's own `capture_run` needed. Tests in
> `tests/test_research_reproducibility.py` (including the story's explicit "same graph + same
> seeds ⇒ identical capture" case) and `tests/test_codegen_export.py`.

## Story 19 — Data-quality gate (`assert_data`) — ✅ done
- [x] **`assert_data`** node: declarative expectation list (non-null, min/max range, uniqueness,
  allowed-values, regex-match, row-count delta vs upstream). Passing → passthrough frame; failing →
  typed `DataQualityError` **and** a tidy violations frame (so the canvas shows *what* failed).
  Reuse the Story 4 schema validator.
- [x] Node + catalog; goldens + equivalence for pass and fail paths.

> **Delivered as:** `emergentflow/data/contract.py::validate_schema` was refactored (behavior
> and raised-message text byte-identical) to delegate to a new, extracted
> `detect_schema_violations` — the pure detection half, returning
> `{"missing": [...], "extra": [...], "mistyped": [...]}` instead of raising. `check_data_quality`
> (`emergentflow/research/quality.py`) reuses that shared helper for its `"schema"` expectation
> type, alongside five more (`non_null`, `range`, `unique`, `allowed_values`, `regex_match`,
> `row_count` — the last supporting both static `min`/`max` and an `expected`/`tolerance`
> "delta vs upstream" form). `DataQualityError` (`emergentflow/research/errors.py`) carries the
> tidy violations frame as `exc.violations`, not just a formatted message, so a catcher gets the
> structured detail. The `research.assert_data` node raises the same typed error on both the
> `execute` and codegen-generated paths (verified by comparing `exc.violations` frames, not
> `Report.__eq__`-style comparison, since a DataFrame-valued field makes `==` raise). Goldens +
> equivalence for both pass and fail paths in `tests/test_reference_nodes.py::TestAssertData`.

## Story 20 — Document ingestion loader (`load_documents`) *(RAG loader half only)* — ✅ done
- [x] **`load_documents`**: PDF/text/markdown → tidy `(doc_id, chunk_id, text, metadata...)` frame,
  with configurable chunking (size/overlap). PDF parsing behind an optional extra
  (`[docs]`/pypdf, MIT); typed error on absence. **New `DocumentFrame` conceptual shape** (a tagged
  `DataFrame`, not embeddings).
- [x] **Explicitly no embedding/retrieval** — cross-reference Epic 11; add a note in the node doc
  pointing there.
- [x] Node + catalog; goldens on a checked-in tiny PDF/markdown fixture.

> **Delivered as:** `emergentflow/data/documents.py::load_documents(path, *, chunk_size=1000,
> chunk_overlap=100)` — a single file or a directory (every `.pdf`/`.txt`/`.md`/`.markdown`
> file inside it, sorted for determinism) chunked via a dependency-free sliding-window character
> splitter, returning `(doc_id, chunk_id, chunk_index, text, source_path, char_count)` rows.
> PDF text extraction (`pypdf.PdfReader`) is gated behind `[docs]`, checked via
> `importlib.util.find_spec` before import. Re-exported as `ef.data.load_documents`; the new
> `DocumentFrame` type token registered. The `data.load_documents` node (a zero-input source
> node like `load_excel`, `cacheable = False` since it re-reads the filesystem). See the Group D
> status note's deviation #3 for the checked-in-fixture rationale
> (`tests/fixtures/documents/sample.pdf` + `sample.md`). Goldens in
> `tests/test_reference_nodes.py::TestLoadDocuments`, including a codegen/execute equivalence
> check on the PDF fixture that verifies the typed-error path when `[docs]` is absent and the
> real parse when it's present.

## Story 21 — Data dictionary / codebook (`data_dictionary`) + PII redaction (`redact_pii`) — ✅ done
- [x] **`data_dictionary`**: per-column type, null rate, cardinality, range/top-values, optional
  user notes → tidy frame + a report-ready section. Pairs with `auto_eda`.
- [x] **`redact_pii`**: regex-based detection + masking (email, phone, SSN-like, credit-card-like) in
  base; presidio behind `[pii]` for NER-based detection. Positioned to run right after ingestion.
- [x] Two nodes + catalog; goldens + equivalence.

> **Delivered as:** `emergentflow/stats/eda.py::data_dictionary` reuses `profile` for the
> type/null-rate/cardinality/range columns, adding `top_values` (a JSON-native list of
> `{"value", "count"}` dicts per column, most frequent first) and a caller-supplied `notes`
> column. `emergentflow/clean/pii.py::redact_pii` defaults to `engine="regex"` (four
> best-effort patterns: `email`/`phone`/`ssn`/`credit_card`) and supports `engine="presidio"`
> (NER-based, `[pii]` extra — presidio-analyzer + presidio-anonymizer, gated by
> `importlib.util.find_spec` before import, with the four category names mapped to presidio's
> own entity names via `PRESIDIO_ENTITY_MAP`). Neither presidio nor its spaCy model dependency
> is installed in this environment; the presidio success path is covered by monkeypatching fake
> `presidio_analyzer`/`presidio_anonymizer` modules into `sys.modules`
> (`tests/test_clean_pii.py`), the same technique Story 16's `render_pdf=True` test used for
> weasyprint. The `stats.data_dictionary` and `clean.redact_pii` nodes; goldens + equivalence in
> `tests/test_reference_nodes.py` (`TestDataDictionary`, `TestRedactPii`) and
> `tests/test_clean_pii.py`.

---

## Story group E — Cross-cutting, testing & the payoff — ✅ **COMPLETE** (Stories 22-25)

> **Group E status.** All four stories are delivered; with them the epic is complete. Gates at
> completion: `uv run ruff check .` clean, `uv run ruff format --check .` clean (534 files),
> `uv run mypy emergentflow` clean (303 source files), full suite **3287 passed / 24 skipped /
> 0 failed** (Group D finished at 3226 passed / 23 skipped — the one new skip is Story 25's
> `render_pdf=True` lane, which `importorskip`s weasyprint), ADR-0002 equivalence gate **336
> passed / 7 skipped** (up from 303 — Story 24's new matrix file is the whole of that delta), and
> the UI gates green — `npm run lint` 0 errors (3 pre-existing warnings, unrelated to this work),
> `npm run typecheck` clean, `npm test` **631 passed** (up from 612: 8 `ReportView` + 9
> `LineagePanel` + 2 `Inspector` tab tests). `scripts/check_ui_boundary.py` — OK, `ui/` imports
> zero `emergentflow`. Contract artifacts regenerated: `schema/rules.json` (now carrying the
> catalog's first explicit subtype edge); `ui/src/generated/*` regenerated **byte-identical**,
> since neither the IR schema nor any node's spec changed in this group.
>
> **New surface:** no new nodes and no new type tokens — Group E is the cross-cutting layer over
> what Groups A-D built. It adds one subtype edge (`DocumentFrame <: DataFrame`), two `ui/`
> components (`ui/src/inspector/ReportView.tsx`, `ui/src/inspector/LineagePanel.tsx`) plus a fifth
> Inspector tab, and four test modules — `tests/test_epic16_equivalence_matrix.py` (33 tests),
> `tests/test_epic16_optional_extras.py` (13), `tests/test_epic16_acceptance_demos.py` (8 + 1
> skipped), and the new `TestEpic16TypeWiring` class in `tests/test_type_catalog.py` (7) — plus
> the three committed demo pipelines under `examples/epic16_acceptance_demos/`.
>
> **Defects found and fixed while closing the group:**
> 1. **`pyproject.toml`'s `[all]` extra was stale.** It listed 11 of the 17 defined extras,
>    silently omitting `recommend`, `fuzzy`, `umap`, `report-pdf`, `docs`, and `pii` — so
>    `pip install emergentflow[all]`, documented in its own comment as installing "every optional
>    extra in one shot", had not actually done so since Epic 15. Fixed, `uv.lock` regenerated (the
>    diff touches only the `all` extra; zero new hard dependencies), and
>    `test_all_extra_lists_every_optional_extra` now diffs the two lists so it cannot drift again.
> 2. **Four of Epic 16's seven optional extras had no base-install typed-error test.** `cloud`,
>    `fuzzy` and `excel` had one; `docs`, `pii`, `report-pdf` and `umap` did not, so a regression
>    turning one of those typed errors back into an opaque `ImportError` would have shipped
>    silently. All four now have a lane, plus a matching "the default path still works without the
>    extra" test.
> 3. **`LineagePanel` rendered raw port ids instead of port names** (caught in the group's final
>    review pass). The `/lineage` DTO's `source_port`/`target_port` are port **ids** —
>    `emergentflow/research/lineage.py:133` fills them from `edge.source.port_id`, since the IR
>    keys edges by id — not the `"frame"`-style names the panel was displaying verbatim. The hop
>    line therefore read `port:a1b2… → port:d4e5…` on a real graph. The panel now resolves each id
>    back through the graph store's node/port shape (`label ?? name ?? id`, so a port deleted
>    since the trace degrades to its id rather than rendering blank). The original test passed
>    only because its hand-written fixture used `"frame"` as the port value; it has been replaced
>    with one that mints real port ids via `addNodeFromSpec` and asserts neither id leaks into the
>    UI, plus a companion test for the deleted-port fallback.
>
> **Deviations, decided during implementation:**
> 1. **The Lineage renderer is a fifth Inspector tab that fetches `POST /lineage`, not a Results-area
>    payload renderer.** Story 23 places it "in the Inspector Results area", but the Results area
>    renders node OUT-port payloads and **no node emits `data_type="Lineage"`** — lineage is
>    computed on demand by the stateless route Story 17 built. A payload renderer would therefore
>    have had nothing to render. `LineagePanel` mirrors `CodePanel.tsx`'s debounced-fetch structure
>    exactly and works for any selected node with no prior run, which is strictly more useful.
>    The **Report** renderer *is* a Results-area payload renderer as specified, dispatched from
>    `PayloadView`'s `"record"` case on `payload.type === "Report"`.
> 2. **`DocumentFrame <: DataFrame` is the built-in catalog's first explicit subtype edge.** Story
>    22's "a `DocumentFrame` wires where a `DataFrame` does" cannot hold in a flat catalog: exact
>    match and wildcard were the only paths to COMPATIBLE, so `load_documents → redact_pii` was
>    INCOMPATIBLE (a red edge on the canvas). Declaring `supertypes=("DataFrame",)` fixes it in
>    the one direction that is sound — a plain `DataFrame` still cannot feed a `DocumentFrame`
>    port. `Report` and `Lineage` deliberately gained **no** supertype (a `Report` must not reach a
>    frame consumer; a `Lineage` is inspect-only), so the flat-catalog test was renamed to
>    `test_builtin_catalog_has_exactly_one_declared_subtype_edge` and now asserts that exact edge
>    set. The research demo's `test_research_demo_validates` asserts
>    `edge_compatibility["e-docs-dict"] is True` by name as the standing regression guard.
> 3. **The north-star demo composes its lineage + reproducibility block at the `ef.research` API
>    level, not declaratively in the graph.** The `research.build_report` **node** exposes no
>    `reproducibility` param (only the `build_report` Python function does), so a canvas-built
>    graph cannot attach the block; adding one would be a node-contract change beyond Story 25's
>    scope. `test_north_star_report_embeds_lineage_and_reproducibility` demonstrates the full
>    composition and documents the limitation.
> 4. **Story 24's matrix uses the node-level `preview()`/`exec` seam, not `assert_equivalent`.**
>    `tests/test_codegen_equivalence.py::assert_equivalent` spawns a real subprocess per graph
>    (180s timeout); across 31 nodes that would have made the file minutes long. The matrix uses
>    the same in-process `_run_codegen` seam as `tests/test_recommend_equivalence_matrix.py`
>    (Epic 15 Story 13) and compares artifacts with a recursive comparator that descends into
>    dataclass fields — necessary because `CrosstabResult`/`CohortRetentionResult`/
>    `DimensionReductionResult`/`Report` all carry DataFrame fields, so a bare `==` raises
>    "truth value of a DataFrame is ambiguous". The per-node `test_codegen_matches_execute` tests
>    in `tests/test_reference_nodes.py` were left in place; the matrix is additive, and adds a
>    `test_every_epic16_node_is_covered` guard so a future Epic-16-family node cannot silently
>    escape it.
> 5. **"Replay fixtures for every `requires_client` ingestion node" is two nodes.** `data.http_fetch`
>    and `data.load_google_sheet` are the only ingestion nodes in this epic that take a client
>    (`ClientKind.HTTP`); both are covered by `ReplayHttpClient` in the matrix. The other
>    `requires_client` nodes in the repo (`llm_call`, `eval_run`, `eval_judge`, `embed_text`) are
>    not ingestion nodes and predate this epic.
> 6. **The committed demo graphs carry repo-relative data paths.** An absolute path would bake the
>    authoring machine's home directory into a checked-in artifact and break the demo for every
>    other checkout, so the pipelines store e.g.
>    `examples/epic16_acceptance_demos/sales/sales_*.csv` and the test module has an autouse
>    `monkeypatch.chdir(REPO_ROOT)` fixture — the same contract
>    `tests/test_data_connectors_acceptance_demo.py` gets by passing `cwd=REPO_ROOT` to its
>    compiled subprocess.
> 7. **The demo graphs' node *and port* ids are derived, not minted.** `NodeDefinition.instantiate`
>    assigns a fresh UUID per port — correct for a live canvas, wrong for a graph committed to
>    `examples/`, because every `uv run pytest` would rewrite all three pipeline JSONs with new
>    ids and dirty the working tree. `_make` therefore overwrites each port id with
>    `<node id>:<direction>:<port name>` (`Port.id` is a plain `str`, no UUID constraint), which
>    also makes the committed files readable. `test_committed_pipelines_are_byte_stable_across_runs`
>    asserts two builds of each demo serialize identically, so the churn cannot come back.
> 8. **The transform demo's two fixture CSVs are regenerated, not committed.** `.gitignore:98`
>    ignores `*.csv` repo-wide, so `examples/epic16_acceptance_demos/sales/*.csv` cannot be
>    checked in without a deliberate `git add -f` overriding that policy — which was left as the
>    repo owner's call rather than taken unilaterally. `_write_transform_fixtures()` recreates
>    them on every test run, so CI and any local `uv run pytest` are unaffected; only a fresh
>    checkout that opens `transform_pipeline.json` on the canvas *before* running the suite will
>    see an unresolved glob. The other two demos' fixtures (the HTTP replay JSON and the markdown
>    corpus) are committed normally.

## Story 22 — Type tokens, catalog & contract regeneration — ✅ done
- [x] Register `Report`, `Lineage`, `DocumentFrame` tokens with Epic 3 compatibility rules (a
  `Report` wires into an export/inspect node but not a `DataFrame` consumer; a `Lineage` is
  inspect-only; a `DocumentFrame` wires where a `DataFrame` does plus into `load_documents`
  consumers).
- [x] Regenerate `ui/src/generated/*` (`scripts/export_ui_contracts.py`), `ui/src/generated/ir.ts`
  (`npm run gen:types`), and verify `scripts/check_ui_boundary.py`.

> **Delivered as:** the three tokens were already *registered* by Group D, so this story's real
> work was the **compatibility semantics**. `DocumentFrame` gained `supertypes=("DataFrame",)` in
> `emergentflow/types/catalog.py`; `Report` and `Lineage` gained wiring-intent prose but no
> supertype (see deviation #2 above for why that is the correct reading of the story). The seven
> `TestEpic16TypeWiring` tests in `tests/test_type_catalog.py` pin every direction of all three
> tokens through `is_compatible`. `schema/rules.json` was regenerated via
> `python -m emergentflow.types.rules_artifact` and now carries
> `"subtypes": [["DocumentFrame", "DataFrame"]]`; `scripts/export_ui_contracts.py` and
> `npm run gen:types` were re-run and produced byte-identical output (no IR-schema or node-spec
> change in this group); `scripts/check_ui_boundary.py` is OK.

## Story 23 — `ui/` inspector renderers (Report + Lineage) — ✅ done
- [x] A **Report** renderer (renders the composed HTML) and a **Lineage** tab (renders the
  source→artifact chain) in the Inspector Results area, consuming only generated contracts. Vitest
  coverage; eslint/tsc gates.

> **Delivered as:** `ui/src/inspector/ReportView.tsx` — dispatched from `PayloadView`'s `"record"`
> case when `payload.type === "Report"`, rendering the meta header, a section index, and the
> composed HTML in the same `sandbox="allow-scripts"` iframe the existing `"html"` payload branch
> uses. It deliberately **suppresses** the `sections` field's `"unsupported"` blob (the payload
> contract cannot JSON-serialize a list of `Section` dataclasses, so it degrades to a Python
> `repr`) and never renders `pdf_bytes`' repr, showing a "PDF rendered" note instead.
> `ui/src/inspector/LineagePanel.tsx` — a debounced `POST /lineage` fetch mirroring
> `CodePanel.tsx`, wired as a fifth `Segmented` tab in `Inspector.tsx` (see deviation #1 for why a
> tab rather than a Results renderer). Both are pure of `emergentflow` imports; `LineagePanel`
> declares the `Lineage` DTO shape locally with runtime type guards, since the generated contracts
> do not cover it, and resolves the DTO's port **ids** back to display names against the graph
> store (see defect #3 above). 19 new vitest cases; `npm test` 612 → **631 passed**,
> `tsc --noEmit` clean, eslint 0 errors.

## Story 24 — Equivalence & golden testing at scale — ✅ done
- [x] Extend the parametrized equivalence harness to cover the full new node matrix, keyed on each
  node's **inspectable** output (frames/reports/lineage), with fixed seeds and replay fixtures for
  every `requires_client` ingestion node. Gate in CI beside the existing `-m equivalence` gate.
- [x] Ensure the offline discipline: no ingestion node touches the network in CI; every optional
  extra has an `importorskip` lane and a base-install typed-error test.

> **Delivered as:** `tests/test_epic16_equivalence_matrix.py` — `pytestmark =
> pytest.mark.equivalence`, so it joins the existing `-m equivalence` gate directly (**303 → 336
> passed**). 27 parametrized cases over the pure nodes, 4 standalone cases for the file/client
> nodes (`load_excel` behind `importorskip("openpyxl")`, `load_documents` on the checked-in
> markdown fixture, `http_fetch` and `load_google_sheet` under `ReplayHttpClient` with
> `tmp_path`-scoped fixtures), and 2 completeness guards asserting the covered set equals all 31
> node types Epic 16 added. Fixed seeds throughout (`sample_rows` seed 42, `reduce_dimensions`
> seed 0, `build_report`'s `generated_at` passed explicitly so the rendered HTML is
> deterministic). See deviation #4 for the harness-altitude choice and #5 for the client-node
> scope. `tests/test_epic16_optional_extras.py` covers the second bullet: four new base-install
> typed-error lanes plus their default-path twins, the `[all]` audit, a no-optional-package-is-a-
> hard-dep assertion, and two offline guards — that both HTTP ingestion nodes raise
> `MissingHttpClientError` with no injected client, and that `emergentflow/data/http/fetch.py`'s
> source text imports no networking library (`urllib.request` lives only in the injected
> `live.py` client). The base-install lanes monkeypatch `importlib.util.find_spec` rather than
> using `importorskip`, so they run on **every** install including one where the extra is present
> — `importorskip` would have made the lane vanish in the dev venv, the opposite of the intent.

## Story 25 — Wire into the canvas + acceptance demos — ✅ done
- [x] **North-star demo:** `http_fetch (replay) → parse_dates → derive_column → assert_data →
  test_proportions → build_report (with lineage + reproducibility block)` builds on the canvas,
  compiles to `.py`, and executes end-to-end.
- [x] **Transform demo:** `load (glob) → clean_text → reshape (melt) → group_by_aggregate →
  crosstab → viz` end-to-end.
- [x] **Research demo:** `load_documents → data_dictionary → redact_pii → build_report (PDF)`
  end-to-end (under the relevant optional-extra lanes).

> **Delivered as:** `tests/test_epic16_acceptance_demos.py` builds all three graphs, writes them to
> `examples/epic16_acceptance_demos/` as committed IR JSON, validates each (zero error
> diagnostics, every edge `edge_compatibility: True`), and proves each both `execute()`s and
> compiles to a module whose `main()` runs. Nodes are built via `NodeDefinition.instantiate`
> rather than the hand-written `Port(...)` literals
> `tests/test_data_connectors_acceptance_demo.py` uses — same result, far less to get wrong.
> Committed fixtures make the demos runnable: a content-hash-keyed HTTP replay fixture under
> `http_fixtures/`, two monthly CSVs under `sales/` (so the transform demo's glob really matches
> multiple files), and a small markdown corpus with a planted email address under `documents/`
> (so `redact_pii` has something to redact). The transform demo's DAG deliberately **branches** at
> the melt node into both `group_by_aggregate → viz` and `crosstab`. The research demo's first
> edge is the `DocumentFrame → DataFrame` regression guard described in deviation #2, and its PDF
> lane is `importorskip("weasyprint")` — the epic's one new skip. See deviations #3 (the
> reproducibility block) and #6 (repo-relative paths).

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
