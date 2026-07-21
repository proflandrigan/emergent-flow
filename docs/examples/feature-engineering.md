# Feature Engineering

Transform raw features into model-ready inputs. Emergent Flow's feature-engineering surface
spans two layers: dedicated canvas transform nodes (`scale_features`, `encode_categorical`,
`discretize`, `generate_features`) and the underlying `ef.ml` adapter functions
(`fit_transform`, `select_features`, `apply_estimator`) they route through. All operations
return NEW DataFrames — none of them mutate the input.

## Setup

```python
import emergentflow as ef
import pandas as pd
import numpy as np

df = pd.DataFrame({
    "age": [25, 30, 35, 40, 45, 50],
    "income": [30000, 45000, 55000, 70000, 80000, 120000],
    "city": ["NYC", "LA", "NYC", "Chicago", "LA", "NYC"],
    "education": ["BS", "MS", "PhD", "BS", "MS", "PhD"],
    "purchased": [0, 0, 1, 0, 1, 1],
})
print(df)
```

| age | income | city | education | purchased |
| ---: | ---: | --- | --- | ---: |
| 25 | 30000 | NYC | BS | 0 |
| 30 | 45000 | LA | MS | 0 |
| 35 | 55000 | NYC | PhD | 1 |
| 40 | 70000 | Chicago | BS | 0 |
| 45 | 80000 | LA | MS | 1 |
| 50 | 120000 | NYC | PhD | 1 |

## 1. Scaling Features

### `fit_transform` with scalers

Every `fit_transform`-archetype estimator (scalers, encoders, decomposition, ...) routes
through `ef.ml.fit_transform`, which fits the curated estimator and transforms the SAME frame
it fit on in one step, returning `(transformer, result)`. `transformer` is a `FittedTransformer`
— an inspectable wrapper (`estimator_type`, `feature_names`) around the live sklearn object,
mirroring `FittedModel` on the supervised side. `result` is a new frame with `component_0`,
`component_1`, ... columns appended, one per output column of the transform.

```python
transformer, scaled_df = ef.ml.fit_transform(df, estimator="StandardScaler", features=["age", "income"])
print(scaled_df[["age", "income", "component_0", "component_1"]])
```

| age | income | component_0 | component_1 |
| ---: | ---: | ---: | ---: |
| 25 | 30000 | -1.464 | -1.272 |
| 30 | 45000 | -0.878 | -0.752 |
| 35 | 55000 | -0.293 | -0.405 |
| 40 | 70000 | 0.293 | 0.116 |
| 45 | 80000 | 0.878 | 0.463 |
| 50 | 120000 | 1.464 | 1.851 |

Note the output columns are `component_0`, `component_1`, etc. — not the original `age`/`income`
column names. This naming convention is shared across every `fit_transform`/`apply_estimator`
`"transform"` call so downstream code never has to guess the shape of a transformer's output.

```python
# MinMaxScaler (0-1 range)
transformer, scaled_df = ef.ml.fit_transform(df, estimator="MinMaxScaler", features=["age", "income"])

# RobustScaler (resistant to outliers, uses median/IQR instead of mean/variance)
transformer, scaled_df = ef.ml.fit_transform(df, estimator="RobustScaler", features=["age", "income"])
```

### Apply a fitted transformer to new data

`transformer` (the `FittedTransformer` from a prior `fit_transform` call) can be replayed
against a different frame via `ef.ml.apply_estimator(..., op="transform")` — the same
"fit once, apply repeatedly" pattern as `FittedModel`/`predict`.

```python
new_data = pd.DataFrame({"age": [28, 55], "income": [40000, 95000], "city": ["LA", "NYC"], "education": ["BS", "MS"], "purchased": [0, 1]})
result = ef.ml.apply_estimator(transformer, new_data, op="transform")
print(result[["age", "income", "component_0", "component_1"]])
```

| age | income | component_0 | component_1 |
| ---: | ---: | ---: | ---: |
| 28 | 40000 | -1.113 | -0.925 |
| 55 | 95000 | 2.049 | 0.983 |

`apply_estimator` validates that every `transformer.feature_names` column is present in
`new_data` and that the output columns (`component_0`, ...) don't already exist there, so a
fitted transformer is never silently applied to the wrong shape of data or made to clobber
real columns.

