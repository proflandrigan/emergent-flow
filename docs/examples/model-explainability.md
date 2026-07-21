# Model Explainability

Understand why your model makes the predictions it does. The `ef.explain` family provides
SHAP-based feature attribution plus diagnostic plots over an already-fitted
`ml.FittedModel`.

## Setup

```python
import emergentflow as ef

# Train a model first
df = ef.data.load_sample("iris")
train, test = ef.ml.train_test_split(df, test_size=0.25, random_state=0)
model = ef.ml.fit_estimator(train, estimator="RandomForestClassifier", target="target", params={"random_state": 0})
```

## 1. SHAP Values

```python
# Requires: pip install 'emergentflow[explain]'
shap_df = ef.explain.shap_values(model, test, seed=42)
print(shap_df.columns.tolist())
# ['row_index', 'feature', 'feature_value', 'shap_value', 'base_value', 'class']
print(shap_df.head(10))
```

| row_index | feature | feature_value | shap_value | base_value | class |
| ---: | --- | ---: | ---: | ---: | ---: |
| 0 | sepal length (cm) | 5.1 | 0.012 | 0.333 | 0 |
| 0 | sepal width (cm) | 3.5 | 0.004 | 0.333 | 0 |
| 0 | petal length (cm) | 1.4 | 0.145 | 0.333 | 0 |
| 0 | petal width (cm) | 0.2 | 0.201 | 0.333 | 0 |
| 1 | sepal length (cm) | 4.9 | -0.008 | 0.333 | 0 |

`shap_values` returns one row per `(row_index, feature[, class])` — a tidy, long-format
DataFrame rather than the wide matrix SHAP normally works with. `row_index` is the 0-indexed
position in `test`; `base_value` is the model's average/expected output the SHAP values are
offsets from. The `class` column is present only for a multiclass classifier (iris has three
target classes, so it shows up above); regression and binary classification have no `class`
column and explain only a single output (binary classification explains the positive class's
probability, mirroring `ef.ml.evaluate`'s `pos_label = classes[1]` convention).

Uses `shap.TreeExplainer` (exact, deterministic) for pure tree-ensemble regressors; every other
model — every classifier, every non-tree regressor — uses a seeded, background-sampled
`shap.Explainer`. `background_samples` (default `100`) bounds and `seed` fixes that background
sample wherever sampling is used, so results are deterministic given the same inputs.

## 2. SHAP Plots

The plot functions consume the tidy `shap_values` DataFrame from step 1, not the model and
frame directly:

```python
# Feature importance (mean |SHAP|), one bar per feature
plot = ef.explain.plot_shap_importance(shap_df)

# Beeswarm plot — one jittered marker per (row, feature), colored by feature value
plot = ef.explain.plot_shap_beeswarm(shap_df)

# Waterfall explaining a single prediction
plot = ef.explain.plot_shap_waterfall(shap_df, row_index=0)
```

`plot_shap_importance` handles a multiclass frame by rendering one grouped bar per feature per
class. `plot_shap_beeswarm` and `plot_shap_waterfall` only support a single-output frame
(regression or binary classification) — for a multiclass `shap_df`, filter to one class's rows
first (e.g. `shap_df[shap_df["class"] == 0]`).

## 3. Error Analysis (no `[explain]` extra needed)

```python
errors = ef.explain.error_table(model, test)
print(errors.head())
```

For a classifier, `error_table` ranks misclassified rows first, then by ascending confidence
within each group:

| row_index | target | prediction | correct | confidence |
| ---: | ---: | ---: | --- | ---: |
| 12 | 1 | 2 | False | 0.41 |
| 47 | 2 | 1 | False | 0.52 |
| 3 | 0 | 0 | True | 0.97 |

For a regression model, it instead ranks by descending `abs_error` and returns `target`,
`prediction`, `residual`, and `abs_error` columns. Both `error_table` and every diagnostic
plot below need only the SDK's hard dependencies — no `shap` install required.

## 4. Diagnostic Plots (no `[explain]` extra needed)

```python
# Residuals (regression)
diabetes = ef.data.load_sample("diabetes")
reg_model = ef.ml.fit_estimator(diabetes, estimator="LinearRegression", target="target")
plot = ef.explain.plot_residuals(reg_model, diabetes)

# Predicted vs actual
plot = ef.explain.plot_predicted_vs_actual(reg_model, diabetes)

# Calibration curve (binary classification)
plot = ef.explain.plot_calibration(model, test)

# ROC and PR curves (binary classification)
plot = ef.explain.plot_roc_pr(model, test)
plot = ef.explain.plot_roc_pr(model, test, curve="pr")
```

`plot_residuals` and `plot_predicted_vs_actual` require a regression model. `plot_calibration`
and `plot_roc_pr` require a *binary* classifier with `predict_proba` — a multiclass model (like
the iris `model` above) raises `UnsupportedModelError` for these two.

## 5. In the Canvas

> **In the Canvas:** Connect a fitted model's output port to any `explain_*` node. The
> `explain_shap_values` node outputs a tidy DataFrame; the plot nodes (`explain_plot_shap_importance`,
> `explain_plot_shap_beeswarm`, `explain_plot_shap_waterfall`) consume that DataFrame and render
> inline. Error analysis and diagnostic nodes (`explain_error_table`, `explain_plot_residuals`,
> `explain_plot_predicted_vs_actual`, `explain_plot_calibration`, `explain_plot_roc_pr`) connect
> directly to a fitted model and work without the `[explain]` extra. See
> [Canvas UI Guide](canvas-ui-guide.md).
