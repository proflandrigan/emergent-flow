# Machine Learning

Emergent Flow's `ef.ml` family is a thin wrapper over scikit-learn for classical machine
learning: train/test splitting, fitting curated estimators, prediction, evaluation, model
comparison, hyperparameter search, pipelines, and clustering. Every operation returns an
inspectable result — never a raw sklearn model on its own — so you can print/plot metrics,
predictions, and fitted-model metadata at every step. This guide walks through the family end
to end, showing DataFrame shapes and example output along the way.

## Setup

```python
import emergentflow as ef

df = ef.data.load_sample("iris")
print(df.shape)  # (150, 5)
print(df.columns.tolist())
# ['sepal length (cm)', 'sepal width (cm)', 'petal length (cm)', 'petal width (cm)', 'target']
```

## 1. Train/Test Split

```python
train_df, test_df = ef.ml.train_test_split(df, test_size=0.25, random_state=0)
print(f"Train: {train_df.shape}, Test: {test_df.shape}")
# Train: (112, 5), Test: (38, 5)
```

`train_test_split` is a thin wrapper over `sklearn.model_selection.train_test_split`: it returns
two NEW DataFrames (with reset indices), deterministic given `random_state`, and never mutates
`df`.

## 2. Quick Classification

`train_classifier` is the fastest path to a baseline model: it fits a logistic-regression
classifier on `df` and returns a `ClassifierResult` — an inspectable dataclass of metrics, never
the fitted estimator itself.

```python
result = ef.ml.train_classifier(df, target="target")
print(f"Accuracy: {result.accuracy:.2%}")
print(f"Classes: {result.classes}")
print(f"Features: {result.feature_names}")
print(f"Coefficients shape: {len(result.coefficients)} x {len(result.coefficients[0])}")
```

```
Accuracy: 96.05%
Classes: ['0', '1', '2']
Features: ['sepal length (cm)', 'sepal width (cm)', 'petal length (cm)', 'petal width (cm)']
Coefficients shape: 3 x 4
```

`ClassifierResult` fields: `accuracy` (held-out accuracy on an internal split), `n_train`/`n_test`
(split sizes), `classes` (label order matching the rows of `coefficients`), `feature_names`
(column order matching the columns of `coefficients`), and `coefficients` (one row per class, one
column per feature). `features` defaults to every column except `target` when not given.

## 3. The Curated Estimator Adapter (`fit_estimator`)

`fit_estimator` is the universal entry point for fitting any curated, allow-listed sklearn
estimator. The `estimator` argument is a string key that must match a registered entry in the
estimator registry (`emergentflow/ml/registry.py`/`catalog.py`) — an unregistered key raises
`UnknownEstimatorError`, and an unknown `params` key raises `InvalidEstimatorParamsError`.
Depending on the estimator's registered archetype, it returns either a `FittedModel`
(supervised classifiers/regressors, or clustering/mixture/outlier `cluster_detect` estimators)
or a `FittedTransformer` (unsupervised transformers like scalers or `PCA`).

### Classification

```python
model = ef.ml.fit_estimator(df, estimator="LogisticRegression", target="target")
print(type(model))              # <class 'emergentflow.ml.FittedModel'>
print(model.estimator_type)     # "LogisticRegression"
print(model.task)               # "classification"
print(model.feature_names)      # ['sepal length (cm)', 'sepal width (cm)', ...]
print(model.target)             # "target"
```

`FittedModel` carries the metadata needed to use the fitted estimator downstream without ever
exposing the live sklearn object as the return value: `estimator_type` (the curated key),
`task` (`"classification"`, `"regression"`, or `"clustering"`), `feature_names` (the columns it
was trained on, in order), and `target` (the trained target column, or `None` for a
`cluster_detect`-archetype model).

### Regression

The curated registry's linear-model key for regression is `"Ridge"` (L2-regularized linear
regression); a plain, unregularized ordinary-least-squares fit is available via
`ef.ml.train_regressor` if you don't need the curated-estimator machinery.

```python
diabetes = ef.data.load_sample("diabetes")
model = ef.ml.fit_estimator(
    diabetes,
    estimator="Ridge",
    target="target",
    features=["bmi", "s5", "bp"],
)
```

