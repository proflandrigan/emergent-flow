# Epic 8 — Complete scikit-learn Support (Supervised & Unsupervised)

> **Repo ↔ roadmap numbering.** Epic files are numbered by **delivery order in this repo**; the
> [technical roadmap](../planning_docs/technical_roadmap.md) numbers epics **globally**. This file
> is repo **Epic 8**. It is the deliberate *deep* build-out of the classical-ML branch that repo
> **Epic 6** (roadmap **Epic 4**, Node Library & Configuration UX) intentionally left shallow —
> Epic 6 Story 6 shipped a demo-sized `ef.ml` slice (`train_test_split`, `train_regressor`,
> `train_random_forest`, `predict`, `evaluate`) and explicitly deferred "the full estimator
> catalog." This epic delivers that catalog. **Always qualify "repo Epic N" vs "roadmap Epic N"** —
> see [`epics/README.md`](./README.md).

> **The one place we reverse the "narrow, not exhaustive" stance — on purpose.** Every prior epic
> ships *the smallest useful set* and treats the catalog as unbounded (Epic 6, Notes). scikit-learn
> is the exception where completeness is the *point*: users expect "if it's in sklearn, it's a
> node." Hand-authoring one node file per estimator — each with its own golden + ADR-0002
> equivalence test — does **not** scale to sklearn's ~200 estimators and would be forever-maintained
> surface. So the strategy is **not** "write N node files." It is: build **one generic
> estimator-adapter** and a **small set of node archetypes** (fit / transform / cluster+detect /
> apply), then **generate the catalog** from sklearn's own introspection. Breadth becomes data, not
> code. `codegen` and `execute` both route through the single adapter wrapper, so ADR-0002
> equivalence holds **by construction across the whole catalog** — the same trick the reference
> nodes use, applied once instead of N times.

**Phase:** Follows repo Epic 6 (node library data path + `Model` type token + `FittedModel`
representation already exist). Sequenced after Epic 6 Story 2 (catalog-as-data) and Story 6
(`Model`-bearing ports), which this epic depends on and generalizes.
**Lives in:** `emergentflow/` — the SDK tree owns the estimator adapter (`emergentflow/ml/`), the new
node archetypes (`emergentflow/nodes/`), the generated catalog entries, and the type tokens. The
canvas palette + config panels (`ui/`, repo Epic 5 Stories 3–4) **only consume** the generated
catalog — no per-estimator UI is written here.
**Dependencies:** Epic 1 (node contract, param schema, registry, `@register`), Epic 2
(`compile_to_code` / `execute` + the golden/equivalence harness), Epic 3 / roadmap 5 (type tokens +
rules-as-data so `Model`/`Transformer` ports validate), Epic 6 (catalog-as-data export;
`FittedModel` model representation; `ef.ml` seam; `Model` type token). scikit-learn (>=1.4,
BSD-3-Clause) is already a runtime dep — **no new dependency is introduced**.
**Blocks:** roadmap Epic 8 (rich result rendering — cluster plots, confusion matrices, PCA scatter
land as the catalog emits their inspectable payloads), roadmap Epic 12 (the NL→graph agent's
quality ceiling rises with catalog breadth), roadmap Epic 14 (model persistence — a fitted-model
export path this epic scopes but defers).

---

## Definition of Done (epic-level)

- [ ] **Coverage:** every sklearn estimator that exposes the standard `fit` + (`predict` |
  `transform` | `fit_predict` | `score_samples`) protocol is reachable as a node — supervised
  (classification, regression), and unsupervised (clustering, decomposition/dimensionality
  reduction, manifold, mixture, preprocessing, feature selection, outlier/novelty detection) — via
  a **small fixed set of archetype nodes** + a generated catalog, **not** one file per estimator.
- [ ] **ADR-0002 holds for the whole catalog by construction:** one adapter wrapper
  (`ef.ml.fit_estimator` / `ef.ml.apply_estimator` or equivalent) is called identically by
  `codegen` (emitted as an `ef.*` call) and `execute`. A **parametrized equivalence harness** proves
  it over a representative estimator matrix, not one bespoke test per estimator.
- [ ] **Both functions stay pure** (no I/O, no global state) — model handles flow in-memory under
  `execute` and as plain variables in compiled code; all persistence stays in `export.py` (ADR 0002,
  the Epic 6 sandboxing prerequisite).
