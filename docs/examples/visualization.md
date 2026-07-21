# Visualization

Emergent Flow wraps Plotly Express through a curated chart catalog. Every chart returns a
JSON-native `PlotSpec`.

## Setup

```python
import emergentflow as ef

df = ef.data.load_sample("iris")
```

## 1. The `ef.viz.plot` Function

`ef.viz.plot` is the single entry point for the curated chart catalog — every curated chart
node routes through it, so it takes the same three parameters no matter which chart you pick:

- `chart` — the chart type key (e.g., `"scatter"`, `"bar"`, `"histogram"`, `"line"`, `"box"`).
  Validated against an allow-list registry — an unknown key raises `UnknownChartError`.
- `encoding` — maps visual channels to column names (e.g.,
  `{"x": "col_a", "y": "col_b", "color": "col_c"}`). Validated against the chart's allowed
  encodings — an unsupported channel or missing column raises `InvalidEncodingError`.
- `options` — additional chart options (e.g., `{"title": "My Chart"}`), also validated against
  the chart's allowed options.

## 2. Chart Types

### Scatter Plot

```python
plot = ef.viz.plot(
    df,
    chart="scatter",
    encoding={"x": "sepal length (cm)", "y": "petal length (cm)", "color": "target"},
    options={"title": "Sepal vs Petal Length"},
)
```

### Histogram

```python
plot = ef.viz.plot(
    df,
    chart="histogram",
    encoding={"x": "sepal length (cm)", "color": "target"},
    options={"title": "Sepal Length Distribution"},
)
```

### Bar Chart

```python
# First aggregate
grouped = ef.stats.group_by_aggregate(
    df, by="target", agg="mean", columns=["petal length (cm)"]
)

plot = ef.viz.plot(
    grouped,
    chart="bar",
    encoding={"x": "target", "y": "petal length (cm)"},
    options={"title": "Mean Petal Length by Species"},
)
```

### Box Plot

```python
plot = ef.viz.plot(
    df,
    chart="box",
    encoding={"x": "target", "y": "sepal width (cm)"},
    options={"title": "Sepal Width by Species"},
)
```

### Line Chart

```python
import pandas as pd
import numpy as np

dates = pd.date_range("2024-01-01", periods=30)
ts_df = pd.DataFrame({"date": dates, "value": np.cumsum(np.random.randn(30))})

plot = ef.viz.plot(
    ts_df,
    chart="line",
    encoding={"x": "date", "y": "value"},
    options={"title": "Time Series"},
)
```

### Other Curated Charts

The full curated catalog also includes `"violin"`, `"strip"`, `"ecdf"`, `"density_heatmap"`,
`"density_contour"`, and `"scatter_matrix"` — each following the same `chart`/`encoding`/
`options` shape shown above, just with a different allowed set of encodings and options. The
catalog is an allow-list, not a reflection of every `plotly.express` function, so it stays
deterministic and version-stable; new chart keys are added by registering a `ChartSpec`, not
by exposing the whole `plotly.express` surface.

## 3. Working with PlotSpec

```python
# PlotSpec is JSON-native
print(type(plot))          # <class 'emergentflow.viz.models.PlotSpec'>
print(plot.chart)           # "scatter"

# Access the raw plotly figure JSON
fig_json = plot.spec        # dict — {"data": [...], "layout": {...}}, JSON-native
```

`PlotSpec` never holds a live `plotly.graph_objects.Figure` — `spec` is produced via
`fig.to_json()` + `json.loads`, so it is always serializable and satisfies the `@public_op`
inspectable contract.

## 4. Bespoke Model Plots

Some plots aren't part of the curated `chart` allow-list because they read a fitted model or
a specific tidy-frame shape directly rather than an arbitrary DataFrame + encoding.

### Correlation Heatmap

```python
corr = ef.stats.correlation(df)
plot = ef.viz.plot_correlation_heatmap(corr)
```

Note: takes the tidy correlation matrix from `ef.stats.correlation`, not a raw DataFrame.

### Missingness Heatmap

```python
import pandas as pd
import numpy as np

df_messy = pd.DataFrame({
    "a": [1, np.nan, 3, np.nan, 5],
    "b": [np.nan, 2, np.nan, 4, 5],
    "c": [1, 2, 3, 4, 5],
})

co_miss = ef.stats.co_missingness(df_messy)
plot = ef.viz.plot_missingness_heatmap(co_miss)
```

Like `plot_correlation_heatmap`, this takes the tidy co-missingness matrix from
`ef.stats.co_missingness`, not a raw DataFrame. Values are fractions in `[0, 1]` (not
correlation's `[-1, 1]`), so it renders with a sequential colorscale instead of a diverging one.

### Confusion Matrix (requires a FittedModel)

```python
model = ef.ml.fit_estimator(df, estimator="LogisticRegression", target="target")
plot = ef.viz.plot_confusion_matrix(model, df)
```

Requires a classification `FittedModel` — raises `VizError` for a regression or clustering
model, since a confusion matrix is undefined for those tasks.

### Model Diagnostic Plots (requires a FittedStatsModel)

```python
fitted = ef.stats.fit_model(
    df,
    model="linear_regression",
    spec={"formula": "Q('sepal length (cm)') ~ Q('petal length (cm)')"},
)
plot = ef.viz.plot_coefficients(fitted)
plot = ef.viz.plot_residuals(fitted)
plot = ef.viz.plot_qq(fitted)
plot = ef.viz.plot_acf(fitted, kind="acf", nlags=10)
```

- `plot_coefficients` — a forest plot of each term's estimate with CI whiskers.
- `plot_residuals` — fitted values vs. residuals, with a reference line at zero.
- `plot_qq` — a Q-Q plot of residuals against a normal distribution.
- `plot_acf` — an ACF (or `kind="pacf"`) bar plot of residuals with a 95% CI band.

## 5. In the Canvas

> **In the Canvas:** Add a `viz_plot` node and connect a DataFrame source to its input.
> Configure the `chart`, `encoding`, and `options` parameters in the Inspector's Config tab.
> The Results tab renders the chart inline. For model plots, connect a `fit_model` or
> `fit_estimator` node's output to the corresponding plot node. See
> [Canvas UI Guide](canvas-ui-guide.md).