### With custom params

```python
model = ef.ml.fit_estimator(
    df,
    estimator="RandomForestClassifier",
    target="target",
    params={"n_estimators": 200, "random_state": 42},
)
```

`params` keys are validated against that estimator's own accepted-kwargs allow-list — passing an
unsupported key (or one meant for a different estimator) raises `InvalidEstimatorParamsError`
rather than silently being ignored or forwarded straight to sklearn.

## 4. Predict & Evaluate

```python
# Predict on test data
predictions = ef.ml.predict(model, test_df)
print(predictions.columns.tolist())
# ['sepal length (cm)', 'sepal width (cm)', 'petal length (cm)', 'petal width (cm)',
#  'target', 'prediction']
print(predictions[["target", "prediction"]].head())
```

| target | prediction |
| ---: | ---: |
| 1 | 1 |
| 0 | 0 |
| 2 | 2 |
| 1 | 1 |
| 0 | 0 |

`predict` returns a NEW DataFrame (`test_df` is never mutated) with a `prediction` column
appended; it validates that every `model.feature_names` column is present in `df` first.

```python
# Evaluate
result = ef.ml.evaluate(model, test_df)
print(f"Task: {result.task}")
print(f"N: {result.n}")
print(f"Metrics: {result.metrics}")
# Task: classification
# N: 38
# Metrics: {'accuracy': 0.97, 'precision_macro': 0.97, 'recall_macro': 0.97, 'f1_macro': 0.97, ...}
```

`evaluate` returns an `EvaluationResult` (`task`, `n`, `metrics`). Regression models report `r2`,
`mae`, `rmse`; classification models always report `accuracy`, plus `precision`/`recall`/`f1`
for binary targets (or their `_macro`/`_weighted` variants for multiclass targets, as in the
iris example above) and `roc_auc` when the estimator supports `predict_proba` on a binary
target.

## 5. Compare Models

`compare_models` cross-validates every curated estimator matching a task and ranks them — a
PyCaret-style "run every baseline and see which wins" step.

```python
comparison, best_model = ef.ml.compare_models(df, task="classification", target="target")
print(comparison[["estimator", "accuracy", "f1", "status"]])
```

| estimator | accuracy | f1 | status |
| --- | ---: | ---: | --- |
| LogisticRegression | 0.973 | 0.973 | ok |
| RandomForestClassifier | 0.960 | 0.960 | ok |
| SVC | 0.953 | 0.953 | ok |
| KNeighborsClassifier | 0.947 | 0.947 | ok |
| GaussianNB | 0.933 | 0.933 | ok |

`comparison` is a tidy DataFrame, one row per candidate estimator (defaulting to every curated
`fit`-archetype estimator whose registered `task` matches), sorted best-first. A `status` column
records `"ok"` or the first line of the failure — one incompatible estimator degrades to a NaN
row rather than aborting the whole comparison. `best_model` is a `FittedModel` wrapping the
top-ranked estimator, refit on the full `df` — ready to use directly with `evaluate`/`predict`.

```python
# Regression comparison
diabetes = ef.data.load_sample("diabetes")
comparison, best = ef.ml.compare_models(diabetes, task="regression", target="target")
print(comparison[["estimator", "r2", "mae", "rmse"]])
```

| estimator | r2 | mae | rmse |
| --- | ---: | ---: | ---: |
| Ridge | 0.457 | 44.2 | 54.1 |
| RandomForestRegressor | 0.431 | 45.9 | 55.4 |
| ElasticNet | 0.144 | 55.7 | 68.0 |

## 6. Grid Search

```python
model, cv_results = ef.ml.grid_search(
    df,
    estimator="RandomForestClassifier",
    target="target",
    param_grid={"n_estimators": [50, 100, 200], "max_depth": [3, 5, None]},
    cv=5,
)
print(cv_results[["param_n_estimators", "param_max_depth", "mean_test_score", "rank_test_score"]])
```

| param_n_estimators | param_max_depth | mean_test_score | rank_test_score |
| ---: | ---: | ---: | ---: |
| 200 | 5 | 0.967 | 1 |
| 100 | 5 | 0.960 | 2 |
| 100 | None | 0.953 | 3 |
| 50 | 3 | 0.947 | 4 |