## 2. Encoding Categorical Variables

Categorical encoding is just another `fit_transform`-archetype estimator — the same adapter as
scaling, only the estimator key changes.

```python
# One-hot encoding
transformer, encoded_df = ef.ml.fit_transform(df, estimator="OneHotEncoder", features=["city"])
print(encoded_df.filter(like="component"))
```

| component_0 | component_1 | component_2 |
| ---: | ---: | ---: |
| 0.0 | 0.0 | 1.0 |
| 0.0 | 1.0 | 0.0 |
| 0.0 | 0.0 | 1.0 |
| 1.0 | 0.0 | 0.0 |
| 0.0 | 1.0 | 0.0 |
| 0.0 | 0.0 | 1.0 |

One binary column per distinct category (`city` has three: `Chicago`, `LA`, `NYC`, in sorted
order). `OneHotEncoder` is registered with `sparse_output=False`, so `fit_transform` never has
to densify a sparse matrix before appending it as DataFrame columns.

```python
# Ordinal encoding
transformer, encoded_df = ef.ml.fit_transform(df, estimator="OrdinalEncoder", features=["education"])
print(encoded_df[["education", "component_0"]])
```

| education | component_0 |
| --- | ---: |
| BS | 0.0 |
| MS | 1.0 |
| PhD | 2.0 |
| BS | 0.0 |
| MS | 1.0 |
| PhD | 2.0 |

A single integer-coded column, one category per distinct value (assigned in sorted order —
`OrdinalEncoder` has no notion of `education`'s natural BS < MS < PhD ordering unless you pass
an explicit category order). Prefer one-hot encoding for nominal categories with no inherent
order, like `city`; ordinal encoding is appropriate when the categories really are ordered, or
when feeding a tree-based model that can split on an arbitrary integer coding either way.

## 3. Dimensionality Reduction

`PCA` is registered as a `fit_transform`-archetype estimator too, so it goes through the exact
same `fit_transform` adapter as a scaler:

```python
iris = ef.data.load_sample("iris")
transformer, reduced = ef.ml.fit_transform(
    iris,
    estimator="PCA",
    features=["sepal length (cm)", "sepal width (cm)", "petal length (cm)", "petal width (cm)"],
    params={"n_components": 2},
)
print(reduced[["component_0", "component_1"]].head())
```

| component_0 | component_1 |
| ---: | ---: |
| -2.684 | 0.319 |
| -2.714 | -0.177 |
| -2.889 | -0.145 |
| -2.745 | -0.318 |
| -2.729 | 0.327 |

The four iris measurement columns collapse to two principal-component columns capturing most of
the variance — a common precursor to 2D visualization or to feeding a downstream model fewer,
decorrelated inputs.

## 4. Feature Selection

`ef.ml.select_features` is a separate adapter from `fit_transform`, restricted to estimators
registered with `is_feature_selector=True` (`SelectKBest`, `VarianceThreshold`, `RFE`,
`SelectFromModel`). It returns `(selector, result, summary)`: `result` keeps only the selected
feature columns (plus any non-candidate columns, like the target, untouched); `summary` is a
tidy, one-row-per-candidate-feature report of what got kept.

```python
selector, result_df, summary = ef.ml.select_features(
    iris,
    selector="SelectKBest",
    target="target",
    params={"k": 2},
)
print(summary)
```

| feature | selected | score |
| --- | --- | ---: |
| sepal length (cm) | False | 119.26 |
| sepal width (cm) | False | 49.16 |
| petal length (cm) | True | 1180.16 |
| petal width (cm) | True | 960.01 |

`SelectKBest` is supervised — it needs `target` to score each feature (here via its default
`f_classif` scoring function) — and keeps the top `k`. `summary` includes a `score` column
because `SelectKBest`'s fitted estimator exposes `scores_`; `select_features` also surfaces a
`ranking` column when the fitted selector exposes `ranking_` instead (e.g. `RFE`).

```python
# Variance threshold (unsupervised, no target needed)
selector, result_df, summary = ef.ml.select_features(iris, selector="VarianceThreshold")
```

