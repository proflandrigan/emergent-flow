# Feature Gap Analysis: PyCaret vs. Emergent Flow

An inventory of features that [PyCaret](https://pycaret.org) provides which emergent flow does not (yet) offer. Intent is to inform roadmap/epic scoping, not to argue that every gap must be closed. emergent flow's philosophy is a composable graph IR of nodes; PyCaret is an opinionated, stateful, task-oriented pipeline engine. The gap themes below reflect that structural difference.

Method: emergent flow's node catalog (`emergentflow/nodes/examples/`), its `ef.*` public operations, and PyCaret 4.0's per-task API surface (`setup`, `create_model`, `compare_models`, etc. across Classification/Regression/Clustering/Anomaly/TimeSeries) were compared.

## High-level structural difference

- **PyCaret** is a single stateful `Experiment` object (one per task type) with a uniform verb surface over `sklearn.pipeline.Pipeline`. A `setup()` call configures preprocessing, train/test split, cross-validation folds, and optional experiment logging all at once; subsequent verbs (`compare_models`, `tune_model`, `predict_model`, ...) read that shared `_fit_state`.
- **emergent flow** has no `Experiment`/`setup()`. Preprocessing, splits, and CV are individual graph nodes composed by the user. This is a deliberate design difference (composability over opinionation), not a defect — but it means several "one call configures everything" PyCaret features have no direct equivalent.

## Feature gaps (PyCaret has, emergent flow does not)

### 1. Unified, opinionated `setup()` preprocessing pipeline

PyCaret's single `setup()` call bundles many preprocessing choices that emergent flow exposes only as separate nodes (or not at all). The ones with **no** direct emergent flow equivalent:

- **Rare-category handling** (`rare_to_value`, `rare_value`) — no equivalent node.
- **Multicollinearity removal** (`remove_multicollinearity`, `multicollinearity_threshold`) — no equivalent node (only plain correlation visualization exists).
- **Low-variance feature threshold** (`low_variance_threshold`) — no equivalent node.
- **Class-imbalance handling** (`fix_imbalance`, `fix_imbalance_method`, e.g. SMOTE) — no equivalent node.
- **Power transforms** (`transformation`, `transformation_method` Box-Cox / Yeo-Johnson) — no equivalent node.
- **Automatic text-column feature extraction** (`text_features`, `text_features_method` TF-IDF) — emergent flow has embeddings (`ef.embed`) but no automatic TF-IDF bag-of-words column pipeline.
- **Group feature handling** (`group_features`, `drop_groups`) — no equivalent node.
- **Custom pipeline step injection** (`custom_pipeline`, `custom_pipeline_position`) — emergent flow has `custom_code` but no slot to inject into a combined preprocessing pipeline.
- **Data profiling** (`profile`, `profile_kwargs`) — emergent flow has `eda_profile`/`auto_eda` but no inline profiling toggled from a setup step.

### 2. Ensembling / blending / stacking

- `ensemble_model` (bagging/boosting wrapper around a single estimator) — no equivalent node.
- `blend_models` (weighted average of multiple models) — no equivalent node.
- `stack_models` (stacking ensemble) — no equivalent node.

emergent flow has individual `fit_estimator`/`train_*` nodes and `compare_models`, but no metalevel ensemble operations that combine fitted models.

### 3. Model tuning beyond grid search

- `tune_model` (randomized / automated hyperparameter search with CV) — emergent flow has `grid_search` but no randomized/automated tuner.

### 4. Post-fit model operations

- `calibrate_model` (probability calibration) — no equivalent node.
- `optimize_threshold` (classification decision-threshold optimization) — no equivalent node.
- `finalize_model` (refit on the full dataset after CV) — no equivalent node (emergent flow `fit_estimator` fits once; no "fit on all data after validation" step).
- `convert_model` (export to ONNX/PMML) — no equivalent node.

### 5. Deployment scaffolding

- `deploy_model`, `create_api`, `create_docker`, `create_app` (one-call REST API / Docker / app scaffolding around a fitted model) — emergent flow has `save_model`/`load_model` and a local server, but no one-call model-serving scaffold.

### 6. Experiment tracking & registry

- `get_logs`, `get_leaderboard`, `save_experiment`, `load_experiment` — emergent flow has research/reproducibility/lineage artifacts (`emergentflow/research/`) but no per-experiment log/leaderboard/save-load-equivalent tied to a fitted model.
- `get_metrics`, `add_metric`, `remove_metric` (pluggable custom metric registry) — emergent flow has fixed metric sets in `ef.ml.evaluate`/`ef.eval`, no additive custom-metric registry.

### 7. Model / data governance checks

- `check_fairness` (fairness metrics) — no equivalent operation.
- `check_drift` (data/feature drift analysis) — no equivalent operation.
- `deep_check` — no equivalent operation.

### 8. Auto-ML

- `automl` (auto-select best model after `compare_models`) — emergent flow has `compare_models` but no auto-pick step.

### 9. Task-type gaps

- **Anomaly detection** as a first-class task type with its own `AnomalyExperiment` and `assign_model`/`plot_model` verbs. emergent flow has an `outlier_detect` archetype in `ef.ml` but not a dedicated, first-class anomaly task surface.
- **Clustering** with `assign_model` (hard label assignment) — emergent flow has a `cluster_detect` archetype but no separate `assign_model` labeling verb.
- **Time series**: `check_stats` (stationarity/seasonality checks), time-series-specific cross-validation / horizon, and TS `compare_models` — emergent flow has `forecast_arima`, `forecast_ets`, `seasonal_decompose` but no stationarity-check op or TS-specific CV.

### 10. Engine / hardware abstractions

- `get_allowed_engines`, `get_engine` (pluggable execution engines) — no equivalent.
- `use_gpu` (GPU-accelerated training) — no equivalent (emergent flow `torch` stays optional and is not wired to a training accelerator path).

## Things PyCaret has that emergent flow already covers (for completeness)

The following map to existing emergent flow nodes/ops and are **not** gaps:

- `compare_models` → `ef.ml.compare_models` / `compare_models` node.
- `create_model` / `fit` → `fit_estimator`, `train_*`, `fit_*` nodes.
- `predict_model` → `predict` / `predict.py` node.
- `evaluate_model` → `ef.ml.evaluate`, `eval_*` nodes.
- `interpret_model` (SHAP) → `explain_*` nodes.
- `plot_model` → `viz_*` nodes.
- `imputation` (numeric/categorical) → `impute` node.
- Encoding (one-hot / ordinal / target) → `encode_categorical`.
- Scaling / normalization → `scale_features`.
- Feature selection → `select_features`.
- Polynomial features → `generate_features`.
- Dimensionality reduction (PCA) → `reduce_dimensions`.
- Binning numeric features → `discretize`.
- Outlier removal → `detect_outliers` / `outlier_detect`.
- Date-component extraction → `parse_dates` components.
- Train/test split + CV → `train_test_split`, `cross_validate`.
- Embeddings → `ef.embed` / `embed_text`.

## Suggested roadmap lens

Highest-value gaps to consider closing (only if the roadmap wants them):

1. Ensembling / blending / stacking (compose fitted models — fits the graph IR well).
2. Post-fit ops: `calibrate_model`, `optimize_threshold`, `finalize_model`.
3. Class-imbalance handling (SMOTE) and rare-category handling in preprocessing.
4. Time-series `check_stats` (stationarity) and TS cross-validation.
5. Pluggable custom-metric registry + experiment log/leaderboard.
6. Auto-ML `automl` auto-pick after `compare_models`.