`grid_search` is a thin wrapper over `sklearn.model_selection.GridSearchCV`: it fits every
combination in `param_grid` (keys validated against the estimator's accepted-kwargs allow-list)
via `cv`-fold cross-validation and refits the best-scoring combination on the full `df`. Returns
`(model, cv_results)` — `model` is a `FittedModel` wrapping the best-scoring estimator, and
`cv_results` is a tidy DataFrame, one row per parameter combination, sorted by rank.

## 7. Cross-Validation

```python
cv_df = ef.ml.cross_validate(
    df,
    estimator="LogisticRegression",
    target="target",
    cv=5,
)
print(cv_df)
```

| fold | test_score | fit_time | score_time |
| ---: | ---: | ---: | ---: |
| 0 | 1.000 | 0.012 | 0.002 |
| 1 | 0.967 | 0.011 | 0.002 |
| 2 | 0.933 | 0.011 | 0.002 |
| 3 | 0.967 | 0.010 | 0.002 |
| 4 | 1.000 | 0.011 | 0.002 |

Unlike `grid_search`, `cross_validate` produces no reusable `FittedModel` — it's a pure
evaluation step over a single, fixed-hyperparameter estimator, one row per fold.

## 8. Pipelines

```python
model = ef.ml.fit_pipeline(
    df,
    target="target",
    steps=[
        {"estimator": "StandardScaler"},
        {"estimator": "LogisticRegression", "params": {"max_iter": 500}},
    ],
)
# model is a FittedModel wrapping an sklearn Pipeline
predictions = ef.ml.predict(model, test_df)
```

`steps` is an ordered list of `{"estimator": <key>, "params": {...}}` dicts. Every step but the
last must be a `fit_transform`-archetype estimator (a scaler, encoder, decomposition step, ...);
the final step must be a `fit` (supervised) or `cluster_detect` (unsupervised) archetype
estimator. The whole chain is composed into ONE `sklearn.pipeline.Pipeline`, riding inside a
single `FittedModel` — so `predict`/`evaluate`/`apply_estimator` work against it exactly as they
would against any single fitted estimator.

## 9. Clustering

```python
model, labeled_df = ef.ml.fit_and_label(
    df,
    estimator="KMeans",
    features=["sepal length (cm)", "sepal width (cm)", "petal length (cm)", "petal width (cm)"],
    params={"n_clusters": 3, "random_state": 0},
)
print(labeled_df[["sepal length (cm)", "cluster"]].head())
```

| sepal length (cm) | cluster |
| ---: | ---: |
| 5.1 | 1 |
| 4.9 | 1 |
| 4.7 | 1 |
| 4.6 | 1 |
| 5.0 | 1 |

`fit_and_label` fits a curated `cluster_detect`-archetype estimator (clustering, mixture, or
outlier/novelty detection) and immediately labels the SAME frame it fit on, since several
clustering estimators (`DBSCAN`, `AgglomerativeClustering`, `SpectralClustering`) have no
separate `.predict()` for new data — sklearn only ever gives you the labels computed at fit
time. Returns `(model, labeled_df)`: `labeled_df` is a NEW frame with an added `cluster` column;
`df` itself is never mutated.

## 10. Model Summary

```python
summary = ef.ml.summarize(model)
print(summary)
```

`summarize` looks up the fitted estimator's registered summary builder and returns a structural,
inspectable dict describing it (e.g. cluster centers and sizes for `KMeans`, coefficients and
intercept for a linear model) — `{"kind": "unsupported"}` if no summary builder is registered
for that estimator type. Like every other `ef.ml` result, this keeps the live estimator out of
the return value.

## 11. In the Canvas

> **In the Canvas:** Add a `load_sample` node → `train_test_split` node → `fit_estimator` node
> (configure `estimator` and `target`) → `predict` node and `evaluate` node (both take the
> FittedModel and test DataFrame). The Inspector shows metrics and predictions. For model
> comparison, add a `compare_models` node connected directly to your data source. See
> [Canvas UI Guide](canvas-ui-guide.md).