- [ ] **`@public_op` inspectable contract respected:** a live estimator is never dumped into a
  response. Fitted estimators ride inside the existing `FittedModel` (or a new `FittedTransformer`)
  dataclass whose live-object field degrades to `{"kind": "unsupported"}` on the result-payload
  contract; every node returns JSON-native / tidy-DataFrame inspectable summaries.
- [ ] **New type tokens registered** (`Transformer`, `ClusterModel`/reuse of `Model`) with
  compatibility rules (Epic 3) so a scaler wires into `transform` but not into a `DataFrame` input,
  and a fitted clusterer does not wire into `predict`-for-supervised.
- [ ] **Catalog is generated + versioned:** estimator entries are produced from sklearn
  introspection (params, defaults, docstring summaries) into the Epic 6 catalog-as-data artifact,
  with a **golden test** and a **curation/allow-list** so we ship a stable, deterministic set (not
  whatever the installed sklearn version happens to expose).
- [ ] **License hygiene:** scikit-learn / scipy only (both BSD-3-Clause). **No GPL** deps
  (`docs/licensing-and-dependencies.md`) — no auto-sklearn, no imbalanced-learn-via-GPL, etc.
- [ ] **Acceptance demo:** a supervised pipeline (scale → select-k-best → gradient-boosting →
  evaluate) **and** an unsupervised pipeline (scale → PCA → KMeans → cluster-summary) both build on
  the canvas, compile to `.py`, and execute end-to-end (Story 10).
- [ ] **Explicitly out of scope:** DL estimators (roadmap Epic 10), GenAI (Epic 11), on-disk model
  persistence/serving (roadmap Epic 14 — the *representation* is settled here, the export path is
  deferred), and the raw-code escape hatch (decided-and-deferred in Epic 6 Story 1).

---

## Story 1 — Lock the estimator-adapter architecture

> Cheap to decide, expensive to retrofit across ~200 estimators. Write an ADR
> (`docs/adr/0016-sklearn-estimator-adapter.md`) capturing these before building.

- [x] **Adapter over per-node files.** Decide: breadth is delivered by a **generic adapter** +
  **archetype nodes** + a **generated catalog**, not one hand-written `NodeDefinition` per
  estimator. Record the trade-off (uniformity + ADR-0002-by-construction vs. bespoke per-estimator
  ergonomics) and why uniformity wins at this scale.
- [x] **Estimator identity is a param, not a node type.** An estimator node's `type` is its
  archetype (e.g. `ml.fit_estimator`); *which* sklearn class it fits is a validated `estimator`
  param (`"RandomForestClassifier"`, `"KMeans"`, …) resolved through a curated **allow-list
  registry** (import path + accepted kwargs). This keeps the node `type` set tiny and the catalog
  data-driven.
- [x] **The four archetypes.** Fix the port shapes now:
  - **fit (supervised):** `DataFrame(+target param)` → `Model` — classifiers/regressors.
  - **fit_transform (unsupervised transformer):** `DataFrame` → `Transformer` + `DataFrame` —
    scalers, encoders, PCA/decomposition, manifold, feature-selection.
  - **cluster/detect (unsupervised label/score):** `DataFrame` → `Model` + `DataFrame` (with a
    `cluster`/`anomaly_score` column) — KMeans/DBSCAN/GMM, IsolationForest/LOF.
  - **apply:** `predict` / `transform` / `evaluate` consume a fitted `Model`/`Transformer` + a
    `DataFrame`.
- [x] **Codegen readability policy.** Decide: emit `ef.ml.fit_estimator(frame, estimator=..., ...)`
  (equivalence-by-construction, the default) — and record "transparent codegen" (emitting native
  `sklearn.ensemble.RandomForestClassifier(...)` for prettier scripts) as a **deferred enhancement**
  that would need its own per-estimator equivalence proof.
