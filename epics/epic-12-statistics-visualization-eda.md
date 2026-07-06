# Epic 12 — High-Level Statistics, Visualization & Exploratory Data Analysis

> **Repo ↔ roadmap numbering.** Epic files are numbered by **delivery order in this repo**; the
> [technical roadmap](../planning_docs/technical_roadmap.md) numbers epics **globally**. This file
> is repo **Epic 12**. It deepens the `ef.stats` seam (repo Epic 6 Story 6 shipped a demo-sized
> slice — `ttest`, `anova`, `describe`, `correlation`) and the `ef.reports` seam into the surface a
> working data analyst / applied statistician / researcher actually reaches for: regression & GLMs,
> hierarchical / mixed-effects models, GAMs, collinearity & residual diagnostics, Bayesian modeling,
> a real interactive-charting catalog, and a first-class exploratory-data-analysis layer.
> **Always qualify "repo Epic N" vs "roadmap Epic N"** — see [`epics/README.md`](./README.md).

> **We borrow Epic 8's central bet, and apply it twice.** Epic 8 proved that breadth is delivered
> by **one adapter + a small set of archetype nodes + a generated catalog** (breadth becomes *data*,
> not N hand-written node files), so ADR-0002 equivalence holds **by construction across the whole
> catalog**. This epic reuses that move in the two places it fits cleanly:
> - **Visualization** is a near-perfect fit: `plotly.express` exposes a fixed, enumerable set of
>   chart types, so **one `viz.plot` archetype + a `chart` param + a generated chart catalog** covers
>   the whole surface, and each node returns `fig.to_plotly_json()` — a **JSON-native, inspectable
>   payload by construction** (no new binary-artifact escape hatch, no pixel-equivalence fragility).
> - **Statistical models** are more heterogeneous than sklearn estimators (each has its own spec,
>   output shape, and diagnostics), so here we do **not** force a single generic adapter. Instead we
>   fix a small number of **model archetypes** (fit-model / diagnostic / bayesian-fit) that all route
>   `codegen` and `execute` through one shared `ef.stats.*` / `ef.viz.*` wrapper per model, and all
>   ride inside **one shared inspectable representation** (`FittedStatsModel`), so ADR-0002
>   equivalence and the `@public_op` inspectable contract hold by construction without pretending the
>   families are more uniform than they are.

**Phase:** Follows repo Epic 6 (node library data path; `ef.stats`/`ef.reports`/`ef.data` seams;
catalog-as-data export) and repo Epic 8 (the estimator-adapter + generated-catalog pattern this epic
reuses, and the `FittedModel` inspectable precedent). Sequenced after Epic 8 so the viz layer can
also render Epic 8's `Model`/`Transformer` outputs (PCA/cluster scatter, confusion matrices).
**Lives in:** `emergentflow/` — the SDK tree owns the model wrappers (`emergentflow/stats/`), the viz
adapter + chart catalog (`emergentflow/viz/`), the new node archetypes (`emergentflow/nodes/`), the
generated chart-catalog entries, the new inspectable representations, and the type tokens. The canvas
palette + config panels (`ui/`, repo Epic 5) **only consume** the generated catalog and render the
`PlotSpec` payload — **no per-chart-type or per-model UI is written here**.
**Dependencies:** Epic 1 (node contract, param schema, registry, `@register`), Epic 2
(`compile_to_code` / `execute` + the golden/equivalence harness), Epic 3 / roadmap 5 (type tokens +
rules-as-data so `StatsModel`/`PlotSpec` ports validate), Epic 6 (catalog-as-data export;
`ef.stats`/`ef.reports` seams; `@public_op` inspectable contract), Epic 8 (`FittedModel` precedent;
the adapter + generated-catalog pattern). `statsmodels` (>=0.14, BSD-3-Clause), `scipy`, `pandas`,
`scikit-learn` are **already** runtime deps. New deps introduced: **`plotly` (MIT)** as a hard dep
for the viz layer; **`pymc` / `bambi` / `arviz`** as an **optional `[bayes]` extra** only (never in
the base install).
**Blocks:** roadmap Epic 8 (rich visual results — this epic emits the `PlotSpec`/tidy-frame payloads
that the Results tab renders), and raises the quality ceiling of the roadmap Epic 12 NL→graph agent
(the analyst surface it can target widens).

