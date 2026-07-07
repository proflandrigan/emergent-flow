# Emergent Flow — Statistics & Visualization Design Note (Epic 12)

- **Status:** Accepted
- **Date:** 2026-07-06
- **Deciders:** Emergent Flow core team
- **Scope:** Not an ADR (per Epic 12 Story 1); a design note capturing the stats/viz
  architecture locked before the model + chart families are built. The Epic-8-Story-1 /
  ADR-0016 equivalent.

## Context

Repo Epic 6 Story 6 shipped a demo-sized `ef.stats` slice — `ttest`, `anova`, `describe`,
`correlation` — that proved the seam exists but stops well short of the surface a working data
analyst, applied statistician, or researcher actually reaches for. Epic 12 deepens that slice
into that surface: regression and GLMs, hierarchical / mixed-effects models, GAMs, collinearity
and residual diagnostics, optional Bayesian modeling, a real interactive-charting catalog, and a
first-class exploratory-data-analysis layer.

We borrow [ADR 0016](./adr/0016-sklearn-estimator-adapter.md)'s central bet — breadth is
delivered as curated *data* consumed by a small, fixed set of archetype nodes, not as N
hand-written `NodeDefinition` files — because it is what let Epic 8 scale to ~200 sklearn
estimators without turning "add an estimator" into a permanent maintenance sink, and without
threatening [ADR 0002](./adr/0002-execute-the-ir-not-the-string.md) equivalence one node at a
time. This epic applies that move in the two places it actually fits: visualization, where
`plotly.express` exposes a fixed, enumerable chart surface and the fit is near-perfect, and,
more carefully, statistical models, where the underlying libraries are far more heterogeneous
in spec shape, output shape, and diagnostics than sklearn's uniform `fit`/`predict`/`transform`
protocol. Forcing the sklearn-style single generic adapter onto the model layer would be a leaky
abstraction; instead we buy the same construction-time equivalence and inspectable-contract
guarantees through one shared representation (`FittedStatsModel`) and shared wrapper routing
per archetype, without pretending MixedLM and GLMGam share a shape.

This note exists because these decisions are cheap to make now and expensive to retrofit once a
generated chart catalog, a model-archetype matrix, an equivalence-test harness, and a canvas
palette all depend on them — the same "lock it before Story 2 builds it" reasoning ADR 0016
recorded for the estimator adapter. Reference [ADR 0002](./adr/0002-execute-the-ir-not-the-string.md)
(execute-the-IR equivalence, the invariant every decision below is in service of),
[ADR 0016](./adr/0016-sklearn-estimator-adapter.md) (the estimator-adapter precedent this note
reuses and, in one place, deliberately departs from), and the `FittedModel`/`Model`-token
precedent from repo Epic 8.

## Decisions

### 1. Two inspectable representations, decided up front

`FittedStatsModel` is the one dataclass every fit-model archetype rides inside: a `model` kind
string, a structured spec echo, a tidy `coefficients` frame, a `diagnostics` frame, a `fit_stats`
dict (AIC/BIC/loglik/`converged`), and a live-model field that degrades to
`{"kind": "unsupported"}` on the result-payload contract — mirroring Epic 8's `FittedModel`. In
parallel, `PlotSpec` is a thin wrapper over `fig.to_json()` (parsed back with `json.loads`), JSON-native by construction,
the terminal render payload every viz node emits.

We fix one shared representation per family rather than per-model or per-chart classes because
that uniformity is what buys `ADR-0002` equivalence and the `@public_op` inspectable contract
across a heterogeneous surface without a bespoke proof per model or per chart. The alternative —
letting OLS, MixedLM, and GLMGam each return their own ad hoc result shape — would mean the
equivalence harness and the Results-tab renderer would each need per-model special-casing,
reintroducing exactly the maintenance sink the archetype pattern exists to avoid. Paying the cost
once, at the representation level, is cheaper than paying it N times at the call-site level.

### 2. Model archetypes, NOT one generic sklearn-style adapter

We fix three port shapes now: **fit-model** (`DataFrame` + a structured spec →
`StatsModel` + a tidy coefficient `DataFrame`; covers OLS/WLS/GLS, GLM, `MixedLM`, GAM),
**diagnostic** (`DataFrame` and/or a fitted `StatsModel` → a tidy `DataFrame`; covers VIF,
normality, heteroscedasticity, autocorrelation), and **bayesian-fit** (optional `[bayes]` extra;
`DataFrame` + spec → `StatsModel` + a tidy posterior-summary `DataFrame`).

