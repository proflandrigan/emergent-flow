# Epic 13 — Data Connectors, Warehouses & SQL (the analyst's front door)

> **Repo ↔ roadmap numbering.** Epic files are numbered by **delivery order in this repo**; the
> [technical roadmap](../planning_docs/technical_roadmap.md) numbers epics **globally**. This file
> is repo **Epic 13**. It delivers the bundled / local happy-path slice of **roadmap Epic 9 — Data
> Connectors & Credential Management** (`planning_docs/technical_roadmap.md` §"Epic 9"): a connector
> framework, a first set of SQL/warehouse connectors (DuckDB, BigQuery, Redshift, Postgres), and
> secrets-out-of-the-IR credential handling. The *premium / managed* connectors and the managed
> per-workspace secret store stay **(hosted)** and out of scope here (roadmap §A6).
> **Always qualify "repo Epic N" vs "roadmap Epic N"** — see [`epics/README.md`](./README.md).

> **We borrow ADR-0017's central bet, and apply it to a second effect type.** Epic 9 (repo) proved
> that a non-deterministic, credentialed, network-I/O node can live inside a product whose whole
> value rests on two **pure** functions over one IR — by **quarantining the effect behind an injected
> client seam** (`LLMClient`, [ADR 0017](../docs/adr/0017-llm-nodes-injected-effectful-client.md)).
> A warehouse query is the *same shape of problem*: same inputs can yield different rows, it touches
> the network, it costs money (bytes scanned), and it depends on secrets. So we do **not** invent a
> new mechanism — we introduce a **`WarehouseClient`** protocol injected exactly the way `LLMClient`
> is, a **`ReplayWarehouseClient`** (content-addressed fixtures) that keeps the ADR-0002 equivalence
> gate value-exact without ever touching a warehouse, and a **secret-free connection reference** that
> generalizes ADR-0017's `api_key_env` rule (the IR carries a *profile name*, never a credential).
> This epic then reuses **two more moves the repo already proved**:
> - **Visual SQL is the Epic-12 "structured params over formula strings" move applied to SQL.** The
>   query-builder node takes a structured spec (`source` / `select[]` / `where[]` / `join[]` /
>   `group_by[]` / `order_by[]` / `limit`); a **single wrapper** compiles it to dialect-specific SQL
>   via **`sqlglot`** — one place, tested once — so `codegen` and `execute` can never build the SQL
>   differently and ADR-0002 holds by construction. (Formula-string / raw-SQL entry is *also* shipped,
>   as its own node — the roadmap's decided escape hatch — not as the only door.)
> - **Warehouse breadth is delivered as data, not N node files** (the Epic 8 / Epic 12 bet). One
>   dialect-agnostic query archetype + a **per-dialect adapter** + a **generated connector catalog**
>   covers DuckDB / BigQuery / Redshift / Postgres; the dialect lives in the connection profile and
>   the injected adapter, so adding a warehouse is an adapter + a catalog row, not a new node.

**Phase:** Follows repo Epic 9 (the `LLMClient` injected-client seam + `ReplayClient` + secrets-by-
env-var-name discipline this epic generalizes), repo Epic 6 (the `ef.data` seam, `load_csv`/`load_
parquet` source-node precedent, catalog-as-data export, `@public_op` inspectable contract), and repo
Epic 12 (the analyst surface — stats/viz/EDA — that warehouse data flows *into*; this epic is the
front door that fills the canvas with real data). Sequenced so a fitted model or a chart from Epic 12
can be built directly on a `SELECT` against production, not just a bundled sample CSV.
**Lives in:** `emergentflow/` — the SDK tree owns the connector framework (`emergentflow/data/warehouse/`),
the `WarehouseClient` seam + replay/adapter clients, the `ef.data.query` wrapper, the query nodes
(`emergentflow/nodes/`), the generated connector catalog, and the connection-profile store. The
canvas (`ui/`, repo Epic 5) **only consumes** the generated catalog + rules and renders the connection
manager, schema browser, and visual-builder panels from catalog/schema data — **no per-warehouse or
per-query-shape UI is hand-written here**.
**Dependencies:** Epic 1 (node contract, param schema, registry, `@register`), Epic 2
(`compile_to_code` / `execute` + the golden/equivalence harness), Epic 3 / roadmap 5 (type tokens +
rules-as-data so a `connection`-ref param and the query output `DataFrame` validate), Epic 6 (the
`ef.data` seam; catalog-as-data export; `@public_op`), **Epic 9 / [ADR 0017](../docs/adr/0017-llm-nodes-injected-effectful-client.md)**
(the injected-client seam + `ReplayClient` + secrets-by-env-var-name — the load-bearing precedent),
and Epic 6-hosted's sandbox-egress note (connector network egress overlaps sandbox policy — roadmap
§Epic 9 risk). New deps: **`sqlglot` (MIT)** as a hard dep (dialect parse / transpile / read-only
validation / structured-spec→SQL compilation) and **`duckdb` (MIT)** as a hard dep (the in-process,
credential-free warehouse — a real feature *and* the offline fixture-recording backend); warehouse
drivers ship **only as optional extras** — `emergentflow[bigquery]` (`google-cloud-bigquery`,
Apache-2.0), `emergentflow[redshift]` (`redshift-connector`, Apache-2.0), `emergentflow[postgres]`
(SQLAlchemy MIT + a permissive driver) — never in the base install.
**Blocks:** raises the ceiling of repo Epic 12 (real warehouse data → stats/viz/EDA) and the roadmap
Epic 12 NL→graph agent (an analyst can say "regress revenue on region from the `sales` table" and the
agent has a query node + a schema to target). Fills the "no real data source" gap in
[`planning_docs/jupyter-replacement-path.md`](../planning_docs/jupyter-replacement-path.md).