---

## Definition of Done (epic-level)

- [ ] **High-level statistics coverage:** regression & GLMs (OLS/WLS/GLS, logistic, Poisson/NegBin,
  Gamma — GLM families + link functions as params), **hierarchical / mixed-effects models**
  (fixed + random effects, random intercepts *and* slopes, grouping factors) via statsmodels
  `MixedLM`, **generalized additive models** (statsmodels `GLMGam` / B-splines), and a
  **diagnostics** family (VIF / multicollinearity, residual normality, heteroscedasticity,
  autocorrelation) are each reachable as nodes.
- [ ] **Bayesian modeling is optional-by-construction:** Bayesian GLM + hierarchical models (via
  `bambi`/`pymc`, summarized with `arviz`) ship behind a `pip install emergentflow[bayes]` extra;
  the base install never imports them, base-install use of a Bayesian node raises a **clear,
  typed "install the `[bayes]` extra" error**, and their equivalence tests use the torch-style
  `importorskip` discipline so CI's default lane never needs the heavy stack.
- [ ] **Model spec is structured params, not formula strings:** model nodes take explicit
  `target` / `fixed_effects[]` / `random_effects[]` / `groups` (etc.) params — validated on the
  canvas — and the wrapper assembles the statsmodels/Bambi call internally. (Formula-string entry is
  recorded as a deferred enhancement, Story 1.)
- [ ] **Visualization is a generated catalog over one archetype:** a single `viz.plot` archetype +
  a `chart` param covers the `plotly.express` chart surface (scatter, line, bar, histogram, box,
  violin, ECDF, density-heatmap, faceting, trendlines), driven by a **generated, curated,
  version-pinned chart catalog** — **not** one node file per chart type — plus a small set of
  **model-aware** plot nodes (coefficient/forest, residual, Q-Q, ACF/PACF, correlation heatmap,
  PCA/cluster scatter) that consume stats/Epic-8 outputs.
- [ ] **The inspectable contract holds everywhere:** every viz node returns a `PlotSpec`
  (`fig.to_plotly_json()` — JSON-native by construction); every model node returns a
  `FittedStatsModel` whose live-model field degrades to `{"kind": "unsupported"}` on the
  result-payload contract, alongside a **tidy coefficient/summary DataFrame** (estimate, SE, stat,
  p-value, CI — or posterior mean/sd/HDI/r_hat/ess for Bayesian) and diagnostic frames. A live
  statsmodels/plotly/PyMC object is **never** dumped into a response.
