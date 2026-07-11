# The Acceptance Demo

**What the app can do today.** This document originally described the canonical end-to-end pipeline that superseded the original hardcoded 5-node vertical slice as the reference usable example. It has since itself been superseded as the flagship reference by the Epic 8 classical-ML acceptance demos below, which exercise the full sklearn estimator catalog (Epic 8) rather than the demo-sized `ef.ml` slice (`train_regressor`/`predict`/`evaluate`) this original pipeline used. The vertical slice still exists as a contract-by-construction proof; this original pipeline remains a valid, simpler worked example.

## The Pipeline

The acceptance demo is an 8-node FUNCTIONAL pipeline that spans five node families (`data`, `clean`, `ml`, `stats`, `reports`) and exercises the structural novelty of Story 7: a **`Model`-bearing edge** from a trained regressor to an evaluation node.

```
load_sample(diabetes) ─→ drop_missing ─→ select_columns
                                            ├─→ train_test_split
                                            │     ├─→ (train) train_regressor ──(model)──→ evaluate
                                            │     └─→ (test) ───────────────────────────→ evaluate
                                            ├─→ stats.describe
                                            └─→ reports.generate_html_summary
```

This pipeline goes **beyond the original five nodes**, pulling from multiple families and demonstrating how a fitted model ports from one stage to evaluation — a validation gate that ensures the type system and structural wiring keep the graph sound.

## Where It Lives

- **`examples/acceptance_demo/pipeline.json`** — the IR graph in canonical form, generated and validated by the test suite.
- **`examples/acceptance_demo/demo.py`** — the runnable worked example. The `run(output_dir=...)` function executes the full pipeline and returns a summary dict with keys: `r2`, `mae`, `n_test`, `n_rows`, `describe_rows`, `report_path`. It writes `report.html` to the specified output directory.
  - **One-liner:** `python examples/acceptance_demo/demo.py`

## How It's Verified

Three gates enforce correctness:

1. **Structural tests** in `tests/test_acceptance_demo.py` — validate the graph's shape, node types, and edge wiring.
2. **End-to-end demo tests** (also in `tests/test_acceptance_demo.py`) — run the pipeline directly and verify that the summary dict has the expected keys and reasonable metric bounds.
3. **ADR-0002 equivalence test** in `tests/test_codegen_equivalence.py` — the `test_acceptance_demo_equivalence` test proves that `ef.compile_to_code(graph)` and `ef.execute(graph)` produce equivalent results across the whole pipeline, including the `Model`-bearing edge. This is the hard invariant that keeps code generation and in-process execution in sync.

## Canvas Round-Trip

The same graph loads in the canvas palette (via `ef.export_catalog()`), compiles through the `/compile` endpoint to downloadable Python, and executes via `/execute` with real-time per-node status — the data-driven catalog path shipped in Stories 2–6.

## Classical ML Today (Epic 8) — the current flagship reference

Epic 8 built out the full scikit-learn estimator surface behind a generic adapter + four node
archetypes (`ml.fit_estimator`, `ml.fit_transform`, `ml.cluster_detect`, `ml.pipeline`/
`ml.grid_search`/`ml.cross_validate`) and a generated catalog, rather than one hand-written node
per estimator (`docs/adr/0016-sklearn-estimator-adapter.md`). Two new pipelines under
`examples/sklearn_acceptance_demo/` are the acceptance criteria for that epic and now supersede
the pipeline described above as the "classical ML the app can do today" reference.

### Supervised: scale → select → classify → evaluate

```
load_sample(iris) ─→ drop_missing ─→ ml.pipeline([StandardScaler, SelectKBest, GradientBoostingClassifier]) ──(model)──→ evaluate
                                                                                      └────────────(cleaned frame)───────────┘
```

`ml.pipeline` composes the scaler, feature-selector, and classifier into ONE fitted
`sklearn.pipeline.Pipeline` (not three DataFrame-chained nodes — see the note below on why),
riding inside the same `FittedModel`/`Model` port every other supervised node uses, so the
existing `ml.evaluate` node scores it unchanged.

### Unsupervised: scale → cluster → summarize

```
load_sample(iris) ─→ ml.fit_transform(StandardScaler) ──(result)──→ ml.cluster_detect(KMeans) ──(model)──→ ml.summarize
                                       └──(transformer)──→ ml.transform  ←──(frame)──┘
```

Demonstrates a real `Transformer`-bearing edge (`ml.fit_transform`'s `transformer` output wired
into the companion `ml.transform` apply node) alongside a labeled frame (`ml.cluster_detect`'s
`cluster` column) and an inspectable structural summary (`ml.summarize`, backed by
`ef.ml.summarize()` — cluster sizes / inertia for `KMeans`).

