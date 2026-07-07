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
                                     └─(frame)──→ stats.fit_model(MixedLM) ──(StatsModel)──→ viz.plot_coefficients
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