- [ ] **ADR-0002 holds by construction:** `codegen` and `execute` for every node route through the
  same `ef.stats.*` / `ef.viz.*` wrapper; both stay **pure** (no I/O, no global state) — fitted
  models and figure specs flow in-memory under `execute` and as plain variables in compiled code.
  A **parametrized equivalence harness** proves it over the model + chart matrix (keyed on the
  inspectable summary / the JSON spec, so opaque model internals aren't compared), gated in CI
  alongside the existing equivalence gate. Determinism is pinned with fixed seeds (and fixed MCMC
  draws/seeds for Bayesian).
- [ ] **New type tokens registered** (`StatsModel`, `PlotSpec`) with Epic 3 compatibility rules so a
  fitted model wires into a coefficient-plot / diagnostic node but not into a `DataFrame` input, and
  a `PlotSpec` is a terminal render output.
- [ ] **First-class EDA layer:** richer describe/profile, missingness analysis, distribution &
  group-by summaries returning tidy frames, and a one-shot "auto-EDA" node returning tidy frames + a
  small set of `PlotSpec`s — reusing the existing `ef.reports` (ydata-profiling) node, not replacing
  it.
- [ ] **License hygiene:** statsmodels/scipy/scikit-learn (BSD), plotly (MIT), and the optional
  pymc/bambi/arviz (Apache-2.0/MIT/Apache-2.0) — **no GPL** deps
  (`docs/licensing-and-dependencies.md`); no seaborn-forced/statsmodels-GPL-adjacent pulls.
- [ ] **Acceptance demos (Story 12):** (a) a **hierarchical-modeling** flow — `load → EDA →
  VIF → mixed-effects model → coefficient/forest plot` — and (b) an **exploratory** flow —
  `load → describe → correlation heatmap → faceted scatter w/ OLS trendline` — both build on the
  canvas, compile to `.py`, and execute end-to-end.
- [ ] **Explicitly out of scope:** time-series/forecasting model catalog (ARIMA/state-space — its own
  future epic; a couple of ACF/PACF *diagnostics* land here, not the model family), survival
  analysis, causal-inference/DoWhy, geospatial viz, dashboard/report *layout* composition (roadmap
  Epic 8/UI owns rendering; we emit payloads), and the raw-code escape hatch (decided-and-deferred,
  Epic 6 Story 1).

---

## Story group A — Foundations (the load-bearing seams)

## Story 1 — Lock the stats/viz architecture

> Cheap to decide, expensive to retrofit across the model + chart surface. No ADR is required (per
> request), but capture these decisions in a design note (`docs/stats-viz-design.md`) before building
> — this is the Epic-8-Story-1 equivalent.

- [ ] **Two inspectable representations, decided up front.** `FittedStatsModel` (one dataclass all
  fit-model archetypes ride inside: model kind, structured spec echo, tidy `coefficients` frame,
  `diagnostics` frame, `fit_stats` dict — AIC/BIC/loglik/converged — and a live-model field that
  degrades to `{"kind": "unsupported"}` on the result-payload contract, mirroring Epic 8's
  `FittedModel`). `PlotSpec` (a thin wrapper over the plotly JSON from `fig.to_plotly_json()`,
  JSON-native, the terminal render payload).
- [ ] **Model archetypes (not one generic adapter).** Fix three port shapes now, and record *why*
  we do **not** force a single sklearn-style adapter here (statistical models are too heterogeneous
  in spec + output + diagnostics; uniformity is bought with the shared `FittedStatsModel`
  representation + shared wrapper routing instead):
  - **fit-model:** `DataFrame (+ structured spec params)` → `StatsModel` + tidy coefficient
    `DataFrame` — OLS/GLM/MixedLM/GAM.
  - **diagnostic:** `DataFrame` (and/or a fitted `StatsModel`) → tidy `DataFrame` — VIF, residual /
    normality / heteroscedasticity / autocorrelation tests.
  - **bayesian-fit** *(optional `[bayes]` extra)*: `DataFrame (+ spec)` → `StatsModel` + tidy
    posterior-summary `DataFrame`.
- [ ] **Viz uses the Epic 8 move (one archetype + generated catalog).** `viz.plot` archetype with a
  `chart` param resolved through a curated **chart allow-list registry** (plotly.express function +
  accepted encoding kwargs); the node returns a `PlotSpec`. Record the trade-off (uniformity +
  ADR-0002-by-construction + zero per-chart UI vs. bespoke per-chart ergonomics) and why uniformity
  wins — same reasoning Epic 8 recorded for estimators.
- [ ] **Structured params over formula strings.** Model nodes take `target` / `fixed_effects[]` /
  `random_effects[]` / `groups` / `family` / `link` etc.; the wrapper builds the statsmodels/Bambi
  invocation internally (assembling a Patsy formula from the structured spec where the backend wants
  one). Record **formula-string entry as a deferred enhancement** (it would need its own validation +
  a formula→structured normalization), not shipped here.
- [ ] **Bayesian is an optional extra, decided as a hard boundary.** `pymc`/`bambi`/`arviz` live only
  under `pip install emergentflow[bayes]`; the base package must import and run with them absent. A
  Bayesian node in a base install raises a typed `MissingOptionalDependencyError("emergentflow[bayes]")`
  — never an opaque `ImportError`. Record the determinism obligation (fixed seed + fixed draws so the
  posterior summary is reproducible for the equivalence gate).
- [ ] **Dependency & license decisions.** Add `plotly` (MIT) as a hard dep and the `[bayes]` extra
  (pymc Apache-2.0 / bambi MIT / arviz Apache-2.0) to `pyproject.toml`; document each in
  `docs/licensing-and-dependencies.md` with the same rigor as the statsmodels/pingouin note. **No
  GPL** — call out that seaborn is *not* pulled (plotly covers the surface) and that the pingouin
  ban (GPL) still stands.

---

## Story 2 — Inspectable representations + the wrapper seams (`emergentflow/stats/`, `emergentflow/viz/`)

> Build the shared representations + the single wrapper each node routes through. This is the
> load-bearing seam: get it right and every model/chart inherits ADR-0002 equivalence and the
> `@public_op` inspectable contract — exactly the Epic 8 Story 2 pattern.

- [ ] Implement `FittedStatsModel` (+ any `PosteriorSummary` fields the bayesian archetype needs) as
  a Pydantic model / dataclass whose live-model field degrades to `{"kind": "unsupported"}` on the
  result-payload contract. Confirm the degrade path against the Epic 6/8 precedent.
- [ ] Implement `PlotSpec` wrapping `fig.to_plotly_json()`; confirm it is JSON-native and round-trips
  through the result-payload contract untouched (no live plotly `Figure` ever escapes).
- [ ] `ef.stats.fit_model(frame, *, model, spec) -> FittedStatsModel` — validates the model key +
  structured spec, resolves columns, fits, and wraps the live model in `FittedStatsModel` with the
  tidy coefficient/diagnostic frames built by a per-family **summary builder** (the Epic 8
  `summaries.py` analog). One function; every fit-model node's `codegen` emits an `ef.stats.fit_model(...)`
  call and its `execute` calls the same function → ADR-0002 by construction.
- [ ] `ef.viz.plot(frame, *, chart, encoding, options) -> PlotSpec` — validates the chart key +
  encoding kwargs against the chart registry, builds the plotly figure, returns
  `PlotSpec(fig.to_plotly_json())`. One function; every viz node routes through it.
- [ ] Every wrapper is a `@public_op` returning an inspectable value. Unit tests on the seams
  themselves: unknown model/chart key → typed error; bad spec/encoding → typed error; determinism
  given a fixed seed; **no input-frame mutation**; live object never present in the serialized
  payload.

---

## Story 3 — Type tokens & the shared structured-spec validation gate

> Structural validation and rendering both key off type tokens + the shape of the summary. Register
> them before the families widen so every new node validates and renders for free. Mirror Epic 8
> Story 3 and the declarative `_prepare_declarative` single-gate pattern.

- [ ] Register `StatsModel` (a fitted statistical model — distinct from Epic 8's `Model` predictor
  and `Transformer`) and `PlotSpec` (terminal render payload) type tokens; add Epic 3 rules-as-data
  compatibility rows to `docs/type-system-spec.md` (a `StatsModel` wires into coefficient-plot /
  diagnostic nodes, not into a `DataFrame` input; a `PlotSpec` is terminal).
- [ ] Implement `_prepare_model_spec` — the **single** structured-spec validation gate shared by both
  `codegen` and `execute` (as `_prepare_declarative` is shared by the compiler and executor) so both
  paths accept/reject identical specs: target exists, fixed/random effect columns exist, `groups` is
  present for mixed models, family/link are compatible, categorical vs. numeric coherence.
- [ ] Define the tidy-frame *shapes* per family once (coefficient frame columns; diagnostic frame
  columns; posterior-summary frame columns) so summaries render uniformly across the catalog and the
  golden tests key on a stable schema.

---

## Story group B — High-level statistics

## Story 4 — Regression & generalized linear models (fit-model archetype)

> The highest-frequency analyst surface. One `stats.fit_model` archetype node; family/link are params,
> not node types.

- [ ] Registry entries for: **OLS / WLS / GLS** (linear regression) and **GLM** with selectable
  `family` (Gaussian, Binomial→logistic, Poisson, NegativeBinomial, Gamma) + `link` — all through
  statsmodels. Structured spec: `target`, `fixed_effects[]`, optional `weights`, `family`, `link`,
  categorical handling (`C(col)` assembled internally), interaction terms.
- [ ] The fit-model node emits `StatsModel` + a tidy coefficient `DataFrame` (estimate, std err,
  statistic, p-value, CI-low, CI-high) plus `fit_stats` (R²/pseudo-R², AIC/BIC, loglik, n_obs,
  converged). Robust/cluster standard-error options exposed as params where statsmodels supports them.
- [ ] Golden `ast.parse` + `ruff check` on a representative spec (an OLS graph and a logistic-GLM
  graph) via a real `load_sample → fit_model` graph, plus the parametrized equivalence slice (Story
  10) over the regression/GLM keys. **Deferred:** regularized GLMs beyond statsmodels' built-ins,
  quantile regression, robust-M estimators (revisit if demand).

## Story 5 — Hierarchical / mixed-effects models (fixed + random effects)

> The headline researcher capability: HLM / multilevel models with fixed and random effects. Delivered
> through the same fit-model archetype + `MixedLM`, driven by structured params.

- [ ] Registry entry for **`MixedLM`** (statsmodels): structured spec `target`, `fixed_effects[]`,
  `random_effects[]` (random **intercepts** and random **slopes**), `groups` (the grouping factor),
  optional `re_formula`/variance-component structure assembled internally from the structured spec.
  The `_prepare_model_spec` gate enforces `groups` presence and that random-effect columns exist.
- [ ] The node emits `StatsModel` + a tidy summary with **fixed-effect** coefficients (est/SE/z/p/CI)
  **and** the estimated **random-effect variance components** (group variance, residual variance) as
  separate, clearly-labeled tidy rows; surface an **ICC** (intraclass correlation) in `fit_stats`
  where well-defined. Convergence status is first-class (non-convergence is common and must be
  reported, not swallowed).
- [ ] Golden + equivalence via the Story 10 harness on a small grouped fixture (fixed seed;
  well-separated groups so the fit is deterministic — the mixed-model analog of Epic 8's "ambiguous
  synthetic data makes KMeans nondeterministic" lesson). **Deferred:** crossed random effects beyond
  what `MixedLM` cleanly supports, GLMM (non-Gaussian mixed) — route non-Gaussian hierarchical use to
  the Bayesian family (Story 7), which handles it more naturally.

## Story 6 — GAMs + regression diagnostics (fit-model + diagnostic archetypes)

> Generalized additive models (smooth/spline terms) and the diagnostic toolkit an analyst runs
> *around* a fitted model — VIF, multicollinearity, residual and assumption checks.

- [ ] **GAM** registry entry: statsmodels `GLMGam` with B-spline smooth terms — structured spec
  `target`, `linear_terms[]`, `smooth_terms[]` (with per-term `df`/spline degree), `family`. Emits
  `StatsModel` + tidy term summary; note the sklearn-`transform`-less analog: partial-dependence /
  smooth-term shape data is surfaced as a tidy frame for a later smooth-plot node (Story 9).
- [ ] **Diagnostic** nodes (the diagnostic archetype → tidy frames, **no** live model in the
  payload):
  - **VIF / multicollinearity:** one tidy frame of per-feature variance-inflation factors
    (`statsmodels ... variance_inflation_factor`), with a configurable flag threshold.
  - **Residual diagnostics** (consume a fitted `StatsModel` or raw residuals): normality
    (Shapiro/Jarque-Bera), heteroscedasticity (Breusch-Pagan / White), autocorrelation
    (Durbin-Watson), plus the point data needed to *draw* residual & Q-Q plots (handed to Story 9).
- [ ] Golden + equivalence via the Story 10 harness. **Deferred:** influence/leverage
  (Cook's distance) as a full family — ship the most common checks first; widen by reviewed change.

## Story 7 — Bayesian modeling *(optional `[bayes]` extra; stretch / gated)*

> Full probabilistic modeling (Bayesian GLM + hierarchical) via PyMC/Bambi, summarized with ArviZ.
> Gated behind Stories 2–4 landing **and** the optional-dependency boundary from Story 1.

- [ ] **bayesian-fit** archetype node backed by `bambi` (structured spec → Bambi model → PyMC
  sampling): Bayesian linear/logistic GLM and Bayesian **hierarchical** models (random intercepts/
  slopes via the same `random_effects[]`/`groups` structured spec as Story 5, so the two families
  share a spec vocabulary). Priors default to Bambi's defaults; expose a small curated prior-override
  surface, `draws`, `tune`, `chains`, and a **fixed `seed`** (required for the equivalence gate).
- [ ] Emits `StatsModel` + a tidy **posterior-summary** frame from `arviz.summary`
  (mean, sd, HDI-low, HDI-high, `r_hat`, `ess_bulk`) — JSON-native — plus convergence diagnostics
  (`r_hat`/divergences) in `fit_stats`. The InferenceData/trace is **never** dumped into a payload;
  posterior/trace *plot data* is handed to Story 9.
- [ ] **Optional-dependency discipline:** base install absent-import → typed
  `MissingOptionalDependencyError("emergentflow[bayes]")`; equivalence/golden tests use
  `pytest.importorskip` (torch-style) so the default CI lane skips them; a **separate CI job** (or an
  opt-in marker) installs `[bayes]` and runs the Bayesian equivalence matrix with fixed draws/seed.
- [ ] Golden + equivalence via the Story 10 harness (under the `[bayes]` job). **Deferred:** custom
  PyMC model graphs (the escape-hatch decision), variational inference, non-Bambi model authoring.

---

## Story group C — Visualization

## Story 8 — Viz adapter + statistical chart catalog (`viz.plot` archetype)

> Breadth-as-data, exactly like Epic 8's estimators: one archetype + a generated, curated chart
> catalog. Every node returns a JSON-native `PlotSpec`.

- [ ] **Chart registry**: `{chart_key -> ChartSpec}` carrying the `plotly.express` function, accepted
  encoding kwargs (`x`, `y`, `color`, `size`, `symbol`, `facet_row`, `facet_col`, `hover_data`),
  chart-specific options, and a curated one-line description. Curate the analyst-core set: **scatter**
  (with `trendline="ols"`/`lowess` via statsmodels), **line**, **bar**, **histogram**, **box**,
  **violin**, **strip**, **ECDF**, **density-heatmap**, **density-contour**, with **faceting** and
  a **log-scale/marginal** option surface.
- [ ] `viz.plot` node routes through `ef.viz.plot`, emits `PlotSpec`. **Curation, not enumeration:**
  the catalog is pinned to the allow-list (not "every plotly.express function the installed version
  exposes") so it's deterministic and version-stable — the Epic 8 catalog-curation invariant.
- [ ] **Generate the chart catalog entries** (label/category/description/encoding schema) into the
  Epic 6 catalog-as-data artifact via a pure generator (`emergentflow/viz/generator.py`, the Epic 8
  `generator.py` analog); wire into `ef.export_catalog()` with a **golden test** and stable ordering.
  The palette lights up with **zero per-chart UI**.
- [ ] Golden `ast.parse` + `ruff check` on a representative chart per kind via a real
  `load_sample → viz.plot` graph, plus the Story 10 equivalence slice (PlotSpec JSON equality on a
  fixed frame + fixed seed for lowess/jitter).

## Story 9 — Model-aware & diagnostic plots (consume `StatsModel` / Epic 8 `Model` outputs)

> The plots that make the stats families legible — they read a fitted model or diagnostic frame, not
> just a raw DataFrame. This is where the stats + viz halves of the epic meet.

- [ ] **Coefficient / forest plot** from a `FittedStatsModel` coefficient frame (point estimate + CI
  whiskers; the mixed-model fixed-effects + variance-components view from Story 5). **Residual plot**
  and **Q-Q plot** from Story 6's residual-diagnostic data. **ACF/PACF** plots from the
  autocorrelation diagnostic. **Correlation heatmap** and **scatter-matrix / pair plot** from a
  DataFrame. All emit `PlotSpec`.
- [ ] **Bridges to Epic 8** (deferred rendering it left to "roadmap Epic 8"): **PCA scatter** (from a
  `Transformer`), **cluster scatter** (from a `cluster_detect` labeled frame), **confusion matrix**
  (from an `evaluate` result). These consume Epic 8 outputs and close its "return the payload, let
  the UI render it" loop with a concrete renderer.
- [ ] **Bayesian plot data** *(under `[bayes]`)*: posterior (KDE/hist) and trace plots built from the
  ArviZ summary/trace-plot data as `PlotSpec` (via plotly, not matplotlib), so they ride the same
  JSON-native contract.
- [ ] Golden + equivalence via the Story 10 harness on fixtures that produce a fitted model first
  (so the plot node's input is a real `StatsModel`/frame, not a stub).

---

## Story group D — Cross-cutting testing, EDA, and the payoff

## Story 10 — Equivalence & golden testing at scale

> ADR-0002 is a CI gate. With a generated chart catalog and a model matrix we prove it with a
> **parametrized harness over the matrix**, keyed on the inspectable summary / JSON spec — not one
> bespoke test per model or chart (the maintenance sink the archetypes exist to avoid). Mirror Epic 8
> Story 9.

- [ ] A `pytest.mark.parametrize` matrix that, per model/chart, builds a minimal graph and asserts
  `execute(ir)` artifacts ≈ running `compile_to_code(ir)` on a fixed sample frame — keyed on the
  tidy summary frame / posterior summary / `PlotSpec` JSON (so opaque model internals and plotly
  object identity aren't compared). Compute the matrix dynamically from the registries (it grows as
  the allow-lists widen — the Epic 8 `keys_for_archetype()` pattern).
- [ ] Fixed seeds + fixed sample datasets for determinism; mark every equivalence test
  `@pytest.mark.equivalence` and gate it in `.github/workflows/ci.yml` alongside the existing
  equivalence gate. Bayesian equivalence runs under the separate `[bayes]` job with fixed draws/seed.
- [ ] Golden tests on **generated code** for a representative model per archetype and chart per kind
  (readable, ruff-clean, importable) — not one golden per entry.

## Story 11 — First-class exploratory data analysis layer

> The everyday analyst loop: understand a dataset fast. Extend the `ef.stats`/`ef.reports` seams
> rather than replacing the existing ydata-profiling report node.

- [ ] EDA nodes returning tidy frames: **richer describe/profile** (numeric + categorical, skew/
  kurtosis, cardinality), **missingness analysis** (per-column null counts/%, and the co-missingness
  data a missingness-heatmap needs), **distribution summary**, and **group-by aggregation** (split /
  agg / pivot returning a tidy frame).
- [ ] An **auto-EDA** one-shot node returning a small bundle: tidy summary frames **+** a curated set
  of `PlotSpec`s (distributions, correlation heatmap, missingness) — composed from Story 8/9 nodes so
  it inherits their equivalence, not a parallel implementation.
- [ ] Confirm the existing `ef.reports.generate_html_summary` (ydata-profiling) node still stands as
  the heavyweight full-profile option; document when to reach for auto-EDA (fast, canvas-native tidy
  frames + plots) vs. the full HTML profile.
- [ ] Golden + equivalence via the Story 10 harness for the tidy-frame outputs.

## Story 12 — Wire into the canvas + acceptance demos

> The payoff: the generated catalog drives the palette and config panels with zero per-node UI, and
> real analyst workflows run end-to-end. Mirror Epic 8 Story 10.

- [ ] The canvas palette (repo Epic 5) renders every generated chart entry and the model/EDA nodes by
  `family`/`category` grouping; config panels render the structured model spec (`target`/
  `fixed_effects`/`random_effects`/`groups`/`family`) and chart encoding from catalog data with
  **zero per-node UI code** (reuse/extend the Epic 8 Story 10 curated-per-field config renderer).
  Confirm `StatsModel`- and `PlotSpec`-bearing edges validate on the canvas (Epic 3 rules), and that
  a `PlotSpec` output renders in the Results tab (roadmap Epic 8 renderer).
- [ ] Round-trip canvas → IR → `/compile` → downloadable `.py` and `/execute` with per-node status,
  including a `StatsModel`-bearing edge (model → coefficient plot) and a `PlotSpec`-terminal edge.
- [ ] **Acceptance demo (hierarchical):** `load_sample → auto-EDA → VIF → MixedLM (random intercept +
  slope, grouped) → coefficient/forest plot` builds on the canvas, compiles, and executes to a fixed-
  effects table + variance components + a rendered forest plot.
- [ ] **Acceptance demo (exploratory):** `load_sample → describe → correlation heatmap → faceted
  scatter with OLS trendline` builds on the canvas, compiles, and executes to tidy summaries + two
  rendered `PlotSpec`s.
- [ ] Document both under `docs/acceptance-demo.md` as the "statistics, viz & EDA the app can do
  today" reference, and add an example graph pair under `examples/stats_viz_acceptance_demo/` (the
  Epic 8 `examples/sklearn_acceptance_demo/` precedent).

---

## Notes / Risks (carry into planning)

- **The inspectable contract is the whole game for viz — and it's already won, if we hold the line.**
  `fig.to_plotly_json()` is JSON-native, so a `PlotSpec` rides the result-payload contract with **no
  new binary-artifact escape hatch** and no pixel-equivalence fragility. Resist any temptation to add
  a matplotlib-PNG node "just for one chart" — a raster blob reintroduces the exact binary-artifact
  problem this decision avoided. If a chart isn't expressible in plotly, that's a scope conversation,
  not a second backend.
- **Don't over-genericize the model layer.** Statistical models are *not* sklearn estimators — their
  specs, outputs, and diagnostics differ per family. Forcing a single generic adapter would be a
  leaky abstraction. The uniformity we need comes from the **shared `FittedStatsModel` representation
  + shared wrapper routing**, not from pretending MixedLM and GLMGam have the same shape. (Viz *is*
  uniform enough for the Epic 8 one-archetype move — apply it there, not here.)
- **Structured params, not formulas — but the backend wants a formula.** The node interface is
  structured (`target`/`fixed_effects`/`random_effects`/`groups`); the wrapper assembles the Patsy
  formula internally. Keep formula-string assembly **inside** the wrapper (one place, tested once) so
  ADR-0002 equivalence isn't threatened by codegen and execute building the formula differently.
- **Bayesian determinism is a hard requirement, not a nice-to-have.** MCMC is stochastic; the
  ADR-0002 equivalence gate compares `execute` vs. compiled output. Pin `seed` + `draws` + `chains`
  and assert on the ArviZ **summary** (mean/sd/HDI to a tolerance), not on raw draws. Without this the
  gate is flaky and the family is untestable.
- **Keep the `[bayes]` stack out of the base install — verified, not assumed.** pymc pulls pytensor +
  a C toolchain; if it leaks into the default import path it slows every install and CI run. Add a
  test that imports the whole package with `[bayes]` absent and asserts a typed
  `MissingOptionalDependencyError` from a Bayesian node — the torch-`importorskip` discipline the
  repo already uses.
- **Mixed-model non-convergence is a first-class result, not an exception to swallow.** `MixedLM`
  frequently fails to converge on real data; surface `converged` in `fit_stats` and never present a
  non-converged fit as if it succeeded. Use well-separated fixtures for the equivalence gate (the
  Epic 8 "ambiguous data makes KMeans nondeterministic" lesson, applied to mixed models).
- **Curate, don't enumerate — for charts too.** Pin the chart allow-list; don't reflect over whatever
  `plotly.express` the installed version exposes, or the catalog golden breaks on a plotly bump. Widen
  by reviewed change (the Epic 8 catalog invariant).
- **License hygiene still applies.** statsmodels/scipy/sklearn (BSD), plotly (MIT), pymc/arviz
  (Apache-2.0), bambi (MIT) are all clean. The bans that bit before still bite: **pingouin is GPL**
  (already replaced by statsmodels — don't reintroduce it for a convenience test), and **seaborn is
  deliberately not pulled** (plotly covers the surface; a seaborn dep would drag matplotlib into the
  render path and tempt the PNG escape hatch).
- **Don't drift into adjacent/future epics.** Time-series *models* (ARIMA/state-space), survival
  analysis, and causal inference are their own future epics (a few ACF/PACF *diagnostics* land here,
  not the model families); rich Results-tab **rendering/layout** is roadmap Epic 8 (we emit the
  `PlotSpec`/tidy-frame payload, the UI renders it); model **persistence/serving** is roadmap Epic 14
  (settle the `FittedStatsModel` representation here, defer the export path); the NL→graph agent is
  roadmap Epic 12.

---

*How to use this file: tick each `- [ ]` to `- [x]` as work completes. A story is done when all its
tasks are checked; the epic is done when the Definition of Done checklist is complete.*