---

## Definition of Done (epic-level)

- [ ] **The injected-client seam is generalized to a second effect, not forked.** A `WarehouseClient`
  protocol (`run(QueryRequest) -> QueryResult`, plus introspection) is injected exactly as `LLMClient`
  is; `execute` and the compiled module's entry point resolve it through a **single client bundle**
  (not a growing pile of positional `client=` params), and graphs with **no** warehouse nodes behave
  exactly as before. ADR-0002 stays one value-exact gate, now parametrized by *two* injectable
  clients. Captured in **[ADR 0018](../docs/adr/0018-data-source-connector-seam.md)** (new).
- [ ] **Secrets never enter the IR or the emitted code.** A graph references a warehouse by a
  **connection-profile name** (`connection="warehouse_prod"`); credentials live in a **local**
  profile store (a `connections.toml` / OS keyring, roadmap §Epic 9), resolved from the environment /
  keyring **at call time inside the effectful client only**. The compiled module reads a profile name
  and resolves credentials at run time; no host, token, key, or DSN is ever serialized, logged, or
  committed — the ADR-0017 `api_key_env` rule generalized. A pre-flight check (the `secrets.py` analog)
  fails fast with a typed error naming the *missing profile / env var*, never a value.
- [ ] **Two query nodes, both routing one wrapper:** a **raw-SQL** node (`data.sql_query`: a SQL
  string + `connection` → `DataFrame`) — the roadmap's decided raw-SQL escape hatch, shipped
  unsandboxed on the local happy path (Jupyter trust model) and clearly marked un-validated — and a
  **visual query builder** node (`data.query_builder`: structured `source`/`select`/`where`/`join`/
  `group_by`/`order_by`/`limit` spec → `DataFrame`) whose wrapper compiles the spec to dialect SQL via
  `sqlglot`. Both `codegen` and `execute` route through the same `ef.data.query(...)` wrapper → ADR-
  0002 by construction.
- [ ] **Warehouse breadth is a generated catalog over one archetype + per-dialect adapters:** DuckDB
  (bundled, in-process), BigQuery, Redshift, and Postgres are reachable through **dialect-agnostic**
  query nodes; the dialect lives in the connection profile + an injected `WarehouseAdapter`, and the
  connector list is a **generated, curated, version-pinned catalog** — **not** one node file per
  warehouse. Adding a warehouse is an adapter + a catalog row.
- [ ] **The inspectable contract holds:** every query node returns a `QueryResult` carrying a **tidy
  `DataFrame`** plus JSON-native metadata (`row_count`, column schema, `bytes_scanned`, `cost_usd`
  estimate, `dialect`, `truncated`, `elapsed_ms`); introspection returns tidy schema frames. A live
  DB connection / cursor / driver object is **never** returned from a node or dumped into a payload.
- [ ] **Query safety & cost governance are first-class, at the effect edge only:** **read-only by
  default** (statement allow-list enforced by parsing with `sqlglot` — `SELECT`/`WITH` only unless the
  profile opts into writes), **row + byte caps** (`LIMIT` injection; BigQuery `maximum_bytes_billed`),
  a **`dry_run` cost estimate** (bytes scanned) *before* a query spends, and a **timeout** — all
  configured on the profile / node params and enforced **inside the client**, never inline in the pure
  core. Typed errors on violation.
- [ ] **ADR-0002 holds by construction & is proven at scale:** `codegen` and `execute` route through
  the same `ef.data.query` wrapper; both stay **pure** (no I/O, no `os.environ`, no socket — the
  effect is the injected client). A **parametrized equivalence harness** proves `execute(ir)` ≈ running
  `compile_to_code(ir)` over the **dialect × query-shape** matrix under a shared
  `ReplayWarehouseClient` (fixtures content-addressed by `QueryRequest.content_hash()`), keyed on the
  result frame + the compiled-SQL string, gated in CI alongside the existing gate — **CI never touches
  a real warehouse.** DuckDB is the offline fixture-recording backend.
