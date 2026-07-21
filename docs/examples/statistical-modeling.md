# Statistical Modeling

Curated `statsmodels` wrappers via a single `ef.stats.fit_model` entry point. `model` is a curated,
allow-listed model key (`"OLS"`, `"WLS"`, `"GLS"`, `"GLM"`, `"GAM"`, `"MixedLM"`, or
`"BayesianGLM"`); `spec` is a structured dict of column names and family-specific parameters — NOT
a raw Patsy/Wilkinson formula string. The underlying Patsy formula is assembled internally from
`spec["target"]`/`spec["fixed_effects"]` (quoting column names with spaces or special characters
via `Q()` automatically), so callers never write formula syntax by hand. Every fit returns a
`FittedStatsModel` with a tidy coefficient frame, fit statistics, and the live results object.

## Setup

```python
import emergentflow as ef

df = ef.data.load_sample("iris")
print(df.columns.tolist())
# ['sepal length (cm)', 'sepal width (cm)', 'petal length (cm)', 'petal width (cm)', 'target']
```

## 1. Linear Regression (OLS / WLS / GLS)

```python
model = ef.stats.fit_model(df, model="OLS", spec={
    "target": "sepal length (cm)",
    "fixed_effects": ["petal length (cm)", "sepal width (cm)"],
})
print(model.coefficients)
```

| term | estimate | std_err | statistic | p_value | ci_low | ci_high |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Intercept | 2.249 | 0.248 | 9.07 | 0.000 | 1.759 | 2.740 |
| petal length (cm) | 0.408 | 0.020 | 20.85 | 0.000 | 0.369 | 0.446 |
| sepal width (cm) | 0.596 | 0.069 | 8.63 | 0.000 | 0.459 | 0.732 |

```python
print(model.fit_stats)
# {'rsquared': 0.84, 'rsquared_adj': 0.837, 'aic': ..., 'bic': ..., 'loglik': ...,
#  'n_obs': 150, 'converged': True}
```

`"OLS"` fits ordinary least squares. `"WLS"` (weighted least squares) additionally requires a
`weights` spec field naming a column of observation weights. `"GLS"` fits generalized least
squares with the default (identity) covariance structure. All three share the same
`target`/`fixed_effects` spec shape and the same coefficient/fit-stats schema. An empty or omitted
`fixed_effects` fits an intercept-only model.

## 2. Generalized Linear Models (GLM)

```python
import pandas as pd

# Logistic regression (Binomial family, logit link)
binary_df = df.copy()
binary_df["is_setosa"] = (df["target"] == 0).astype(int)

model = ef.stats.fit_model(binary_df, model="GLM", spec={
    "target": "is_setosa",
    "fixed_effects": ["petal length (cm)", "petal width (cm)"],
    "family": "binomial",
    "link": "logit",
})

# Poisson regression (count data)
model = ef.stats.fit_model(count_df, model="GLM", spec={
    "target": "count",
    "fixed_effects": ["x1", "x2"],
    "family": "poisson",
    "link": "log",
})
```

`family` is required; `link` is optional and defaults to that family's first registered link.
Optional `weights` fits a variance-weighted GLM. Valid `family`/`link` combinations:

| family | valid links |
| --- | --- |
| `gaussian` | `identity`, `log`, `inverse` |
| `binomial` | `logit`, `probit`, `cloglog` |
| `poisson` | `log`, `identity`, `sqrt` |
| `negativebinomial` | `log`, `identity` |
| `gamma` | `inverse`, `log`, `identity` |

`model.fit_stats` for a GLM reports `pseudo_rsquared` (McFadden-style, `1 - deviance /
null_deviance`) instead of `rsquared`, plus `aic`/`bic`/`loglik`/`n_obs`/`converged`.

## 3. Generalized Additive Models (GAM)

```python
model = ef.stats.fit_model(df, model="GAM", spec={
    "target": "sepal length (cm)",
    "linear_terms": ["sepal width (cm)"],
    "smooth_terms": [
        {"column": "petal length (cm)", "df": 4, "degree": 3},
    ],
})
```

`smooth_terms` is required: a non-empty list of `{"column": str, "df": int (default 4), "degree":
int (default 3)}` dicts, fit as B-spline smooths (statsmodels `GLMGam`, unpenalized — no
smoothing-penalty selection). `linear_terms` are unpenalized linear predictors alongside the
smooths; `family`/`link` are optional and accept the same values as GLM (default `gaussian`).
In `model.coefficients`, linear terms (plus the intercept) get real coefficient statistics; each
smooth term appears as a `s(column)` row with `NaN` estimate/std_err/statistic/p_value/ci — a
smooth's spline-basis coefficients have no single interpretable point estimate.

## 4. Mixed-Effects Models

```python
model = ef.stats.fit_model(data, model="MixedLM", spec={
    "target": "score",
    "fixed_effects": ["treatment"],
    "groups": "subject_id",
})
print(model.coefficients)
```