- [x] **Curation policy.** The catalog is pinned to a **curated allow-list**, not
  `sklearn.utils.all_estimators()` at runtime, so the node set is deterministic and version-stable
  (mirrors Epic 6's "catalog is versioned" decision). New sklearn versions widen the list via a
  reviewed change, not automatically.
- [x] **Param-surface policy.** Decide which constructor kwargs are exposed per estimator (curated
  "common" kwargs with defaults/help/hints) vs. an `advanced_params: dict` passthrough for the long
  tail — so the config panel stays legible without hiding capability.

---

## Story 2 — The estimator adapter + allow-list registry (`emergentflow/ml/`)

> Build the single wrapper that every archetype node routes through. This is the load-bearing seam:
> get it right and the whole catalog inherits ADR-0002 equivalence and the inspectable contract.

- [ ] Define an **estimator registry**: `{estimator_key -> EstimatorSpec}` where `EstimatorSpec`
  carries import path, sklearn class, archetype (fit/transform/cluster), accepted kwargs (with
  defaults + hints scraped/curated from the class), and the produced inspectable-summary builder.
- [ ] `ef.ml.fit_estimator(frame, *, estimator, target=None, features=None, params={}) -> FittedModel`
  — validates the estimator key + kwargs against the registry, resolves features/target the same way
  the existing `train_*` wrappers do, fits, and wraps the live estimator in `FittedModel`
  (extend/reuse the Epic 6 dataclass; add a `FittedTransformer` sibling for the transform archetype).
- [ ] `ef.ml.apply_estimator(model, frame, *, op)` covering `predict` / `transform` /
  `score_samples`, returning a **new** frame (never mutate input) — the apply archetype's backend.
- [ ] Every wrapper is a `@public_op` returning an **inspectable** value (metrics dataclass /
  tidy DataFrame / the `FittedModel` dataclass). Confirm the live-estimator field degrades correctly
  under the result-payload contract (Epic 6 Story 6 precedent).
- [ ] Unit tests on the adapter itself: unknown estimator key → typed error; bad kwargs → typed
  error; determinism given `random_state`; no input mutation.

---

## Story 3 — Type tokens & inspectable summaries per family

> Structural validation and rendering both key off type tokens + the shape of the summary. Register
> them before the catalog widens so every generated node validates and renders for free.

- [ ] Register `Transformer` (fitted preprocessing/decomposition state) and confirm/rename the
  `Model` token so ports distinguish "predictor" from "transformer" from "clusterer" (Epic 3
  rules-as-data; add compatibility rows to `docs/type-system-spec.md`).
- [ ] **Inspectable summary builders** per family, all JSON-native / tidy-DataFrame:
  - classifier: accuracy/report, classes, feature importances or coefficients.
  - regressor: r²/mae/rmse, coefficients or importances.
  - decomposition/PCA: explained variance ratio, components, n_components.
  - clustering: cluster sizes, inertia/silhouette (where defined), n_clusters, labels frame.
  - outlier/novelty: contamination, score distribution summary.
  - preprocessing: fitted stats (means/scales/categories) as a tidy frame.
- [ ] Extend `ef.ml.evaluate` metric coverage to be **task-aware** (multiclass classification
  report, ROC-AUC where binary+proba available; regression already covered) — still returning the
  `EvaluationResult` inspectable shape.

---

## Story 4 — Supervised catalog: classifiers & regressors (fit archetype)

> The largest, highest-value family. Delivered by the fit archetype + generated catalog entries — no
> new node files per estimator.

- [ ] Curate the supervised allow-list into the registry: linear
  (Logistic/Ridge/Lasso/ElasticNet/SGD/LinearSVC/SVR), tree & ensemble
  (DecisionTree, RandomForest, ExtraTrees, GradientBoosting, HistGradientBoosting, AdaBoost, Bagging),
  neighbors (KNeighbors), naive Bayes (Gaussian/Multinomial), SVM (SVC/SVR), plus discriminant
  analysis — each with curated common kwargs + `advanced_params` passthrough.
- [ ] Generate their catalog entries (label/category/description/param schema) from Story 6's
  generator; they light up the palette with zero per-estimator UI.
- [ ] Golden-code test on a **representative subset** (one per estimator kind) + the parametrized
  equivalence harness (Story 9) covering the whole allow-list. **Deferred:** hyperparameter search
  (Story 8), calibration, class-imbalance tooling.

---

## Story 5 — Unsupervised transformers: preprocessing, decomposition, manifold, feature selection (fit_transform archetype)

> Transformers are the glue that makes estimators usable (scaling, encoding) *and* a whole
> unsupervised surface (PCA, t-SNE, feature selection). One archetype, generated entries.

- [ ] Registry entries for: preprocessing (StandardScaler, MinMaxScaler, RobustScaler,
  Normalizer, OneHotEncoder, OrdinalEncoder, PolynomialFeatures), decomposition
  (PCA, TruncatedSVD, NMF, FastICA, FactorAnalysis), manifold (TSNE, Isomap — fit_transform only,
  no `transform` on new data where sklearn lacks it), and feature selection
  (SelectKBest, VarianceThreshold, RFE, SelectFromModel).
- [ ] The `fit_transform` node emits `Transformer` + a transformed `DataFrame`; a companion
  `ml.transform` apply node reuses a fitted `Transformer` on new data (skip/flag estimators that
  don't support out-of-sample `transform`).
- [ ] Golden + equivalence via the Story 9 harness. **Deferred:** `ColumnTransformer` /
  per-column routing (folds into Story 8 pipelines), custom function transformers (needs the
  escape-hatch decision).

---

## Story 6 — Unsupervised: clustering, mixture & outlier/novelty detection (cluster/detect archetype)

> The "no target" learners that produce labels or scores rather than a predictor.

- [ ] Registry entries for clustering (KMeans, MiniBatchKMeans, DBSCAN, AgglomerativeClustering,
  SpectralClustering, MeanShift, Birch), mixture (GaussianMixture, BayesianGaussianMixture), and
  outlier/novelty (IsolationForest, LocalOutlierFactor, OneClassSVM, EllipticEnvelope).
- [ ] The cluster/detect node emits a `Model` + a `DataFrame` with a `cluster` (or `anomaly_score`)
  column, plus the family's inspectable summary (sizes, inertia/silhouette, contamination).
- [ ] Handle the `fit_predict`-only estimators (DBSCAN/LOF) explicitly — they don't produce a
  reusable predictor for new rows; the node exposes labels, and `predict`-on-new-data is disabled in
  the catalog for them (validation, not a runtime surprise).
- [ ] Golden + equivalence via the Story 9 harness.

---

## Story 7 — Catalog generation from sklearn introspection

> Turn the registry into Epic 6 catalog-as-data entries deterministically. This is what makes
> "complete support" a data artifact rather than N hand-written files.

- [ ] A pure generator maps each `EstimatorSpec` → a catalog entry (`type` = archetype, plus
  `estimator` key, curated per-param `{type, default, help, hints}`, `label`, `category`,
  `description` — descriptions summarized from the sklearn docstring first line, curated, not raw).
- [ ] Entries feed `ef.export_catalog()` (Epic 6 Story 2) — **golden test** with stable ordering;
  the generated set is pinned to the curated allow-list so output is independent of the installed
  sklearn's estimator enumeration.
- [ ] Document the generation + curation process in `docs/` next to the catalog-as-data contract,
  including how to add an estimator (allow-list edit + regenerate golden), so it's a reviewed change,
  not automatic.

---

## Story 8 — Pipelines & model selection *(stretch / gated)*

> Composing estimators (Pipeline) and searching hyperparameters (GridSearchCV) is part of "complete"
> sklearn use, but it is a distinct graph-shape problem — sequence a chain of fitted steps — and can
> ship after the estimator surface. Gate it behind Stories 2–7 landing.

- [ ] A `ml.pipeline` node (or graph-native chaining convention) that fits an ordered sequence of
  transformer steps + a final estimator, emitted through the adapter so ADR-0002 still holds.
- [ ] `ml.grid_search` / `ml.cross_validate` returning **inspectable** CV results (best params, per-
  fold scores as a tidy frame) — the fitted best-estimator rides in `FittedModel`.
- [ ] Golden + equivalence via the Story 9 harness. **Deferred:** nested CV, `ColumnTransformer`
  routing, randomized/Bayesian search backends beyond sklearn's built-ins.

---

## Story 9 — Equivalence & golden testing at scale

> ADR-0002 is a CI gate. With a generated catalog we prove it with a **parametrized/property-based
> harness over the estimator matrix**, not one bespoke test per estimator — otherwise the test suite
> becomes the maintenance sink the adapter was meant to avoid.

- [ ] A `pytest.mark.parametrize` (or `hypothesis`) matrix over the allow-list that, for each
  estimator: builds a minimal graph, asserts `execute(ir)` artifacts ≈ running
  `compile_to_code(ir)` on a fixed sample frame (the ADR-0002 equivalence property), keyed on the
  inspectable summary so opaque estimator internals aren't compared.
- [ ] Golden tests on **generated code** for a representative estimator per archetype (readable,
  ruff-clean, importable) — not one golden per estimator.
- [ ] Fixed seeds + fixed sample datasets so the matrix is deterministic; gate it in
  `.github/workflows/ci.yml` alongside the existing equivalence gate. Keep the torch-style
  `importorskip` discipline where an estimator needs an optional extra.

---

## Story 10 — Wire into the canvas + acceptance demo

> The payoff: the generated catalog drives the palette with zero per-estimator UI, and real
> supervised + unsupervised pipelines run end-to-end.

- [ ] The canvas palette (repo Epic 5 Story 3) renders every generated estimator entry; config
  panels (Story 4) render curated kwargs + the `advanced_params` passthrough with **zero per-node UI
  code**. Confirm `Model`/`Transformer`-bearing edges validate on the canvas (Epic 3 rules).
- [ ] Round-trip canvas → IR → `/compile` → downloadable `.py` and `/execute` with per-node status,
  including a `Transformer`-bearing edge and a `Model`-bearing edge.
- [ ] **Acceptance demo (supervised):** `load_sample → drop_missing → StandardScaler →
  SelectKBest → GradientBoostingClassifier → evaluate` runs to metrics on the canvas.
- [ ] **Acceptance demo (unsupervised):** `load_sample → StandardScaler → PCA → KMeans →
  cluster-summary` runs to a labeled frame + inspectable cluster summary on the canvas.
- [ ] Document both as the "classical ML the app can do today" reference, superseding the Epic 6
  demo-sized `ef.ml` slice.

---

## Notes / Risks (carry into planning)

- **The adapter is the whole bet.** If estimator identity is a node `type` instead of a param, you
  are back to ~200 hand-maintained files and ~200 equivalence tests. Keep the node `type` set tiny
  (the four archetypes) and push breadth into curated *data*. This is the single decision that makes
  the epic tractable — protect it in review.
- **ADR-0002 must stay by-construction.** Both paths route through one adapter wrapper. Resist the
  temptation to emit native `sklearn.*(...)` in codegen for prettier scripts — that reintroduces a
  per-estimator equivalence obligation. "Transparent codegen" is a *deferred* enhancement (Story 1),
  not a shortcut.
- **Purity is non-negotiable (Epic 6 sandboxing depends on it).** Fitted models flow in-memory under
  `execute` and as plain variables in compiled code; no pickling, no disk I/O in the adapter. Model
  persistence is roadmap Epic 14 — settle the `FittedModel` *representation* here, defer the export
  path.
- **The inspectable contract is the sharp edge for unsupervised learners.** A fitted `KMeans` or
  `PCA` is not JSON-native. Every archetype must return a curated inspectable summary; never let a
  live estimator reach the result-payload contract (Epic 6 Story 6 precedent — degrade to
  `{"kind": "unsupported"}`).
- **Curate, don't enumerate.** `all_estimators()` at runtime makes the catalog non-deterministic and
  couples it to the installed sklearn version — breaking the golden test and the versioned-catalog
  invariant. Pin an allow-list; widen it by reviewed change.
- **License hygiene still applies.** sklearn + scipy only (both BSD). The temptations here — auto-ml
  (auto-sklearn), imbalanced-learn extras, xgboost/lightgbm — each need a license + dependency review
  before entering; several are out of scope entirely (DL/boosting-libs = roadmap Epic 10).
- **Param surface is a UX risk, not just a coverage one.** Exposing every sklearn kwarg makes config
  panels unusable; exposing too few hides capability. The curated-common + `advanced_params`
  passthrough split (Story 1) is the compromise — validate it against the acceptance demos.
- **Don't drift into adjacent epics.** Rich cluster/confusion-matrix rendering is roadmap Epic 8
  (return the inspectable payload, let the UI render it); DL/boosting libraries are Epic 10; model
  serving is Epic 14; connectors are Epic 9.

---

*How to use this file: tick each `- [ ]` to `- [x]` as work completes. A story is done when all its
tasks are checked; the epic is done when the Definition of Done checklist is complete.*
