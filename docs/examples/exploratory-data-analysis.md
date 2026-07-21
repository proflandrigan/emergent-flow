# Exploratory Data Analysis

Exploratory data analysis (EDA) is the first step in any analysis — understanding a dataset's
shape, distributions, relationships, and gaps before modeling it. Emergent Flow provides
`ef.stats` for summary statistics, missingness, distribution, and hypothesis-testing operations,
and `ef.reports` for an automated, self-contained HTML profiling report.

## Setup

```python
import emergentflow as ef

df = ef.data.load_sample("iris")
```

`df` has 150 rows and 5 columns: `sepal length (cm)`, `sepal width (cm)`, `petal length (cm)`,
`petal width (cm)`, and `target` (0/1/2, one of the three iris species).

## 1. Summary Statistics

### describe

```python
summary = ef.stats.describe(df)
print(summary)
```

Thin wrapper over `pandas.DataFrame.describe`, with the statistic name moved out of the index
into a leading `statistic` column so the result is tidy:

| statistic | sepal length (cm) | sepal width (cm) | petal length (cm) | petal width (cm) | target |
| --- | ---: | ---: | ---: | ---: | ---: |
| count | 150.0 | 150.0 | 150.0 | 150.0 | 150.0 |
| mean | 5.843333 | 3.057333 | 3.758000 | 1.199333 | 1.000000 |
| std | 0.828066 | 0.435866 | 1.765298 | 0.762238 | 0.819232 |
| min | 4.3 | 2.0 | 1.0 | 0.1 | 0.0 |
| 25% | 5.1 | 2.8 | 1.6 | 0.3 | 0.0 |
| 50% | 5.8 | 3.0 | 4.35 | 1.3 | 1.0 |
| 75% | 6.4 | 3.3 | 5.1 | 1.8 | 2.0 |
| max | 7.9 | 4.4 | 6.9 | 2.5 | 2.0 |

```python
# Describe specific columns only
summary = ef.stats.describe(df, columns=["sepal length (cm)", "petal width (cm)"])
```

`columns`, when given, must all exist in `df` (each is validated up front) and restricts the
result to just those columns.

### correlation

```python
corr = ef.stats.correlation(df)
print(corr)
```

Thin wrapper over `pandas.DataFrame.corr`. By default it correlates every numeric column (row
labels moved into a leading `column` field so the matrix stays tidy):

| column | sepal length (cm) | sepal width (cm) | petal length (cm) | petal width (cm) | target |
| --- | ---: | ---: | ---: | ---: | ---: |
| sepal length (cm) | 1.000000 | -0.117570 | 0.871754 | 0.817941 | 0.782561 |
| sepal width (cm) | -0.117570 | 1.000000 | -0.428440 | -0.366126 | -0.426658 |
| petal length (cm) | 0.871754 | -0.428440 | 1.000000 | 0.962865 | 0.949035 |
| petal width (cm) | 0.817941 | -0.366126 | 0.962865 | 1.000000 | 0.956547 |
| target | 0.782561 | -0.426658 | 0.949035 | 0.956547 | 1.000000 |

Values fall between -1 and 1; the diagonal is always 1.0 (a column against itself).

```python
# Spearman or Kendall
corr = ef.stats.correlation(df, method="spearman")
corr = ef.stats.correlation(df, method="kendall", columns=["sepal length (cm)", "petal length (cm)"])
```

Methods: `"pearson"` (default), `"spearman"`, `"kendall"`. With `columns` given, only those
columns are correlated (each must exist) instead of the default "every numeric column."

## 2. Missing Data Analysis

Use a DataFrame with missing values for this section:

```python
import pandas as pd
import numpy as np

df_messy = pd.DataFrame({
    "a": [1, np.nan, 3, np.nan, 5],
    "b": [np.nan, 2, np.nan, 4, 5],
    "c": [1, 2, 3, 4, 5],
})
```

### missingness

```python
miss = ef.stats.missingness(df_messy)
print(miss)
```

One row per column, sorted by `pct_missing` descending (then `column` ascending as a tiebreak):

