# Time Series

Forecasting and feature transforms via thin statsmodels/pandas wrappers. Forecasting ops
(`forecast_arima`, `forecast_ets`, `seasonal_decompose`) return a structured, inspectable
result pairing a tidy summary DataFrame with the live statsmodels results object. Feature
transforms (`ewma`, `lag_features`, `rolling_aggregate`, `difference`,
`time_weighted_aggregate`) return an augmented copy of the input DataFrame and never mutate
it.

## Setup

```python
import emergentflow as ef
import pandas as pd
import numpy as np

# Create a simple time series
np.random.seed(42)
dates = pd.date_range("2023-01-01", periods=120, freq="D")
trend = np.linspace(10, 50, 120)
seasonal = 5 * np.sin(2 * np.pi * np.arange(120) / 30)
noise = np.random.randn(120) * 2
df = pd.DataFrame({"date": dates, "value": trend + seasonal + noise})
print(df.head())
```

| date | value |
| --- | ---: |
| 2023-01-01 | 10.99 |
| 2023-01-02 | 11.68 |
| 2023-01-03 | 13.05 |
| 2023-01-04 | 14.02 |
| 2023-01-05 | 13.89 |

## 1. ARIMA Forecasting

```python
result = ef.timeseries.forecast_arima(
    df, target="value", date_col="date",
    order=(1, 1, 1), horizon=14,
)
print(f"Model: {result.model}")        # "ARIMA"
print(f"Order: {result.order}")         # (1, 1, 1)
print(f"AIC: {result.fit_stats['aic']:.1f}")
print(result.forecast.head())
```

`ef.timeseries.forecast_arima(df, *, target, order=(1, 0, 0), seasonal_order=(0, 0, 0, 0),
horizon=10, date_col=None)` is a thin wrapper over `statsmodels.tsa.statespace.sarimax.SARIMAX`.
`order` is `(p, d, q)`. With `date_col` given, that column is parsed to datetime and set as the
index before fitting; `df` itself is never mutated. Returns a `ForecastResult` with
`model="ARIMA"` and `fit_stats` carrying `aic`/`bic`/`loglik`.

`result.forecast` is a tidy DataFrame with `horizon` rows:

| step | forecast | lower_ci | upper_ci |
| ---: | ---: | ---: | ---: |
| 1 | 48.91 | 45.32 | 52.50 |
| 2 | 49.03 | 44.01 | 54.05 |
| 3 | 49.10 | 42.98 | 55.22 |

### Seasonal ARIMA

```python
result = ef.timeseries.forecast_arima(
    df, target="value", date_col="date",
    order=(1, 1, 1), seasonal_order=(1, 0, 1, 30),
    horizon=30,
)
```

`seasonal_order` is `(P, D, Q, s)`; the trailing `s` is the seasonal period (30 days here).

## 2. Exponential Smoothing (ETS)

```python
result = ef.timeseries.forecast_ets(
    df, target="value", date_col="date",
    trend="add", horizon=14,
)
print(result.forecast.head())
```

`ef.timeseries.forecast_ets(df, *, target, trend="add", seasonal=None, seasonal_periods=None,
horizon=10, date_col=None)` wraps `statsmodels.tsa.holtwinters.ExponentialSmoothing`. `trend`
and `seasonal` are each `"add"`, `"mul"`, or `None`; `seasonal_periods` is required whenever
`seasonal` is set. Returns a `ForecastResult` with `model="ETS"` — note that `lower_ci`/
`upper_ci` are `NaN` in `result.forecast`, since plain exponential smoothing produces no
prediction intervals.

```python
# With a seasonal component
result = ef.timeseries.forecast_ets(
    df, target="value", date_col="date",
    trend="add", seasonal="add", seasonal_periods=30,
    horizon=30,
)
```

## 3. Seasonal Decomposition

```python
result = ef.timeseries.seasonal_decompose(
    df, target="value", date_col="date",
    model="additive", period=30,
)
print(result.components.head())
```

`ef.timeseries.seasonal_decompose(df, *, target, model="additive", period=None, date_col=None)`
wraps `statsmodels.tsa.seasonal.seasonal_decompose`. `model` is `"additive"` or
`"multiplicative"`; `period` is required (the seasonal period is never inferred). Returns a
`DecomposeResult` (`model`, `period`, `components`), where `components` has one row per input
observation:

| observed | trend | seasonal | residual |
| ---: | ---: | ---: | ---: |
| 10.99 | NaN | -0.42 | NaN |
| 11.68 | NaN | 0.87 | NaN |
| 13.05 | 15.21 | 2.05 | -4.21 |

## 4. Feature Transforms

### EWMA

```python
smoothed = ef.timeseries.ewma(df, columns=["value"], span=7)
print(smoothed[["value", "value_ewma"]].head())
```

`ef.timeseries.ewma(df, *, columns, span=None, halflife=None, alpha=None, suffix="_ewma")` wraps
`DataFrame.ewm(...).mean()`. Exactly one of `span`/`halflife`/`alpha` must be given. New columns
are named `{col}{suffix}`.

| value | value_ewma |
| ---: | ---: |
| 10.99 | 10.99 |
| 11.68 | 11.36 |
| 13.05 | 12.19 |

### Lag Features

```python
lagged = ef.timeseries.lag_features(df, columns=["value"], lags=[1, 7, 14])
print(lagged[["value", "value_lag_1", "value_lag_7", "value_lag_14"]].head(15))
```

`ef.timeseries.lag_features(df, *, columns, lags)` wraps `Series.shift`. `lags` is a non-empty
list of integers `>= 1`; appends `{col}_lag_{k}` for every column x lag pair.

### Rolling Aggregate

```python
rolled = ef.timeseries.rolling_aggregate(
    df, columns=["value"], window=7, agg="mean",
)
print(rolled[["value", "value_rolling_mean_7"]].head(10))
```

`ef.timeseries.rolling_aggregate(df, *, columns, window, agg="mean", min_periods=None)` wraps
`Series.rolling`. Appends `{col}_rolling_{agg}_{window}`. Available `agg` values: `"mean"`,
`"sum"`, `"std"`, `"min"`, `"max"`.

### Differencing

```python
diffed = ef.timeseries.difference(df, columns=["value"], periods=1)
print(diffed[["value", "value_diff_1"]].head())

# With seasonal differencing
diffed = ef.timeseries.difference(
    df, columns=["value"], periods=1, seasonal_periods=30,
)
```

`ef.timeseries.difference(df, *, columns, periods=1, seasonal_periods=None)` wraps
`Series.diff`. Appends `{col}_diff_{periods}`; with `seasonal_periods` given, also appends
`{col}_seasonal_diff_{seasonal_periods}`.

### Time-Weighted Aggregate

```python
weighted = ef.timeseries.time_weighted_aggregate(
    df, columns=["value"], date_col="date", decay="linear", window=7,
)
```

`ef.timeseries.time_weighted_aggregate(df, *, columns, date_col, decay="linear", window=None)`
appends recency-weighted rolling-mean columns `{col}_tw_{decay}`. `decay="linear"` weights
observations `1, 2, ..., n` (most recent weighted more); `decay="exponential"` weights them by a
fixed decay factor. With `window` given, weights are computed over a trailing rolling window;
otherwise over all preceding rows (expanding). `date_col` must exist and row order is assumed to
already be chronological.

## 5. Chaining Transforms for ML

```python
features = (
    ef.timeseries.lag_features(df, columns=["value"], lags=[1, 7])
    .pipe(ef.timeseries.rolling_aggregate, columns=["value"], window=7, agg="mean")
    .pipe(ef.timeseries.ewma, columns=["value"], span=7)
    .dropna()
)
```

Since every feature transform takes a DataFrame and returns an augmented copy, they compose
naturally via `.pipe(...)` into a single feature-engineering pipeline, ending with `.dropna()`
to drop the rows with missing lag/rolling values before fitting a model.

## 6. In the Canvas

> **In the Canvas:** Time series nodes are in the palette under the `timeseries` family. Connect
> a data source to a `forecast_arima` or `forecast_ets` node and configure the order/horizon.
> Feature transform nodes (`ts_ewma`, `ts_lag_features`, `ts_rolling_aggregate`, `ts_difference`)
> chain like cleaning nodes — each takes a DataFrame in and passes an augmented one out. See
> [Canvas UI Guide](canvas-ui-guide.md).