We explicitly do **not** force a single generic adapter the way ADR 0016 did for sklearn
estimators. That decision worked for sklearn because the underlying protocol really is uniform:
every estimator exposes the same `fit` + (`predict`|`transform`|`fit_predict`|`score_samples`)
shape, so one adapter plus a curated allow-list could cover ~200 estimators without loss of
fidelity. Statistical models do not share that uniformity: an OLS spec is a flat set of
predictors, a `MixedLM` spec additionally requires `random_effects[]` and `groups`, a GAM spec
carries per-term smoothing degrees, and each family's diagnostics and fit statistics differ in
kind, not just in value. Collapsing all of that into one generic adapter call would either
truncate real capability behind a lowest-common-denominator param surface, or grow a single
function's parameter list into an unreadable superset of every backend's quirks — a worse outcome
than ADR 0016's estimator adapter, whose single param surface stays coherent precisely because
the protocol underneath it already is. Instead, the uniformity we need comes from the shared
`FittedStatsModel` representation and from routing every family's `codegen`/`execute` pair
through the same per-family wrapper function, not from pretending the families themselves are
interchangeable. This is the direct point of departure from ADR 0016, recorded here so a future
reader doesn't wonder why Epic 12 didn't just reuse Epic 8's adapter wholesale.

### 3. Viz uses the Epic 8 move — one archetype + a generated catalog

Visualization gets the opposite treatment, because here the underlying surface genuinely is
uniform: a single `viz.plot` archetype takes a `chart` param resolved through a curated **chart
allow-list registry** (a `plotly.express` function plus its accepted encoding kwargs per chart
key), and the node returns a `PlotSpec`. This is the same trade-off ADR 0016 recorded for
estimators — uniformity, `ADR-0002`-equivalence-by-construction, and zero per-chart UI, traded
against bespoke per-chart ergonomics (no chart gets a hand-tuned config panel or idiomatic
codegen) — and it wins for the identical reason: the cost of bespoke polish per chart is real but
small, while the cost of N hand-written chart nodes (N codegen/execute pairs, N equivalence
tests, N palette entries) would recreate the exact maintenance sink ADR 0016 was written to
avoid. As with the sklearn catalog, this is curation, not enumeration: the chart catalog is
pinned to an allow-list and is never reflected from `plotly.express` at runtime, so a
`plotly` version bump can't silently change the generated catalog or break the golden test on it
— the same version-stability argument ADR 0016 made for not calling
`sklearn.utils.all_estimators()`.

### 4. Structured params over formula strings

Model nodes take explicit structured params — `target`, `fixed_effects[]`, `random_effects[]`,
`groups`, `family`, `link`, and so on — rather than accepting a raw Patsy/R-style formula string.
The wrapper assembles the statsmodels/Bambi invocation internally, building a Patsy formula from
the structured spec in the one place a backend actually wants one. We keep that formula assembly
strictly inside the wrapper, and nowhere else, because if `codegen` and `execute` each built the
formula string independently there would be two places for the assembly logic to drift apart,
directly threatening `ADR-0002` equivalence for a reason that has nothing to do with the model
math itself. A single, tested assembly path removes that risk by construction, at the cost of the
wrapper carrying that translation logic.

Formula-string entry — letting a user type `y ~ x1 + x2 * x3` directly — is recorded here as a
**deferred enhancement**, not shipped in this epic. It would require its own validation surface
and a formula-to-structured normalization step (so the canvas config panel and the equivalence
gate still have a structured spec to key off), which is real work with no capability gain over
what structured params already express; it does not earn its cost until there is concrete demand
for raw-formula authoring.

### 5. Bayesian is an optional extra — a hard boundary

`pymc`, `bambi`, and `arviz` live only under `pip install emergentflow[bayes]`; the base package
must import and run correctly with all three absent. A Bayesian node invoked in a base install
raises a typed `MissingOptionalDependencyError("emergentflow[bayes]")` — never a bare, opaque
`ImportError` a user has to decode. This mirrors the repo's existing `torch`-optionality
discipline (equivalence/golden tests use `pytest.importorskip`, and a separate CI job installs
`[bayes]` to run the Bayesian matrix) rather than inventing a new pattern for one dependency
family.

The harder obligation is determinism: MCMC sampling is inherently stochastic, but the
`ADR-0002` equivalence gate compares `execute(ir)` against running `compile_to_code(ir)`, so a
Bayesian node must still produce comparable output across the two paths. We resolve this by
pinning a fixed `seed` plus fixed `draws`/`chains` as required params, and by asserting
equivalence on the ArviZ **summary** (posterior mean/sd/HDI to a numeric tolerance) rather than on
raw MCMC draws, which would never compare bit-for-bit even with a fixed seed across
runs/environments. Without both the fixed-seed requirement and the summary-level comparison, the
Bayesian equivalence gate would be flaky by nature and the family effectively untestable.

### 6. Dependency & license decisions