**Why not `scale → PCA → cluster`, matching the epic's original informal wording exactly?**
`ef.ml.fit_transform` always names its output columns `component_0`, `component_1`, ... and
raises if the input frame it's given already has a column with one of those names — so two
`ml.fit_transform` nodes cannot be chained directly via a DataFrame edge (the second call's
`component_0` collides with the first call's). Composing more than one transform step requires
`ml.pipeline` instead (as the supervised demo above does) — but a `Pipeline`-wrapped `Model`'s
`estimator_type` is `"Pipeline"`, which has no registered summary builder, so `ml.summarize`
would degrade to `{"kind": "unsupported"}` and defeat the point of the "inspectable cluster
summary" acceptance criterion. This demo keeps exactly one `fit_transform` step feeding directly
into `cluster_detect` so `ml.summarize` returns KMeans's real structural summary.

### Where they live

- **`examples/sklearn_acceptance_demo/supervised_pipeline.json`** /
  **`examples/sklearn_acceptance_demo/unsupervised_pipeline.json`** — the IR graphs in canonical
  form, generated and validated by `tests/test_sklearn_acceptance_demo.py`.
- Both graphs load in the canvas palette (via `ef.export_catalog()`'s generated `"estimators"`
  entries), compile through `/compile` to downloadable Python, and execute via `/execute` — the
  same data-driven catalog path the original acceptance demo above documents, now exercising the
  full sklearn archetype surface.

### How they're verified

`tests/test_sklearn_acceptance_demo.py` proves, for each pipeline: the committed JSON matches
what the builder function produces (a drift guard), the graph's node/edge counts and node types
are as expected, and an `@pytest.mark.equivalence` test (reusing
`tests/test_codegen_equivalence.py`'s `assert_equivalent` harness) that `execute(graph)` and
running the code `compile_to_code(graph)` emits produce equivalent results end to end.

## Statistics, Visualization & EDA Today (Epic 12) — the analyst surface

Epic 12 deepened `ef.stats`/`ef.viz` into the working-analyst surface — regression/GLM,
mixed-effects (`MixedLM`), GAMs, diagnostics (VIF/residual/normality), a generated `viz.plot`
chart catalog + model-aware plots, and a first-class EDA layer (`stats.auto_eda` one-shot
bundle). Two pipelines under `examples/stats_viz_acceptance_demo/` are the acceptance criteria
and demonstrate the stats+viz+EDA halves meeting end to end. Note both ride the same
inspectable-payload + ADR-0002 contracts as everything else (a `StatsModel`-bearing edge into a
coefficient plot; a `PlotSpec`-terminal edge the Results tab renders).

### Hierarchical: auto-EDA → VIF → mixed-effects → forest plot

```
load_sample(iris) ─→ stats.auto_eda ──(frame)──→ stats.diagnostic_frame(VIF)
                                     └─(frame)──→ stats.fit_mixed_model ──(StatsModel)──→ viz.plot_coefficients
```

`stats.auto_eda` returns tidy `profile`/`missingness`/`correlation` frames + curated `PlotSpec`s
(including a co-missingness heatmap) AND passes the frame through so VIF (multicollinearity) and
the `MixedLM` fit both read it;
`MixedLM` fits fixed + random effects on `petal length (cm)` grouped by `target`, emitting a
`FittedStatsModel` (fixed-effect coefficients + variance components) that flows over a
`StatsModel` edge into the coefficient/forest plot (a `PlotSpec`). Non-convergence is a
first-class, reported result (`fit_stats.converged`), not a swallowed exception.

### Exploratory: describe → correlation heatmap → faceted scatter w/ OLS trendline

```
load_sample(iris) ─→ stats.describe
                 ├─→ stats.correlation ──(matrix)──→ viz.plot_correlation_heatmap
                 └─→ viz.plot(scatter, facet_col=target, trendline="ols")
```

The everyday EDA loop — tidy `describe` summary, a correlation matrix rendered as a `PlotSpec`
heatmap, and a faceted scatter with a statsmodels OLS trendline (via the generated `viz.plot`
catalog's `scatter` chart + `trendline` option), each output a JSON-native `PlotSpec` or tidy
frame.

### Where they live

- **`examples/stats_viz_acceptance_demo/hierarchical_pipeline.json`** /
  **`examples/stats_viz_acceptance_demo/exploratory_pipeline.json`** — the IR graphs in canonical
  form, generated and validated by `tests/test_stats_viz_acceptance_demo.py`.
- Both load in the canvas palette (via `ef.export_catalog()`'s generated catalog entries — the
  new `stats.*` model/EDA nodes and `viz.*` chart/plot nodes), compile through `/compile` to
  downloadable Python, and execute via `/execute` — the same data-driven catalog path, now
  exercising the stats + viz + EDA surface with zero per-node UI.

### How they're verified

`tests/test_stats_viz_acceptance_demo.py` proves, for each pipeline: the committed JSON matches
the builder (drift guard), the node/edge counts and node types are as expected, and an
`@pytest.mark.equivalence` test (reusing `assert_equivalent`) that `execute(graph)` and running
the `compile_to_code(graph)` output produce equivalent results end to end — keyed on the
canonical inspectable payloads (tidy frames / `PlotSpec` JSON / the `FittedStatsModel` summary,
whose live results object degrades to `{"kind": "unsupported"}`), so opaque model internals are
never compared.

## Data Connectors & Warehouses Today (Epic 13) — the front door

Epic 13 gives the analyst surface a real front door: a `WarehouseClient` seam injected exactly
like `LLMClient` (ADR 0018), a raw-SQL escape hatch (`data.sql_query`) and a visual query
builder (`data.query_builder`) that both compile through one `ef.data.query` wrapper, and a
generated connector catalog spanning DuckDB (bundled, credential-free), BigQuery, Redshift, and
Postgres. Both query nodes' `frame` OUT port is a bare, tidy `DataFrame` — the same
`QueryResult` metadata (`row_count`, `bytes_scanned`, `cost_usd`, `dialect`, ...) `ef.data.query`
computes is available at the SDK level, but the node unwraps to `.df` on its declared
`DataFrame` port (except under `dry_run`, where there is no real frame to unwrap — the port
carries the `QueryResult`/`CostEstimate` metadata instead, which the canvas's dry-run cost badge
reads) so a query's output flows into the rest of Epics 6/8/12 with zero glue code. Two
pipelines under `examples/data_connectors_acceptance_demo/` are the acceptance criteria and
demonstrate exactly that: a raw query feeding the EDA/viz surface, and a structured, joined
query feeding a mixed-effects model.

### Exploration: sql_query → describe → correlation heatmap

```
sql_query(DuckDB, read_parquet('.../sales.parquet')) ─→ stats.describe
                                                     └─→ stats.correlation ──(matrix)──→ viz.plot_correlation_heatmap
```

A raw SQL query against a bundled parquet fixture
(`examples/data_connectors_acceptance_demo/sales.parquet`) — no credentials, no network, runs
anywhere including CI — flows straight into a `stats.describe` summary and a
`stats.correlation` matrix rendered as a `PlotSpec` heatmap, proving the "DataFrame flows into
the analyst surface for free" contract holds for warehouse data exactly as it does for
`data.load_sample`/`data.load_csv`.

### Warehouse → Stats: query_builder (join + group-by, BigQuery SQL) → MixedLM → forest plot

```
query_builder(join sales × regions, group by region+rep, dialect=bigquery) ─→ stats.fit_mixed_model (random intercept by region) ──(StatsModel)──→ viz.plot_coefficients
```

The structured query builder joins a transactions table to a region-level covariates table,
groups down to one row per rep per region, and compiles to **BigQuery** SQL via the shared
`compile_spec` function (the same function backing the canvas's live SQL preview — one place,
never drifts). The resulting frame fits a `MixedLM` with a random intercept by region, emitting
a `FittedStatsModel` that flows over a `StatsModel` edge into a coefficient/forest plot. This
demo runs entirely under a `ReplayWarehouseClient` fixture keyed on the compiled BigQuery SQL —
**BigQuery is never touched**, in this test or in CI; DuckDB is the only warehouse this repo's
gates ever really connect to.

### Where they live

- **`examples/data_connectors_acceptance_demo/exploration_pipeline.json`** /
  **`examples/data_connectors_acceptance_demo/warehouse_stats_pipeline.json`** — the IR graphs
  in canonical form, generated and validated by `tests/test_data_connectors_acceptance_demo.py`
  and `tests/test_data_connectors_warehouse_stats_demo.py` respectively.
- **`examples/data_connectors_acceptance_demo/sales.parquet`** — the bundled, deterministic
  parquet fixture the exploration demo queries directly.
- Both graphs load in the canvas palette (via `ef.export_catalog()`'s generated `"connectors"`
  entries), compile through `/compile` to downloadable Python (the compiled BigQuery SQL is
  visible in the generated `.py` for the warehouse-stats demo), and execute via `/execute` with
  per-node status — the connection manager, schema browser, and query-builder panel (live SQL
  preview + dry-run cost badge) render entirely from the generated catalog and the design-time
  schema-browser API, zero per-warehouse UI code.

### How they're verified

Unlike the Epic 8/12 demos above, these two do **not** reuse
`tests/test_codegen_equivalence.py`'s `assert_equivalent` harness — that helper calls bare
`execute(graph)` with no way to inject a `WarehouseClient`. Instead, each demo's
`@pytest.mark.equivalence` test builds a `ReplayWarehouseClient` fixture (content-addressed by
`QueryRequest.content_hash()`, exactly like the Story 9 dialect × query-shape equivalence
matrix in `tests/test_warehouse_equivalence_matrix.py`), then compares `execute(graph,
clients=...)` against the SAME compiled module's `main(clients=...)` run in-process — the
compiler's own `_assemble(graph).out_ports` locates each leaf artifact's compiled variable name
precisely, so the comparison never depends on dict-insertion-order luck. The committed JSON
matches each builder (drift guard); node/edge counts and node types are as expected; and the
compiled code for both demos passes `ast.parse` + `ruff check`.

## Agent Collaboration Today (Epic 14) — human + agent on one canvas

Graph sessions (`emergentflow/collab/session.py`) let a human and an agent co-author one shared
graph over plain HTTP. An agent proposes changes as a `GraphMutation` (it never edits files),
the server validates the proposal before the human ever sees it (validate-on-propose), and an
accepted proposal becomes an ORDINARY graph — the exact same `/compile`/`/execute` a solo canvas
user hits, so ADR-0002 needs no new equivalence case. The two demos below prove collaboration
runs both directions.

### Agent builds, human accepts: load_csv → describe, extended with a stats + chart pair

```
load_csv(sample.csv) ─→ describe
                  └─→ describe (extension) ──→ plot(histogram)
```

A seeded session with a `data.load_csv` node feeding a `stats.describe` node (wired by edge
`e1`). The agent discovers the session via `GET /sessions`, reads `/catalog`, and builds a
proposed extension: a parallel second `stats.describe` (n3, labelled "Describe (extension)")
reading from the same `load_csv` node, whose `summary` output port feeds a `viz.plot` node
(n4, chart=`"histogram"`, encoding=`{"x": "score"}`) in series. The agent pre-flights the
full 4-node candidate through `/validate` (clean diagnostics) and `/compile` (ruff-clean
Python), then submits it as a `GraphMutation` with `author: "emergent-flow-collaborator"`.
The human accepts via the ordinary proposal-accept machinery, the session version increments
from 0 to 1, and the accepted graph compiles to ruff-clean Python and executes to real results
— all asserted in `tests/test_acceptance_demo_agent_builds.py`.

### Human builds, agent reviews: a planted encoding flaw, fixed via a review's attached mutation

```
load_csv(sample.csv, encoding="latin-1")
              ↑  ⚠️ reviewer: "stale encoding, recommend utf-8"
```

A human seeds a session with a single `data.load_csv` node that reads the bundled sample CSV
but has `encoding` pinned to `"latin-1"` (stale — the modern default is `"utf-8"`). The
`data_modeller` persona (following the Review workflow in `agents/emergent-flow-collaborator.md`)
posts two findings on the session: an **info** finding (`grain_check`: "grain is trivially one
row per source row") with no fix attached, and a **warning** finding (`encoding_stale`:
"encoding is pinned to latin-1; recommend utf-8") with a `GraphMutation` fix (`set_params`:
n1's encoding → `"utf-8"`). The human replies ("Good catch, applying now."), then applies the
fix by posting the review's attached mutation as an ordinary proposal — there is zero new
"apply" code (Story 6/4's point — the fix rides the same proposal machinery as any other
delta). The accepted graph re-validates clean, compiles to ruff-clean Python, and executes to
real results — all asserted in `tests/test_acceptance_demo_human_builds.py`.

### Where they live

- **`tests/test_acceptance_demo_agent_builds.py`** /
  **`tests/test_acceptance_demo_human_builds.py`** — the CI-enforced source of truth for both
  demos.
- **`examples/agent_collaboration_acceptance_demo/`** — the seed graphs (`seed_graph_agent_builds.json`,
  `seed_graph_human_builds.json`), persona-file pointers, and human-readable `curl`-style call
  sequence transcripts (`transcript_agent_builds.md`, `transcript_human_builds.md`) for both
  demos.
- **`agents/emergent-flow-collaborator.md`** — the full collaboration protocol (find the
  server, sessions, catalog, pre-flight, propose, accept) that both demos' scripted agent
  follows.
- **`agents/data-modeller.md`** — the reviewer persona used in the "human builds, agent
  reviews" demo.

### How they're verified

Both demos run entirely as scripted pytest HTTP clients over `TestClient(create_app())` — no
LLM, no live network; the "agent" IS the test. The accepted/fixed graph in each demo is proven
`ast.parse`-valid and `ruff check`-clean, then actually executed via `/execute` with per-node
`"status": "ok"` assertions, mirroring the Epic 8/12/13 demos' own `ast.parse` + `ruff check`
discipline (see the Epic 13 section above) extended one step further to also execute.

The manual milestone — a live Claude Code session with the persona file driving the same flows
against a real `emergentflow serve` process, ghost diff visible on the canvas — is the
human-observable proof-of-concept companion to these CI tests (not itself CI-checked; see
`epics/epic-14-agent-collaboration.md` Story 12's unchecked manual-milestone line).