- [ ] **The visual builder's SQL compilation is deterministic and golden-tested per dialect:** a given
  structured spec compiles to a **stable, dialect-specific SQL string** (BigQuery vs Redshift vs
  Postgres vs DuckDB), pinned by golden tests — the highest-leverage test surface in the epic.
- [ ] **Schema discovery is a real feature, through the seam:** list databases/schemas/tables and
  describe columns/types via client introspection methods (also replayable), surfaced as tidy frames
  and as a **design-time schema-browser API** the server/UI calls to power the builder's pickers and
  the "`df.<TAB>` discoverability" gap — not inline in `execute`/`codegen`.
- [ ] **New type tokens / param kinds registered** (`ConnectionRef` param kind; a `Schema` token for
  introspection frames) with Epic 3 rules; the query output is a **`DataFrame`** so it flows into the
  entire existing analyst surface (Epic 6 transforms, Epic 8 ML, Epic 12 stats/viz/EDA) for free.
- [ ] **License hygiene:** sqlglot (MIT), duckdb (MIT), google-cloud-bigquery (Apache-2.0),
  redshift-connector (Apache-2.0), SQLAlchemy (MIT) are all clean; **no GPL / no copyleft driver on
  the hard-dep path** — call out that **psycopg2/psycopg3 are LGPL** and are therefore an *optional*
  `[postgres]` extra (not a base dep), and that all warehouse drivers are extras so the base install
  is credential-free and light (`docs/licensing-and-dependencies.md`, same rigor as the `[bayes]` note).
- [ ] **Acceptance demos (Story 11):** (a) an **exploration** flow — `sql_query (DuckDB over a local
  parquet fixture) → describe → correlation heatmap` — and (b) a **warehouse→stats** flow —
  `query_builder (join + group_by, compiled to BigQuery SQL) → MixedLM → coefficient/forest plot` —
  both build on the canvas, compile to `.py`, and execute end-to-end under the replay client.
- [ ] **Explicitly out of scope:** writes / DML / DDL & table materialization (dbt-style `CREATE TABLE
  AS`), a full dbt integration, streaming / CDC sources (Kafka), an ORM layer, warehouse
  admin/provisioning, **pushdown** of graph computation into SQL (v1 **pulls** the query result into
  the engine — pushdown is a later performance epic, roadmap §Epic 9 note), cross-source federated
  joins, the **managed / premium connectors + managed secret store** (hosted, roadmap §A6), and a
  cloud object-store connector (S3/GCS blobs — a sibling connector, its own slice).

---

## Story group A — Foundations (the load-bearing seams)

## Story 1 — Lock the connector architecture (ADR 0018 + design note)

> Cheap to decide, expensive to retrofit across four dialects and the credential boundary. Unlike
> Epic 12, this **does** warrant an ADR — it extends the injected-client *contract* to a second effect
> type and introduces the connection-profile / secret-store boundary, both cross-cutting. Write
> **ADR 0018** (`docs/adr/0018-data-source-connector-seam.md`) and a design note
> (`docs/data-connectors-design.md`) before building.

- [ ] **Generalize the injected-client seam (the load-bearing decision).** Today `requires_client:
  bool` implies *the LLM client*, and the executor / compiled `main()` thread exactly one `client`.
  Decide how a node declares **which** effect it needs now that there are two. Record the trade-off
  and recommend a **client bundle**:
  - **(rejected) a second boolean `requires_warehouse` + a second `warehouse=` param** — simple but
    doesn't scale to Epic 11's vector store or a future object-store client; forks the threading N ways.
  - **(recommended) a `Clients` bundle** carrying `.llm` and `.warehouse` (extensible), threaded as a
    single `clients=` through `execute(graph, *, clients=...)` and the compiled `main(clients=...)`.
    Nodes declare a **capability set** (e.g. `requires = frozenset({ClientKind.WAREHOUSE})`); the
    executor resolves each from the bundle. **Back-compat is a hard requirement:** the existing
    `execute(graph, *, client=...)` and `requires_client` boolean keep meaning *the LLM client* (a
    shim maps them onto the bundle), so every Epic 9 LLM node and its tests are untouched, and graphs
    with no warehouse nodes behave identically. Note the threading obligation through the server
    (Epic 7) and CLI — the same "grows a client param" consequence ADR-0017 already flagged.