`VarianceThreshold` needs no `target` — it drops features whose variance falls below a
threshold regardless of any label, so `summary` here has no `score`/`ranking` column (the
fitted `VarianceThreshold` exposes neither attribute).

## 5. Polynomial / Interaction Features

```python
transformer, poly_df = ef.ml.fit_transform(
    df,
    estimator="PolynomialFeatures",
    features=["age", "income"],
    params={"degree": 2, "include_bias": False},
)
print(poly_df.filter(like="component").head())
```

| component_0 | component_1 | component_2 | component_3 | component_4 |
| ---: | ---: | ---: | ---: | ---: |
| 25.0 | 30000.0 | 625.0 | 750000.0 | 9.00e8 |
| 30.0 | 45000.0 | 900.0 | 1.35e6 | 2.03e9 |
| 35.0 | 55000.0 | 1225.0 | 1.93e6 | 3.03e9 |
| 40.0 | 70000.0 | 1600.0 | 2.80e6 | 4.90e9 |
| 45.0 | 80000.0 | 2025.0 | 3.60e6 | 6.40e9 |

With two input features and `degree=2`, `PolynomialFeatures` emits every degree-1 and degree-2
term: `age`, `income`, `age^2`, `age*income`, `income^2` — five `component_*` columns in that
order. `include_bias=False` drops the constant `1.0` column PolynomialFeatures would otherwise
prepend (its curated default is `include_bias=True`; most downstream estimators already fit
their own intercept, so the bias column is usually redundant).

## 6. Discretization

```python
transformer, binned_df = ef.ml.fit_transform(
    df,
    estimator="KBinsDiscretizer",
    features=["age", "income"],
    params={"n_bins": 3, "strategy": "quantile"},
)
print(binned_df[["age", "income", "component_0", "component_1"]])
```

| age | income | component_0 | component_1 |
| ---: | ---: | ---: | ---: |
| 25 | 30000 | 0.0 | 0.0 |
| 30 | 45000 | 0.0 | 0.0 |
| 35 | 55000 | 1.0 | 1.0 |
| 40 | 70000 | 1.0 | 1.0 |
| 45 | 80000 | 2.0 | 2.0 |
| 50 | 120000 | 2.0 | 2.0 |

Each continuous column is bucketed into `n_bins` integer-coded bins (`strategy="quantile"`
splits so each bin holds roughly the same number of rows; `"uniform"` splits the value range
into equal-width bins instead, and `"kmeans"` clusters values into bins). The curated
`KBinsDiscretizer` defaults to `encode="ordinal"`, so each output column is a single integer bin
index rather than one-hot columns per bin.

## 7. Combining in a Pipeline

Chaining a `fit_transform`-archetype step with a final `fit`-archetype estimator composes into
one `sklearn.pipeline.Pipeline` via `ef.ml.fit_pipeline` — no separate `apply_estimator` node
needed to thread a scaler's output into a model at inference time.

```python
model = ef.ml.fit_pipeline(
    df,
    target="purchased",
    features=["age", "income"],
    steps=[
        {"estimator": "StandardScaler"},
        {"estimator": "LogisticRegression"},
    ],
)
print(model.estimator_type, model.task, model.feature_names)
# Pipeline classification ['age', 'income']

predictions = ef.ml.apply_estimator(model, df, op="predict")
print(predictions[["purchased", "prediction"]])
```

| purchased | prediction |
| ---: | ---: |
| 0 | 0 |
| 0 | 0 |
| 1 | 0 |
| 0 | 1 |
| 1 | 1 |
| 1 | 1 |

`model` is a `FittedModel` wrapping the whole `Pipeline` (scaler + classifier fit together) —
`ef.ml.predict`/`ef.ml.evaluate`/`ef.ml.apply_estimator` all work against it exactly as they
would against a single fitted estimator, since a `Pipeline` duck-types `.predict()` the same
way.

## 8. In the Canvas

> **In the Canvas:** Feature engineering nodes (`scale_features`, `encode_categorical`,
> `discretize`, `generate_features`) take a DataFrame in and pass a transformed DataFrame out.
> Chain them between your data source and your model node. Each node's Config tab shows the
> available parameters (scaler type, encoding strategy, etc.). See
> [Canvas UI Guide](canvas-ui-guide.md).