| column | n_missing | n_present | pct_missing |
| --- | ---: | ---: | ---: |
| a | 2 | 3 | 40.0 |
| b | 2 | 3 | 40.0 |
| c | 0 | 5 | 0.0 |

### co_missingness

```python
co_miss = ef.stats.co_missingness(df_messy)
print(co_miss)
```

A matrix showing the fraction of rows where BOTH columns are simultaneously null — the diagonal
is a column's own missing fraction, off-diagonal cells are pairwise co-occurrence:

| column | a | b | c |
| --- | ---: | ---: | ---: |
| a | 0.4 | 0.0 | 0.0 |
| b | 0.0 | 0.4 | 0.0 |
| c | 0.0 | 0.0 | 0.0 |

`a` and `b` are each individually 40% missing, but their nulls never land on the same row (0.0
co-occurrence) — `co_missingness` surfaces that pattern where `missingness` alone can't.

## 3. Distribution Analysis

### distribution_summary

```python
dist = ef.stats.distribution_summary(df, columns=["sepal length (cm)"])
print(dist)
```

One row per numeric column with count/mean/std, percentiles (`p05`/`p25`/`p50`/`p75`/`p95`),
min/max, and `iqr` (`p75 - p25`):

| column | count | mean | std | min | p05 | p25 | p50 | p75 | p95 | max | iqr |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| sepal length (cm) | 150 | 5.843333 | 0.828066 | 4.3 | 4.6 | 5.1 | 5.8 | 6.4 | 7.255 | 7.9 | 1.3 |

A named column that isn't numeric is silently omitted from the output (a named column that
doesn't exist at all still raises).

### group_by_aggregate

```python
grouped = ef.stats.group_by_aggregate(df, by="target", agg="mean")
print(grouped)
```

`by` names the grouping column(s); `agg` is an aggregation name (or a dict mapping value columns
to aggregation function(s)) passed to `DataFrame.groupby(by).agg(agg)`. With `columns=None` and a
string `agg`, every numeric non-`by` column is aggregated — one row per group:

| target | sepal length (cm) | sepal width (cm) | petal length (cm) | petal width (cm) |
| ---: | ---: | ---: | ---: | ---: |
| 0 | 5.006 | 3.428 | 1.462 | 0.246 |
| 1 | 5.936 | 2.770 | 4.260 | 1.326 |
| 2 | 6.588 | 2.974 | 5.552 | 2.026 |

```python
# Restrict to a single value column
grouped = ef.stats.group_by_aggregate(
    df,
    by="target",
    agg="mean",
    columns=["sepal length (cm)"],
)
```

`columns`, when given, restricts which value columns get aggregated (each must exist).

## 4. Automated EDA

### auto_eda

```python
eda_result = ef.stats.auto_eda(df)
```

Runs a one-shot EDA pass and returns an inspectable `AutoEdaResult` bundle composed from the
other `ef.stats`/`ef.viz` seams — never a parallel implementation:

- `eda_result.frames` — a dict of tidy DataFrames: `"profile"`, `"missingness"`,
  `"co_missingness"`, `"distribution_summary"`, `"correlation"`.
- `eda_result.plots` — a dict of `PlotSpec`s: `"distributions"` (per-column histograms, faceted),
  `"correlation_heatmap"`, `"missingness"` (a co-missingness heatmap).

```python
print(eda_result.frames["missingness"])
```

### profile

```python
prof = ef.stats.profile(df, columns=["sepal length (cm)", "target"])
print(prof)
```