- [ ] **`WarehouseClient` mirrors `LLMClient` (don't invent a new pattern).** One protocol:
  `run(request: QueryRequest) -> QueryResult`, plus introspection (`list_relations`,
  `describe_relation`) and a `dry_run(request) -> CostEstimate`. Building the `QueryRequest` from node
  inputs is **pure**; running it is the **only** effect and lives entirely inside the client — exactly
  ADR-0017 §Decision. Three implementations ship (Story 2/6): `ReplayWarehouseClient` (pure, default in
  tests + the gate), `DuckDBWarehouseClient` (in-process, credential-free — real feature + fixture
  recorder), and `AdapterWarehouseClient` (effectful, dispatches to a per-dialect adapter).
- [ ] **Secrets stay out of the IR — the `api_key_env` rule, generalized.** The IR carries a
  **connection-profile name** only. A `ConnectionProfile` is a named, serializable, **secret-free**
  descriptor (dialect; connection coordinates — BQ project/dataset/location, Redshift host/port/db;
  auth *method* + credential *references* — env-var names / keyring handle / ADC; default limits) kept
  in a **local** store outside the IR (`~/.config/emergentflow/connections.toml` and/or OS keyring,
  roadmap §Epic 9). The effectful client resolves credentials from env/keyring at call time; nothing
  secret is serializable within the pure core's reach. Record why (the IR gets exported to Git and
  shared — roadmap §Epic 9 secrets risk).
