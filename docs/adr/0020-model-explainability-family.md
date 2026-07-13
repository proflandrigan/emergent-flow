# ADR 0020 — SHAP-based explainability and error analysis is a new `explain` family, a pure allow-listed reader of `ml.FittedModel`

- **Status:** Accepted
- **Date:** 2026-07-11
- **Deciders:** SDK maintainers (proflandrigan)

## Context

Once a user fits a model with `ml.fit_estimator` (Epic 8 / [ADR 0016](./0016-sklearn-estimator-adapter.md))
they have no way, inside the graph, to ask *why* it predicts what it predicts, which features drive it,
or where it is wrong. `ef.ml.evaluate` gives aggregate metrics only; `ef.ml.summarize` gives structural
model internals (coefficients, tree depth); there is no per-feature attribution and no per-row error
surface. SHAP (Lundberg & Lee, MIT license) is the standard tool for the former; predicted-vs-actual /
residual / calibration / worst-error views are the standard tool for the latter. Both read an
already-fitted `FittedModel` (`emergentflow/ml/registry.py`'s `estimator` dataclass) plus a `DataFrame`
and produce new, inspectable artifacts — no new fitting, no new IR node types beyond the usual
`NodeDefinition` contract.

Three forces shape the decision:

1. **Determinism (ADR 0002).** `shap.Explainer`'s fastest paths per estimator family are exact and
   deterministic (`TreeExplainer` for tree ensembles, `LinearExplainer` for linear models), but its
   general fallback (`PermutationExplainer`, used for SVMs, KNN, MLP, voting/stacking ensembles) samples
   a background dataset and permutes feature coalitions. Left unseeded, two runs over the same
   `(model, frame)` would disagree — breaking the `execute(ir) == compile_to_code(ir)` equivalence gate,
   which runs both paths and diffs the artifacts byte-for-byte. Every explainability node must therefore
   pin a `seed` and a bounded `background_samples`, exactly like `stats.fit_bayesian_model` pins
   `seed`/`draws`/`tune`/`chains` for MCMC determinism.
2. **Dependency weight (ADR 0007).** `shap` pulls in `numba`/`llvmlite` (a JIT toolchain) — too heavy for
   the base install. This is the same shape of problem `pymc`/`bambi`/`arviz` solved for the Bayesian
   family ([`emergentflow/stats/errors.py`](../../emergentflow/stats/errors.py)'s
   `MissingOptionalDependencyError` + `requires_extra` on `ModelSpec`): a base-install use of an
   explainability node must raise a typed, actionable error, never an opaque `ImportError`.
3. **No new effectful seam needed.** Unlike LLM calls (ADR 0017) or warehouse queries (ADR 0018), SHAP
   computation and the error/diagnostic views are pure, in-process, credential-free functions of
   `(model, frame)` — closer in shape to `stats.diagnostic` reading a `FittedStatsModel`'s residuals than
   to an injected client. `requires_client` stays `False` for every node in this family.

The rejected framing is folding these nodes into the existing `ml` family under a new category string.
The user directing this work wants explainability to read as **one discoverable group** in the node
palette and in `ef.*` — closer to how `stats`/`viz`/`ml` are already separate top-level families than to
another `ml` category alongside `Machine Learning`.

## Decision

**We will add `explain` as a fifth `ef.*` family: a pure, allow-listed reader of `ml.FittedModel` +
`DataFrame` that produces SHAP attributions, feature-importance/error-analysis plots, and a worst-error
table — gated behind a new `emergentflow[explain]` optional dependency (`shap`).**

1. **New top-level family, own category.** `emergentflow/explain/` is a new package, lazily imported as
   `ef.explain` exactly like `ef.stats`/`ef.ml`/`ef.viz` (`emergentflow/__init__.py`,
   `emergentflow/api.py`). Every node in this family sets `family = "explain"`,
   `category = "Model Explainability"`, and a `explain.<name>` type — a new, self-contained group in the
   node catalog/palette, not a subcategory of `"Machine Learning"`.

2. **Plot nodes live in `explain`, not `viz` — a deliberate, narrow exception to "plots live in `viz`".**
   Every existing model-aware plot (`viz.plot_coefficients`, `viz.plot_residuals`, `viz.plot_confusion_matrix`,
   …) lives in the `viz` family. This ADR keeps SHAP/error-analysis plots in `explain` instead, so a user
   exploring a model's behavior finds `shap_values`, `plot_shap_importance`, `plot_shap_beeswarm`,
   `plot_shap_waterfall`, `error_table`, `plot_predicted_vs_actual`, `plot_residuals`, `plot_calibration`,
   and `plot_roc_pr` as one adjacent group, not scattered across two palette categories. Every plot
   function still returns a `PlotSpec` (`emergentflow/viz/models.py`) built the same way `viz`'s plot
   functions build one — `emergentflow.explain` imports the `PlotSpec` **type** from `emergentflow.viz`
   (a data type, not behavior), exactly as `emergentflow.viz` already imports `FittedModel` from
   `emergentflow.ml`. No live matplotlib/shap figure object ever escapes a node's `execute`/`codegen`; shap's
   own (matplotlib-based) plotting functions are never called — every chart is rebuilt from raw SHAP
   values/error data via plotly, mirroring how `viz.plot_coefficients` rebuilds a forest plot from tidy
   coefficients rather than calling `statsmodels`' own plot helpers.

3. **A fast exact path for tree regressors; a uniform, seeded permutation path for everything else.**
   `emergentflow/explain/_shap.py` dispatches on `model.estimator_type`: a curated allow-list of
   pure tree ensembles (`RandomForest*`, `ExtraTrees*`, `GradientBoosting*`, `HistGradientBoosting*`,
   `DecisionTree*`) fit for **regression** uses `shap.TreeExplainer(model.estimator)` directly — exact,
   no background sampling, no seed needed, since the tree structure is walked exactly rather than
   estimated. Every other case — every classifier regardless of estimator type, and every non-tree
   regressor — goes through `shap.Explainer(predict_fn, background, seed=seed)`
   (`shap`'s `PermutationExplainer` under the hood), where `predict_fn` is `model.estimator.predict` for
   regression or a `predict_proba`-derived callable for classification. Classification is deliberately
   **never** routed through `TreeExplainer`, even for tree-based classifiers: `TreeExplainer` and the
   permutation path disagree on output units for a classifier (raw margin/log-odds vs. `predict_proba`
   probability space) unless `TreeExplainer` is additionally reconfigured with its own background data
   and `model_output="probability"` — at that point it has the same background-sampling dependency as
   the permutation path with none of its simplicity, so classification uniformly takes the
   `predict_proba` path instead. This keeps every classification SHAP value in one well-defined unit
   (probability) regardless of estimator, at the cost of not fast-pathing tree classifiers — a
   deliberate correctness-over-speed tradeoff (see Consequences). Every node that can hit the permutation
   path takes required `seed: int` and `background_samples: int` params (background rows are
   deterministically `frame[feature_names].sample(n=background_samples, random_state=seed)`, or the full
   frame if smaller); `execute` and `codegen` both route through the one `ef.explain.shap_values`
   wrapper, so ADR 0002 equivalence holds by construction exactly as every other archetype in this
   codebase achieves it — through one shared backend function, not through independent reimplementation
   in the two paths.

4. **SHAP output is a tidy, long-format DataFrame — one row per `(row_index, feature[, class])`.** Columns:
   `row_index` (position in the input frame), `feature`, `feature_value`, `shap_value`, `base_value`
   (repeated per row group; tidy over minimal, matching this codebase's existing diagnostic-frame
   convention), and `class` (only present for multiclass classifiers, one block of rows per class). Binary
   classification is treated as single-output — only the positive class's (`estimator.classes_[1]`)
   probability attribution is returned, with no `class` column — mirroring `ef.ml.evaluate`'s existing
   `pos_label = classes[1]` convention for binary metrics; regression is likewise single-output with no
   `class` column. This is the shape every downstream `explain.plot_shap_*` node consumes, and the shape a
   user can pivot/filter/`group_by_aggregate` with the existing transform nodes without a bespoke
   wide-matrix type.

5. **Scope is `ml.FittedModel` with `archetype="fit"` (supervised classification/regression) only.**
   `cluster_detect` (no meaningful "prediction" to attribute or err against) and `fit_transform`
   (`FittedTransformer`, no target) are out of scope, as is `stats.FittedStatsModel` (statsmodels/Bayesian
   results already have native coefficient-based interpretation via `viz.plot_coefficients` and are a
   different results object entirely). A node given the wrong kind of model raises a typed `ValueError`,
   mirroring `apply_estimator`'s `op`-vs-wrapper-kind checks.

6. **Error analysis dispatches on `model.task`.** `error_table` (worst-|residual| rows for regression;
   lowest-confidence/misclassified rows for classification), `plot_predicted_vs_actual` and `plot_residuals`
   (regression only), `plot_calibration` and `plot_roc_pr` (binary classification only, mirroring
   `ef.ml.evaluate`'s existing binary-only `roc_auc` gate) all raise a typed `ValueError` when called against
   the wrong `model.task`, rather than silently producing a nonsensical plot.

7. **`emergentflow/explain/errors.py` roots `ExplainError(ValueError)` and defines
   `MissingOptionalDependencyError(extra="emergentflow[explain]")`**, mirroring
   `emergentflow/stats/errors.py` exactly. `shap` is imported lazily, inside `_shap.py`'s explainer
   constructor, never at module import time — a bare `import emergentflow` and a bare `pip install
   emergentflow` stay light and shap-free (ADR 0007).

## Consequences

**Easier / positive**

- A user can go fit → explain → visualize entirely inside the canvas, with feature attribution and error
  surfacing as first-class, discoverable node types, without leaving the graph or writing SHAP boilerplate.
- ADR 0002 holds by construction: one shared backend per node, seeded/bounded wherever SHAP samples.
- The base install gains zero new hard dependencies; `emergentflow/explain/` is only ever imported on
  first access to `ef.explain` or when an `explain.*` node executes.
- The tidy long-format shap-values frame composes with every existing transform/viz node for free (filter
  to one feature, `group_by_aggregate` by class, feed a custom plot) — no bespoke matrix type to special-case
  through the codegen/execute pipeline.

**Harder / negative**

- `PermutationExplainer`'s background-sampling determinism is a real constraint: a `seed`/
  `background_samples` change (or an upstream frame change) changes results, and golden/equivalence
  fixtures for non-tree estimators must be re-recorded accordingly, mirroring the Bayesian family's
  MCMC-fixture-maintenance cost.
- Tree-based classifiers (`RandomForestClassifier`, `GradientBoostingClassifier`, …) do NOT get
  `TreeExplainer`'s speed/exactness advantage — clause 3's correctness-over-speed tradeoff routes every
  classifier through the same seeded permutation path a plain `LogisticRegression` would use, so a
  large-forest classifier's SHAP computation is slower than it needs to be. Revisiting this (e.g.
  `TreeExplainer(..., model_output="probability")` with its own seeded background) is a scoped,
  additive follow-up if that latency becomes a real complaint.
- Plot nodes living in `explain` rather than `viz` is an intentional, narrow asymmetry from the rest of the
  codebase's "all plots live in `viz`" convention — documented here so it reads as a deliberate choice, not
  drift, the next time a new model-aware plot family is added.
- Beeswarm has no native plotly chart type; `plot_shap_beeswarm` reimplements it as a jittered strip plot
  (one marker per `(row, feature)`, y-jittered within each feature's row, colored by normalized
  `feature_value`) rather than calling shap's own matplotlib beeswarm — more implementation surface than the
  bar/waterfall plots, and a candidate for follow-up visual polish.

**Deferred**

- **Dependence plots** (SHAP value vs. one feature's raw value, optionally colored by an interacting
  feature) are useful but explicitly out of v1 scope; a future `explain.plot_shap_dependence` node is
  additive and needs no changes to this ADR.
- **`stats.FittedStatsModel` explainability** (SHAP over statsmodels/Bayesian results) is deferred; those
  models already expose native coefficient interpretation and would need a different explainer strategy
  (no `.predict_proba`-shaped sklearn interface to hand `shap.Explainer`).
- **Error-by-segment breakdown** (bucketing a chosen feature and reporting mean error per bucket) was
  scoped out of v1 in favor of the worst-error table and predicted-vs-actual/residual/calibration/ROC-PR
  plots; it is a natural, additive follow-on `explain.error_by_segment` node.