`profile` is a lightweight, dependency-free per-column profile — **not** a ydata-profiling
wrapper (that's `ef.reports.generate_html_summary`, see section 6). Every column gets
`column`/`dtype`/`count`/`n_missing`/`pct_missing`/`n_unique`/`cardinality`; numeric columns
additionally get `mean`/`std`/`min`/`max`/`skew`/`kurtosis` (`NaN` for non-numeric columns):

| column | dtype | count | n_missing | pct_missing | n_unique | cardinality | mean | std | min | max | skew | kurtosis |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| sepal length (cm) | float64 | 150 | 0 | 0.0 | 35 | 0.2333 | 5.843333 | 0.828066 | 4.3 | 7.9 | 0.315 | -0.552 |
| target | int64 | 150 | 0 | 0.0 | 3 | 0.02 | 1.000000 | 0.819232 | 0.0 | 2.0 | 0.0 | -1.5 |

## 5. Hypothesis Testing

### t-test

```python
# Compare sepal length between two species
two_species = ef.clean.filter_rows(df, column="target", operator="isin", value=[0, 1])
result = ef.stats.ttest(two_species, group_col="target", value_col="sepal length (cm)")
print(f"t = {result.t_statistic:.3f}, p = {result.p_value:.4f}")
print(f"Group {result.group_a}: mean = {result.mean_a:.2f} (n={result.n_a})")
print(f"Group {result.group_b}: mean = {result.mean_b:.2f} (n={result.n_b})")
```

`ttest` needs exactly two distinct groups in `group_col`; `two_species` narrows `target` down to
`0`/`1` (setosa/versicolor). Output:

```
t = -10.521, p = 0.0000
Group 0: mean = 5.01 (n=50)
Group 1: mean = 5.94 (n=50)
```

`result` is a `TTestResult` with fields `t_statistic`, `p_value`, `df`, `group_a`/`group_b`
(sorted group labels), `n_a`/`n_b`, `mean_a`/`mean_b`, `equal_var`, `alpha`.

```python
# Welch's t-test (unequal variances)
result = ef.stats.ttest(two_species, group_col="target", value_col="sepal length (cm)", equal_var=False)
```

`equal_var=True` (default) runs Student's t-test; `False` runs Welch's. `alpha` is recorded on
the result for callers but doesn't change the computation — the raw p-value is always reported.

### ANOVA

```python
result = ef.stats.anova(df, group_col="target", value_col="sepal length (cm)")
print(f"F = {result.f_statistic:.2f}, p = {result.p_value:.4f}")
print(f"Effect size (eta²) = {result.effect_size:.3f}")
print(result.summary)
```

`anova` needs at least 2 distinct groups in `group_col`; here all three species are compared at
once. Output:

```
F = 119.26, p = 0.0000
Effect size (eta²) = 0.619
```

`result.summary` is statsmodels' tidy `anova_lm` table (`typ=2`):

| | sum_sq | df | F | PR(>F) |
| --- | ---: | ---: | ---: | ---: |
| C(_grp) | 63.21 | 2.0 | 119.26 | 1.67e-31 |
| Residual | 38.96 | 147.0 | NaN | NaN |

`result` is an `AnovaResult` with fields `f_statistic`, `p_value`, `effect_size` (partial
eta-squared), `summary`.

## 6. HTML Profiling Report

```python
html = ef.reports.generate_html_summary(df, title="Iris Dataset Profile")
with open("iris_report.html", "w") as f:
    f.write(html)
```

Produces a self-contained HTML report powered by ydata-profiling (`minimal=True`) — open it in a
browser for interactive exploration (per-column distributions, interactions, correlation
matrices, missing-value patterns). Unlike the `ef.stats` functions above, the HTML embeds a
generation timestamp, so it is not byte-reproducible between calls even for identical input data.

## 7. Visualizing EDA Results

```python
# Correlation heatmap (see Visualization guide)
corr = ef.stats.correlation(df)
plot = ef.viz.plot_correlation_heatmap(corr)

# Missingness heatmap
co_miss = ef.stats.co_missingness(df_messy)
plot = ef.viz.plot_missingness_heatmap(co_miss)
```

See the Visualization guide for the full `ef.viz` catalog and how to render a returned
`PlotSpec`.

## 8. In the Canvas

> **In the Canvas:** Add a `load_sample` node, then connect it to a `describe` node and a
> `correlation` node in parallel (both take the same DataFrame input). The Inspector's Results
> tab shows each node's output table. For a full profile, connect to a `report` node — the
> server stores the HTML and the canvas links to it. See [Canvas UI Guide](canvas-ui-guide.md).