- [ ] **Structured spec over SQL string — but the backend wants SQL.** The builder interface is
  structured; a single wrapper compiles it to dialect SQL via `sqlglot` (Epic-12's formula-inside-the-
  wrapper rule, applied to SQL). Keep compilation in **one** place so `codegen`/`execute` never diverge.
  The raw-SQL node is *also* shipped (the roadmap's decided escape hatch) — record both doors and why.
- [ ] **Breadth-as-data + dialect adapters.** One query archetype; a `WarehouseAdapter` per dialect; a
  **curated, version-pinned** generated connector catalog (Epic 8 catalog-curation invariant — do not
  reflect over "every driver installed"). `sqlglot` transpilation lets one compiled spec target any
  dialect. Record the pull-not-pushdown decision (v1 pulls results; pushdown deferred).
- [ ] **Optional-extras dependency boundary (the `[bayes]` discipline).** `sqlglot` + `duckdb` are hard
  deps; every cloud driver is an extra (`[bigquery]`/`[redshift]`/`[postgres]`). Base install absent-
  import of a driver → typed `MissingOptionalDependencyError("emergentflow[bigquery]")`, never an
  opaque `ImportError`. Add a test that imports the whole package with all drivers absent.
- [ ] **Safety defaults, decided up front.** Read-only by default (sqlglot statement allow-list); row +
  byte caps; `dry_run` before spend; query timeout — enumerate the defaults and where each is enforced
  (always the client edge). Record the sandbox-egress overlap (roadmap §Epic 9 / Epic 6-hosted).

## Story 2 — Inspectable representations + the `ef.data.query` wrapper seam (`emergentflow/data/warehouse/`)

> The load-bearing seam: get it right and every query node + every dialect inherits ADR-0002
> equivalence and the `@public_op` inspectable contract — the Epic 9 Story 2 / Epic 12 Story 2 pattern.

- [ ] Implement `QueryRequest` — a **pure, JSON-native, hashable** description of one query (mirrors
  `LLMRequest`): compiled `sql`, `dialect`, `connection` (profile **name** — never credentials),
  optional bound `params`, `max_rows`, `byte_scan_cap`, `read_only`, `dry_run`. A `content_hash()`
  (sorted-keys sha256, excluding nothing secret because nothing secret is present) keys replay fixtures.
- [ ] Implement `QueryResult` — the inspectable result: a **tidy `DataFrame`** + JSON-native metadata
  (`row_count`, `columns` schema/dtypes, `bytes_scanned`, `cost_usd`, `dialect`, `truncated`,
  `elapsed_ms`). Confirm it satisfies `emergentflow.api.is_inspectable` and that no live connection/
  cursor escapes. Add `CostEstimate` (bytes/rows a `dry_run` would scan) and the schema-introspection
  result types (tidy frames).
- [ ] `ef.data.query(*, sql | spec, connection, client, limits) -> QueryResult` — the **single**
  wrapper both query nodes route through: it builds the `QueryRequest` (compiling the structured spec
  to SQL via `sqlglot` when given `spec`, or validating the raw `sql`), then calls
  `client.run(request)`. One function; `codegen` emits an `ef.data.query(...)` call threading the
  injected `clients.warehouse`, and `execute` calls the same function → ADR-0002 by construction.
- [ ] `ReplayWarehouseClient` (pure) + `write_fixture` — content-addressed `<content_hash>.json`
  fixtures replayed keyed by `QueryRequest.content_hash()`, raising a `FixtureMissError` with a copy-
  pasteable record hint on a miss (the exact `emergentflow/llm/replay.py` shape). This is the default
  in tests + the equivalence gate; CI never touches a warehouse.
- [ ] Every wrapper is a `@public_op` returning an inspectable value. Unit tests on the seam: unknown
  connection / dialect → typed error; a non-SELECT under read-only → typed error; **no input mutation**;
  a live driver object never present in the serialized payload; `content_hash()` stable across runs.

## Story 3 — Connection profiles + credential management (secret-free) & client-bundle threading

> The credential boundary and the bundle threading — both cross-cutting, both must land before the
> query nodes so they wire the injected client, not `os.environ`.

- [ ] Implement the **connection-profile store**: load/validate named `ConnectionProfile`s from the
  local file (+ optional OS keyring handle) into a secret-free in-memory registry the IR references by
  name. Serialization round-trips **without** any credential field. A `test_connection(profile)`
  helper (design-time, through the effectful client) validates coordinates + auth before a graph runs.
- [ ] Implement credential resolution **at the edge only**: `AdapterWarehouseClient` resolves a
  profile name → live credentials from env-var names / keyring / ADC at `run()` time. Add the
  **pre-flight presence check** (`emergentflow/data/warehouse/preflight.py`, the `llm/secrets.py`
  analog): before a run, for every warehouse-requiring node, assert the referenced profile exists and
  its credential env vars are set — raising a typed error naming the **missing profile / env var**,
  never a value.
- [ ] Thread the **client bundle** through `execute` and the compiled `main()` (Story 1 decision):
  `execute(graph, *, clients=Clients(llm=..., warehouse=...))` with the back-compat `client=` shim;
  the compiler emits `main(clients=...)` and each node resolves `clients.warehouse`. Update the server
  (Epic 7) execute path and any CLI entry to construct the bundle. Golden test: a graph with **both**
  an LLM node and a warehouse node compiles to a `main` that threads both, and a graph with neither is
  byte-identical to today's output.
- [ ] Register the `ConnectionRef` param kind + `Schema` type token (Epic 3 rules-as-data): a
  `connection` param renders as a **profile picker** on the canvas (choices from the local store, not
  the IR); the query node's OUT port is a plain `DataFrame`.

---

## Story group B — The query surface (raw SQL + visual builder + adapters)

## Story 4 — Raw-SQL node (`data.sql_query`) — the decided escape hatch

> The highest-frequency analyst reflex: paste a `SELECT` and get a DataFrame. The roadmap decided to
> **ship** the raw-SQL node (Decision #3: unsandboxed on the local happy path, Jupyter trust model,
> clearly marked un-validated). One node, routing `ef.data.query`.

- [ ] `data.sql_query` node: params `sql` (a SQL string; `widget="sql"`), `connection` (profile ref),
  `max_rows`, `dry_run`. `requires` the warehouse client; `cacheable = False` (underlying data can
  change without the SQL changing — the `load_csv` precedent). `execute` and `codegen` both call
  `ef.data.query(sql=..., connection=..., client=clients.warehouse, ...)`.
- [ ] `sqlglot`-based **read-only validation + dialect awareness**: parse the SQL in the profile's
  dialect; reject non-`SELECT`/`WITH` unless the profile opts into writes; surface parse errors as
  typed, actionable errors (marked un-validated per the roadmap decision, but still guarded against
  accidental DML). Inject `LIMIT max_rows` when absent.
- [ ] Golden `ast.parse` + `ruff check` on a representative `sql_query` graph (against DuckDB over a
  parquet fixture), plus the Story 9 equivalence slice under the replay client.

## Story 5 — Visual query builder (`data.query_builder`) — structured spec → dialect SQL

> "Visual SQL": the structured-params-over-formula move (Epic 12) applied to SQL. The analyst composes
> a query from pickers; the wrapper compiles it — verifiably, one dialect at a time. Design-inspired by
> the repo's `incremental-query-builder` philosophy: each layer (source → filter → join → aggregate)
> is independently valid and countable.

- [ ] `data.query_builder` node: structured spec params — `source` (relation, from the schema
  browser), `select[]` (columns / aggregates with aliases), `where[]` (predicates), `join[]`
  (relation + on-keys + join type), `group_by[]`, `having[]`, `order_by[]`, `limit`, `distinct`. A
  **single `_prepare_query_spec` gate** (the `_prepare_declarative` / `_prepare_model_spec` analog)
  shared by `codegen` and `execute` validates the spec (columns exist against the introspected schema
  where available, aggregates imply/accept `group_by`, join keys resolve) so both paths accept/reject
  identically.
- [ ] The wrapper compiles the spec to a **dialect-specific SQL string via `sqlglot`** (build an AST,
  render for the profile's dialect) — **inside the wrapper, one place**, so `codegen` and `execute`
  never differ. Expose a pure `compile_spec(spec, dialect) -> str` used by the wrapper *and* the UI's
  live SQL preview (same function → the preview can't drift from what runs).
- [ ] **Per-dialect compiled-SQL golden tests** — the epic's highest-leverage tests: one representative
  spec (join + filter + group-by + order + limit) compiled to BigQuery, Redshift, Postgres, and DuckDB
  SQL, each pinned. Plus the Story 9 equivalence slice (the compiled SQL runs against DuckDB fixtures
  and the result frame matches `execute`). **Deferred:** window functions, CTEs-as-builder-steps,
  sub-query composition, `UNION` (raw-SQL node covers them until demanded — widen by reviewed change).

## Story 6 — Warehouse adapters + generated connector catalog (breadth-as-data)

> Breadth as data + adapters, exactly like Epic 8's estimators / Epic 12's charts. One archetype,
> per-dialect adapters, a generated catalog. The dialect lives in the profile + adapter, never in a node.

- [ ] `WarehouseAdapter` protocol (execute a `QueryRequest` against a resolved connection → rows +
  schema + cost metadata) with implementations: **DuckDB** (bundled, in-process, MIT — over local
  parquet/CSV/duckdb files *and* as the fixture recorder), **BigQuery** (`[bigquery]` extra;
  `dry_run` + `maximum_bytes_billed` first-class), **Redshift** (`[redshift]` extra; `redshift-
  connector`, Apache-2.0), **Postgres** (`[postgres]` extra; SQLAlchemy + a permissive driver — psycopg
  is LGPL and lives only behind this extra). `AdapterWarehouseClient` dispatches by the profile's
  dialect.
- [ ] **Generate the connector catalog** (dialect key, label, extra name, auth-method schema,
  supported limits, one-line description) into the Epic 6 catalog-as-data artifact via a pure generator
  (`emergentflow/data/warehouse/generator.py`, the Epic 8 `generator.py` analog); wire into
  `ef.export_catalog()` with a **golden test** and stable ordering. The connection-manager UI lights up
  with **zero per-warehouse UI** — it renders auth fields from the catalog's auth-method schema.
- [ ] **Curate, don't enumerate** (the Epic 8 invariant): the catalog is the pinned allow-list of
  supported dialects, not whatever `sqlglot` can parse. Widen by reviewed change. **Deferred:**
  Snowflake, MySQL, Trino/Presto, Athena (add as adapters + rows when demanded).

---

## Story group C — Discovery & governance

## Story 7 — Schema introspection & the schema-browser API

> Analysts live in the schema: browse databases → schemas → tables → columns, then build against them.
> Introspection is I/O too — so it goes **through the client seam** (replayable), never inline in the
> pure core. Closes the "`df.<TAB>` discoverability" gap from the jupyter-replacement analysis.

- [ ] `WarehouseClient.list_relations(...)` / `describe_relation(...)` → **tidy schema frames**
  (database / schema / table / column / data_type / nullable). Replayable through
  `ReplayWarehouseClient` (content-addressed like queries) and served concretely by DuckDB + each
  adapter. A `data.describe_relation` **node** surfaces a schema frame in-graph (a `DataFrame` output).
- [ ] A **design-time schema-browser API** (server/UI-facing, not a graph node — the server calls it
  through the effectful client to populate pickers): list/describe with caching. This powers the
  builder's column/relation pickers and the raw-SQL editor's completion. Keep it out of `execute`/
  `codegen` (design-time only; the graph never re-introspects at run time).
- [ ] Golden/replay tests on the introspection frames (stable schema-frame shape); equivalence is n/a
  for the design-time API (it's not in the pure core) but the `describe_relation` node rides Story 9.

## Story 8 — Query safety, cost governance & guardrails

> Warehouses introduce a genuinely new risk class the rest of the product never had: a wrong query can
> cost real money or scan terabytes. Make the guardrails first-class and enforced **at the effect edge**.

- [ ] **Read-only by default:** `sqlglot`-parsed statement allow-list (`SELECT`/`WITH` only) unless the
  profile explicitly enables writes; block `DELETE`/`DROP`/`UPDATE`/`INSERT`/`TRUNCATE` with a typed
  error. **Row + byte caps:** inject `LIMIT`; set BigQuery `maximum_bytes_billed`; mark `truncated` on
  the result when a cap trims rows. **Timeout** per profile/node.
- [ ] **Dry-run cost estimate before spend:** `dry_run=True` returns a `CostEstimate` (bytes scanned /
  estimated rows) *without* running the query (BigQuery dry-run; a planner estimate elsewhere) — so the
  canvas can warn "this scans 4.2 TB" before the analyst hits run. All of this lives **inside the
  client / adapter**, never in `execute`/`codegen`.
- [ ] Tests: a DML string under a read-only profile → typed error; a byte-cap breach → typed error / a
  `dry_run` that surfaces the estimate; a cap that sets `truncated`. **Deferred:** per-user query
  budgets / spend ledgers (a hosted governance concern, roadmap §A6 — the `ef.llm.budget` analog for
  warehouses, if demanded).

---

## Story group D — Cross-cutting testing, canvas, and the payoff

## Story 9 — Equivalence & golden testing at scale

> ADR-0002 is a CI gate. With four dialects and two query nodes we prove it with a **parametrized
> harness over the dialect × query-shape matrix**, under a shared `ReplayWarehouseClient` — not one
> bespoke test per warehouse. Mirror Epic 9 Story 8 / Epic 12 Story 10.

- [ ] A `pytest.mark.parametrize` matrix that, per (dialect, query-shape), builds a minimal graph and
  asserts `execute(ir)` ≈ running `compile_to_code(ir)` — both handed the **same
  `ReplayWarehouseClient`** — keyed on the `QueryResult` frame **and** the compiled-SQL string (so
  driver identity / connection objects aren't compared). Compute the matrix dynamically from the
  connector registry (it grows as the allow-list widens — the Epic 8 `keys_for_archetype()` pattern).
- [ ] **DuckDB is the offline fixture backend:** record `QueryResult` / schema fixtures by running the
  compiled SQL against DuckDB-loaded parquet fixtures, so goldens are reproducible **without a cloud
  account**. Cloud-dialect fixtures (BigQuery/Redshift SQL text + a captured result) are checked in and
  replayed; a documented `--record` mode captures them. Mark every equivalence test
  `@pytest.mark.equivalence` and gate it in `.github/workflows/ci.yml` alongside the existing gate.
- [ ] Per-dialect **compiled-SQL goldens** (Story 5) + golden generated code for a representative
  `sql_query` and `query_builder` graph (readable, ruff-clean, importable). A **separate CI job** (the
  `[bayes]` precedent) installs the driver extras and runs against DuckDB/ephemeral Postgres; cloud
  dialects stay replay-only in the default lane (never touch BigQuery/Redshift in CI).

## Story 10 — Wire into the canvas (connection manager, schema browser, visual builder)

> The payoff on the UI side: the generated catalog + schema API drive the connection manager, the
> schema browser, and the visual builder with **zero per-warehouse / per-query-shape UI code**. Mirror
> Epic 8 Story 10 / Epic 12 Story 12 (consume the catalog, don't hand-write panels).

- [ ] **Connection manager** (`ui/`): create/select/test a named `ConnectionProfile`, rendering auth
  fields **from the connector catalog's auth-method schema**; credentials are stored **locally, never
  in the IR / never sent to the graph** (roadmap §Epic 9). The node's `connection` param renders as a
  profile picker.
- [ ] **Schema browser**: a database → schema → table → column tree from the design-time introspection
  API (Story 7), driving the builder's relation/column pickers and the raw-SQL editor's completion.
- [ ] **Visual builder panel + raw-SQL editor**: the `query_builder` structured spec renders from the
  node's param schema via the **existing curated config renderer** (Epic 8/12 Story-10 pattern — zero
  per-node UI), with a **live compiled-SQL preview** driven by the *same* `compile_spec` function that
  runs (Story 5) and an optional **dry-run cost badge** (Story 8). A new `sql` widget backs the raw-SQL
  node's editor. Confirm the query node's `DataFrame` output renders in the Results tab (Epic 7/12).
- [ ] Round-trip canvas → IR → `/compile` → downloadable `.py` and `/execute` (under the replay client
  in tests) with per-node status, for both a `sql_query`-terminal and a `query_builder → DataFrame`
  edge feeding an Epic 12 node.

## Story 11 — Acceptance demos (the payoff: real data → the whole analyst surface)

> Two end-to-end analyst workflows that prove the front door opens onto everything Epics 6/8/12 built.
> Mirror Epic 12 Story 12.

- [ ] **Acceptance demo (exploration):** `sql_query (DuckDB over a bundled parquet fixture) → describe →
  correlation heatmap` builds on the canvas, compiles to `.py`, and executes to a tidy summary + a
  rendered `PlotSpec` — proving a raw query flows straight into the Epic 12 EDA/viz surface, credential-
  free (DuckDB), so the demo runs in CI.
- [ ] **Acceptance demo (warehouse → stats):** `query_builder (join sales × regions, group-by,
  compiled to BigQuery SQL) → MixedLM (random intercept by region) → coefficient/forest plot` builds on
  the canvas, compiles (compiled BigQuery SQL visible in the `.py`), and executes **under the replay
  client** to a fixed-effects table + variance components + a rendered forest plot — proving the
  structured builder → dialect SQL → stats path end-to-end without touching BigQuery in CI.
- [ ] Document both under `docs/acceptance-demo.md` as the "data connectors, SQL & warehouses the app
  can do today" reference, and add an example graph pair under `examples/data_connectors_acceptance_demo/`
  (the Epic 8/12 `examples/*_acceptance_demo/` precedent), with the DuckDB parquet fixture + the
  checked-in BigQuery replay fixtures.

---

## Notes / Risks (carry into planning)

- **The injected-client seam already solved this — don't reinvent it.** A warehouse query is
  ADR-0017's exact problem (non-deterministic, credentialed, network I/O colliding with two pure
  functions). The temptation will be to let a node "just open a `bigquery.Client()` inline because it's
  only a read." That reintroduces the impurity ADR-0017 quarantined and breaks the ADR-0002 gate. The
  effect goes **through the injected `WarehouseClient`, always** — the middle stays pure.
- **Secrets in the IR is the one-way door.** The IR is exported to Git and shared with teammates
  (ADR-0001). A host / token / DSN that leaks into it can't be un-leaked. Carry a **profile name**;
  resolve credentials at the edge; add the pre-flight check *and* a test that serializes a
  warehouse-bearing graph and asserts no credential substring appears. This is the roadmap's explicit
  §Epic 9 risk — treat it as a hard invariant, not a best-effort.
- **Compile SQL in exactly one place.** The builder's structured spec must become a SQL string in a
  single `compile_spec` function shared by the wrapper (what runs) and the UI preview (what the analyst
  sees). Two code paths building SQL = the Epic-12 "codegen and execute build the formula differently"
  trap, but worse (a wrong join silently returns wrong numbers, not an error). One function, golden-
  tested per dialect.
- **Dialect drift breaks goldens — pin sqlglot.** A `sqlglot` bump can change rendered SQL. Pin it and
  treat the compiled-SQL goldens as the change-detector; a rendering change is a reviewed diff, not a
  silent surprise (the Epic 8/12 "pin the catalog, curate don't enumerate" invariant, applied to a
  transpiler).
- **Cost is a footgun the rest of the product never had.** A `SELECT *` on a partitioned fact table can
  scan terabytes and bill real money. Read-only + byte caps + `dry_run`-before-spend are not polish —
  they're the difference between a safe analyst tool and a way to accidentally spend $500. Enforce at
  the client edge; surface the estimate on the canvas *before* the run.
- **Pull, not pushdown, for v1 — and say so.** v1 pulls the query result into the engine; it does not
  push graph computation (a downstream `group_by` node) back down into SQL. Pushdown is a real later
  performance play (roadmap §Epic 9 note) but a different epic — resist starting it here or the query
  node's contract blurs into a query *planner*.
- **DuckDB is the unlock for CI and for real local work.** It's a real feature (query local parquet
  with zero credentials) *and* the offline fixture backend so the whole equivalence matrix + both
  acceptance demos run in CI without a cloud account. Lean on it hard; keep cloud dialects replay-only
  in the default lane.
- **Keep the base install credential-free and light.** Every cloud driver is an optional extra
  (`[bigquery]`/`[redshift]`/`[postgres]`), verified by a "import the package with all drivers absent →
  typed `MissingOptionalDependencyError`" test — the torch/`[bayes]` `importorskip` discipline. **psycopg
  is LGPL**: it lives only behind `[postgres]`, never on the hard-dep path; sqlglot/duckdb (MIT) and the
  BigQuery/Redshift connectors (Apache-2.0) are the only warehouse code near the base install.
- **The raw-SQL node is the decided escape hatch — ship it, mark it.** The roadmap already resolved the
  "do we ship a raw-SQL node?" debate: **yes, unsandboxed on the local happy path** (Jupyter trust
  model), clearly marked un-validated, gated behind the sandbox only in the hosted tier. Don't relitigate
  it; do keep the read-only guard even on the escape hatch so a stray `DROP` doesn't nuke a table.
- **Don't drift into adjacent/future work.** Table **writes / materialization** (dbt-style) and a full
  dbt integration are their own scope; **streaming/CDC** sources are a different connector family;
  **object storage** (S3/GCS blobs) is a sibling connector, not this SQL/warehouse slice; **managed/
  premium connectors + a managed secret store** are the hosted product (roadmap §A6); and **pushdown**
  is a later performance epic. This epic is the *read/query + introspect* front door — deliver that
  cleanly and let the analyst surface (Epics 6/8/12) do the rest.

---

*How to use this file: tick each `- [ ]` to `- [x]` as work completes. A story is done when all its
tasks are checked; the epic is done when the Definition of Done checklist is complete.*
</content>
</invoke>