`groups` (the grouping-factor column, e.g. subject/site/region) is required. `random_effects` is
optional — a list of columns for random slopes; omitting it fits a random-intercept-only model
(statsmodels' default). `model.coefficients` includes both fixed-effect rows (real inferential
stats) and variance-component rows (`"Group Var (...)"`, `"Residual Var"`) with `NaN` inferential
columns, since MixedLM has no closed-form SE/CI for variance components. `model.fit_stats`
additionally reports `icc` (intraclass correlation); `aic`/`bic` may be `NaN` under REML (the
default fit method).

## 5. Bayesian Models (optional `[bayes]` extra)

```python
# pip install 'emergentflow[bayes]'  (installs bambi + pymc + arviz)
model = ef.stats.fit_model(df, model="BayesianGLM", spec={
    "target": "sepal length (cm)",
    "fixed_effects": ["petal length (cm)"],
    "seed": 0,
    "draws": 1000,
    "tune": 1000,
    "chains": 2,
})
```

`seed`, `draws`, `tune`, and `chains` are all REQUIRED (not defaulted) so MCMC runs are exactly
reproducible. `family` is optional (default `gaussian`); setting `groups` (plus optional
`random_effects`) fits a hierarchical model, mirroring `MixedLM`'s spec shape. Raises
`MissingOptionalDependencyError("emergentflow[bayes]")` if bambi/pymc/arviz aren't installed.
`model.coefficients` is a posterior-summary frame (`term`, `mean`, `sd`, `hdi_low`, `hdi_high`,
`r_hat`, `ess_bulk`) instead of the frequentist coefficient schema; `model.fit_stats` reports
`max_r_hat`, `divergences`, and a `converged` heuristic (`max_r_hat < 1.01`).

## 6. Working with FittedStatsModel

```python
print(model.model)          # the curated model key, e.g. "OLS"
print(model.spec)           # JSON-native echo of the resolved spec used to fit

# Tidy coefficients
print(model.coefficients.columns.tolist())
# ['term', 'estimate', 'std_err', 'statistic', 'p_value', 'ci_low', 'ci_high']

# Fit statistics
print(model.fit_stats)  # {'aic': ..., 'bic': ..., 'n_obs': ..., 'converged': True, ...}

# Live results object (for advanced use; not JSON-serialized)
print(model.results.summary())
```

`FittedStatsModel` is the one shared representation every model family returns: `model` (the
curated key), `spec` (the resolved, JSON-native spec), `coefficients` (tidy, per-family — see
above), `diagnostics` (a tidy frame, empty at fit time for every family — populate it via
`ef.stats.diagnostic`, below), `fit_stats` (a JSON-native dict), and `results` (the live
statsmodels/bambi object — degrades to `{"kind": "unsupported"}` wherever the result is
serialized, but stays usable in-process).

## 7. Diagnostics

`ef.stats.diagnostic(df=None, *, diagnostic, model=None, spec=None)` mirrors `fit_model`: exactly
one of `df`/`model` must be given, matching the diagnostic's own requirement.

```python
# 'vif' needs the raw DataFrame (checks predictor multicollinearity, not a specific fit)
diag = ef.stats.diagnostic(df, diagnostic="vif")
print(diag)  # columns: diagnostic, statistic, p_value, detail

# The rest need an already-fitted model and read its residuals
diag = ef.stats.diagnostic(diagnostic="heteroscedasticity", model=model)  # Breusch-Pagan
diag = ef.stats.diagnostic(diagnostic="normality", model=model)           # Jarque-Bera
diag = ef.stats.diagnostic(diagnostic="autocorrelation", model=model)     # Durbin-Watson
```

The residual-based diagnostics (`normality`/`heteroscedasticity`/`autocorrelation`) require a
model whose results expose `.resid` or `.resid_response` — OLS/WLS/GLS/GLM/MixedLM/GAM are
supported; a `BayesianGLM` model raises `InvalidModelSpecError` since ArviZ results expose
neither.

## 8. Visualization

```python
# Coefficient / forest plot
plot = ef.viz.plot_coefficients(model)

# Residuals vs fitted
plot = ef.viz.plot_residuals(model)

# Q-Q plot
plot = ef.viz.plot_qq(model)

# ACF of residuals
plot = ef.viz.plot_acf(model, kind="acf", nlags=15)
```

All four take a `FittedStatsModel` directly and return a `PlotSpec` — bespoke, model-aware plots
distinct from the generic `ef.viz.plot(df, *, chart, ...)` archetype. `plot_acf`'s `kind` accepts
`"acf"` or `"pacf"`.

## 9. In the Canvas

> **In the Canvas:** Add a data source node, then connect to a `fit_linear_regression` (OLS/WLS/
> GLS), `fit_glm`, `fit_gam`, `fit_mixed_model`, or `fit_bayesian_model` node. Configure `target`,
> predictor columns, and family-specific parameters (`family`/`link`, `smooth_terms`, `groups`,
> ...) in the Inspector. Connect the fitted model output to `viz_plot_coefficients`,
> `viz_plot_residuals`, `viz_plot_qq`, or `viz_plot_acf` nodes for diagnostics. See
> [Canvas UI Guide](canvas-ui-guide.md).