`plotly` (MIT) is added as a hard runtime dependency, since the whole viz archetype rests on it.
The `[bayes]` extra adds `pymc` (Apache-2.0), `bambi` (MIT), and `arviz` (Apache-2.0). All of
these are permissive licenses compatible with the SDK's Apache-2.0 license — **no GPL** is
introduced anywhere in this epic.

Two omissions are deliberate and worth recording explicitly rather than leaving as silent
absences: **seaborn is not pulled**, because `plotly` already covers the interactive-chart
surface this epic needs, and a `seaborn` dependency would drag `matplotlib` into the render path
and tempt a PNG/raster escape hatch — precisely the binary-artifact problem the `PlotSpec`
JSON-native contract exists to avoid. And the **pingouin ban (GPL) still stands**: pingouin is
GPL-licensed, was already rejected once in favor of `statsmodels`, and this epic does not
reintroduce it for any convenience test it might otherwise make marginally easier to write. Both
decisions are cross-referenced in `docs/licensing-and-dependencies.md`, which this epic updates
with the same rigor as the existing statsmodels/pingouin note.

## New type tokens

`StatsModel` (a fitted statistical model — distinct from Epic 8's `Model` predictor and
`Transformer` tokens) and `PlotSpec` (the terminal render payload), with Epic 3 rules-as-data
compatibility: a `StatsModel` wires into a coefficient-plot or diagnostic node, never into a
`DataFrame` input; a `PlotSpec` is a terminal render output and does not wire into anything
downstream.

## Consequences

**Positive:**

- `ADR-0002` equivalence holds for the whole chart catalog the moment it holds for `ef.viz.plot`,
  and for each model family the moment it holds for that family's wrapper — without a bespoke
  proof per chart or per model.
- The viz node `type` enum stays fixed at one archetype forever; growing the chart surface is a
  reviewed allow-list change, not a new node file, new codegen, or new equivalence test.
- The model layer's honesty about heterogeneity (three archetypes, not one) means no family is
  contorted to fit a shape it doesn't have, keeping each family's spec and diagnostics legible on
  their own terms while still sharing one inspectable representation.
- Bayesian modeling is fully optional; the base install, its CI lane, and its install time are
  unaffected by the heavy PyMC/pytensor stack.

**Negative / obligations:**

- No individual chart gets bespoke, idiomatic codegen or a hand-tuned config panel — every
  generated chart script calls through `ef.viz.plot`, which this note accepts as the cost of
  catalog-wide equivalence-by-construction (mirroring ADR 0016's identical trade-off).
- The chart allow-list and the per-family model registries are now maintenance surface: every
  `plotly` bump or new statsmodels/Bambi capability requires a reviewed pass to decide what
  widens, exactly as ADR 0016 records for the sklearn allow-list.
- The three model archetypes' port shapes are load-bearing for every family built on them —
  changing one later means re-touching every already-generated model node's wiring and the Epic 3
  canvas edge-validation rules built on `StatsModel`.
- Formula assembly lives only inside the wrapper; any future formula-string entry point must
  route through the same normalization path rather than reimplementing formula construction.
- The Bayesian equivalence gate is only as strong as its fixed-seed/fixed-draws discipline; any
  Bayesian node that skips a required `seed`/`draws`/`chains` param breaks the determinism this
  note commits to.

**Deferred:**

- Formula-string entry for model specs (Decision 4) — needs its own validation and a
  formula-to-structured normalization step.
- The actual model and chart catalogs, the per-family wrappers, the generated catalog artifacts,
  and the parametrized equivalence matrix over both — Stories 2 through 11, which build on the
  architecture locked here.
- Time-series/forecasting models (ARIMA/state-space), survival analysis, causal inference
  (DoWhy), geospatial visualization, dashboard/report layout composition, and the raw-code escape
  hatch — all explicitly out of scope per the epic's Definition of Done.

## EDA: `auto_eda` vs. the full HTML profile

Story 11 ships two ways to explore a frame, and they are complements, not competitors.
`ef.stats.auto_eda` / the `stats.auto_eda` node is the **fast, canvas-native** EDA path: it
returns tidy summary frames (`profile`/`missingness`/`co_missingness`/`distribution_summary`/
`correlation`) plus a curated set of JSON-native `PlotSpec`s (distributions, correlation heatmap,
co-missingness heatmap), all
riding the same `ADR-0002` equivalence and `@public_op` inspectable-result-payload contracts as
every other node, composed from the existing `ef.stats`/`ef.viz` seams rather than a parallel
implementation. `ef.reports.generate_html_summary` (the ydata-profiling `report` node) remains
the **heavyweight, full-profile** option: a complete standalone HTML report, best for deep one-off
exploration outside the canvas result flow.

- Reach for `auto_eda` inside a graph/pipeline, and whenever you want inspectable frames + plots
  that the Results tab can render directly.
- Reach for the HTML profile when you want an exhaustive, shareable standalone report and don't
  need the output to flow into downstream nodes.
