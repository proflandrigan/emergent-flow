"""
emergentflow.timeseries
~~~~~~~~~~~~~~~~~~~~~~~~
Time-series forecasting and feature-transform operations.

Thin wrappers over statsmodels and pandas (both hard deps) — no reimplementation of
forecasting or feature-engineering algorithms. Each public operation validates its
inputs at the boundary (fail fast, clear typed ``ValueError``s) and otherwise defers
entirely to the underlying, trusted library. Forecasting functions (``forecast_arima``,
``forecast_ets``, ``seasonal_decompose``) return a live statsmodels results object
alongside tidy, inspectable summary frames; feature-transform functions
(``ewma``, ``lag_features``, ``rolling_aggregate``, ``difference``,
``time_weighted_aggregate``) return an augmented copy of the input DataFrame and never
mutate the original.

See ``docs/sdk-design-philosophy.md`` and ``docs/public-api-conventions.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tsa.seasonal import seasonal_decompose as _sm_seasonal_decompose
from statsmodels.tsa.statespace.sarimax import SARIMAX

from emergentflow.api import public_op

__all__ = [
    "ForecastResult",
    "DecomposeResult",
    "forecast_arima",
    "forecast_ets",
    "seasonal_decompose",
    "ewma",
    "lag_features",
    "rolling_aggregate",
    "difference",
    "time_weighted_aggregate",
]

_ROLLING_AGGS = ("mean", "sum", "std", "min", "max")
_DECOMPOSE_MODELS = ("additive", "multiplicative")
_DECAY_METHODS = ("linear", "exponential")
_EXPONENTIAL_DECAY_ALPHA = 0.5


@dataclass
class ForecastResult:
    """Structured, inspectable result of a univariate forecast.

    Attributes
    ----------
    model: the forecasting method used (``"ARIMA"`` or ``"ETS"``).
    order: the ``(p, d, q)`` ARIMA order, or ``None`` for non-ARIMA models.
    seasonal_order: the ``(P, D, Q, s)`` seasonal ARIMA order, or ``None``.
    forecast: tidy DataFrame with columns ``step``, ``forecast``, ``lower_ci``,
        ``upper_ci`` (``horizon`` rows). Confidence-interval columns are ``NaN`` when
        the underlying model does not produce them.
    fit_stats: JSON-native in-sample fit statistics (e.g. ``aic``/``bic``).
    results: the live statsmodels results object; not JSON-serialized.
    """

    model: str
    order: tuple[int, ...] | None
    seasonal_order: tuple[int, ...] | None
    forecast: pd.DataFrame
    fit_stats: dict[str, Any] = field(default_factory=dict)
    results: Any = None


@dataclass
class DecomposeResult:
    """Structured, inspectable result of a seasonal decomposition.

    Attributes
    ----------
    model: ``"additive"`` or ``"multiplicative"``.
    period: the seasonal period used.
    components: tidy DataFrame with columns ``observed``, ``trend``, ``seasonal``,
        ``residual``.
    """

    model: str
    period: int
    components: pd.DataFrame


def _prepare_series(df: pd.DataFrame, *, target: str, date_col: str | None) -> pd.Series:
    """Validate + extract the target column as a Series, optionally DatetimeIndex-ed.

    Never mutates ``df``.
    """
    if target not in df.columns:
        raise ValueError(f"unknown target {target!r}; expected one of {list(df.columns)!r}.")
    if date_col is None:
        return df[target]
    if date_col not in df.columns:
        raise ValueError(f"unknown date_col {date_col!r}; expected one of {list(df.columns)!r}.")
    if date_col == target:
        raise ValueError(f"date_col and target must differ; both were {date_col!r}.")
    work = df.copy()
    work[date_col] = pd.to_datetime(work[date_col])
    work = work.set_index(date_col)
    return work[target]


def _validate_horizon(horizon: int) -> None:
    if horizon < 1:
        raise ValueError(f"horizon must be >= 1; got {horizon}.")


def _validate_columns(df: pd.DataFrame, columns: list[str]) -> None:
    if not columns:
        raise ValueError("columns must be a non-empty list.")
    unknown = [c for c in columns if c not in df.columns]
    if unknown:
        raise ValueError(f"unknown columns {unknown!r}; expected one of {list(df.columns)!r}.")


@public_op(name="ef.timeseries.forecast_arima")
def forecast_arima(
    df: pd.DataFrame,
    *,
    target: str,
    order: tuple[int, int, int] = (1, 0, 0),
    seasonal_order: tuple[int, int, int, int] = (0, 0, 0, 0),
    horizon: int = 10,
    date_col: str | None = None,
) -> ForecastResult:
    """Fit a SARIMAX model on ``target`` and forecast ``horizon`` steps ahead.

    Thin wrapper over ``statsmodels.tsa.statespace.sarimax.SARIMAX``. ``order`` is
    ``(p, d, q)``; ``seasonal_order`` is ``(P, D, Q, s)``. With ``date_col`` given, that
    column is parsed to datetime and set as the index before fitting; never mutates
    ``df``. Returns a :class:`ForecastResult` with ``model="ARIMA"``.
    """
    if len(order) != 3:
        raise ValueError(f"order must have length 3 (p, d, q); got {order!r}.")
    if len(seasonal_order) != 4:
        raise ValueError(f"seasonal_order must have length 4 (P, D, Q, s); got {seasonal_order!r}.")
    _validate_horizon(horizon)
    series = _prepare_series(df, target=target, date_col=date_col)

    model = SARIMAX(series, order=order, seasonal_order=seasonal_order)
    fit = model.fit(disp=False)
    pred = fit.get_forecast(steps=horizon)
    mean = np.asarray(pred.predicted_mean, dtype=float)
    ci = np.asarray(pred.conf_int(), dtype=float)

    forecast = pd.DataFrame(
        {
            "step": list(range(1, horizon + 1)),
            "forecast": mean,
            "lower_ci": ci[:, 0],
            "upper_ci": ci[:, 1],
        }
    )

    return ForecastResult(
        model="ARIMA",
        order=tuple(order),
        seasonal_order=tuple(seasonal_order),
        forecast=forecast,
        fit_stats={"aic": float(fit.aic), "bic": float(fit.bic), "loglik": float(fit.llf)},
        results=fit,
    )


@public_op(name="ef.timeseries.forecast_ets")
def forecast_ets(
    df: pd.DataFrame,
    *,
    target: str,
    trend: str | None = "add",
    seasonal: str | None = None,
    seasonal_periods: int | None = None,
    horizon: int = 10,
    date_col: str | None = None,
) -> ForecastResult:
    """Fit a Holt-Winters exponential-smoothing model on ``target`` and forecast ahead.

    Thin wrapper over ``statsmodels.tsa.holtwinters.ExponentialSmoothing``. ``trend``
    and ``seasonal`` are each ``"add"``, ``"mul"``, or ``None``; ``seasonal_periods`` is
    required when ``seasonal`` is set. With ``date_col`` given, that column is parsed to
    datetime and set as the index before fitting; never mutates ``df``. Returns a
    :class:`ForecastResult` with ``model="ETS"``; ``lower_ci``/``upper_ci`` are ``NaN``
    since plain exponential smoothing does not produce prediction intervals.
    """
    if trend is not None and trend not in ("add", "mul"):
        raise ValueError(f"trend must be 'add', 'mul', or None; got {trend!r}.")
    if seasonal is not None and seasonal not in ("add", "mul"):
        raise ValueError(f"seasonal must be 'add', 'mul', or None; got {seasonal!r}.")
    if seasonal is not None and seasonal_periods is None:
        raise ValueError("seasonal_periods is required when seasonal is set.")
    _validate_horizon(horizon)
    series = _prepare_series(df, target=target, date_col=date_col)

    model = ExponentialSmoothing(
        series,
        trend=trend,
        seasonal=seasonal,
        seasonal_periods=seasonal_periods,
    )
    fit = model.fit()
    mean = np.asarray(fit.forecast(horizon), dtype=float)

    forecast = pd.DataFrame(
        {
            "step": list(range(1, horizon + 1)),
            "forecast": mean,
            "lower_ci": [float("nan")] * horizon,
            "upper_ci": [float("nan")] * horizon,
        }
    )

    return ForecastResult(
        model="ETS",
        order=None,
        seasonal_order=None,
        forecast=forecast,
        fit_stats={"aic": float(fit.aic), "bic": float(fit.bic), "sse": float(fit.sse)},
        results=fit,
    )


@public_op(name="ef.timeseries.seasonal_decompose")
def seasonal_decompose(
    df: pd.DataFrame,
    *,
    target: str,
    model: str = "additive",
    period: int | None = None,
    date_col: str | None = None,
) -> DecomposeResult:
    """Decompose ``target`` into observed/trend/seasonal/residual components.

    Thin wrapper over ``statsmodels.tsa.seasonal.seasonal_decompose``. ``model`` is
    ``"additive"`` or ``"multiplicative"``. ``period`` must be given explicitly (the
    seasonal period is not inferred). With ``date_col`` given, that column is parsed to
    datetime and set as the index first; never mutates ``df``.
    """
    if model not in _DECOMPOSE_MODELS:
        raise ValueError(f"model must be one of {list(_DECOMPOSE_MODELS)!r}; got {model!r}.")
    if period is None:
        raise ValueError("period is required for seasonal_decompose.")
    if period < 1:
        raise ValueError(f"period must be >= 1; got {period}.")
    series = _prepare_series(df, target=target, date_col=date_col)

    result = _sm_seasonal_decompose(series, model=model, period=period)
    components = pd.DataFrame(
        {
            "observed": np.asarray(result.observed, dtype=float),
            "trend": np.asarray(result.trend, dtype=float),
            "seasonal": np.asarray(result.seasonal, dtype=float),
            "residual": np.asarray(result.resid, dtype=float),
        }
    )

    return DecomposeResult(model=model, period=period, components=components)


@public_op(name="ef.timeseries.ewma")
def ewma(
    df: pd.DataFrame,
    *,
    columns: list[str],
    span: float | None = None,
    halflife: float | None = None,
    alpha: float | None = None,
    suffix: str = "_ewma",
) -> pd.DataFrame:
    """Append exponentially-weighted moving-average columns for each of ``columns``.

    Thin wrapper over ``pandas.DataFrame.ewm(...).mean()``. Exactly one of
    ``span``/``halflife``/``alpha`` must be given. New columns are named
    ``{col}{suffix}``. Returns an augmented copy; never mutates ``df``.
    """
    _validate_columns(df, columns)
    given = [v for v in (span, halflife, alpha) if v is not None]
    if len(given) != 1:
        raise ValueError(f"exactly one of span, halflife, alpha must be given; got {len(given)}.")
    result = df.copy()
    for col in columns:
        result[f"{col}{suffix}"] = df[col].ewm(span=span, halflife=halflife, alpha=alpha).mean()
    return result


@public_op(name="ef.timeseries.lag_features")
def lag_features(
    df: pd.DataFrame,
    *,
    columns: list[str],
    lags: list[int],
) -> pd.DataFrame:
    """Append lagged columns ``{col}_lag_{k}`` for each column x lag in ``lags``.

    Thin wrapper over ``pandas.Series.shift``. Returns an augmented copy; never
    mutates ``df``.
    """
    _validate_columns(df, columns)
    if not lags:
        raise ValueError("lags must be a non-empty list of integers.")
    if any(lag < 1 for lag in lags):
        raise ValueError(f"all lags must be >= 1; got {lags!r}.")
    result = df.copy()
    for col in columns:
        for lag in lags:
            result[f"{col}_lag_{lag}"] = df[col].shift(lag)
    return result


@public_op(name="ef.timeseries.rolling_aggregate")
def rolling_aggregate(
    df: pd.DataFrame,
    *,
    columns: list[str],
    window: int,
    agg: str = "mean",
    min_periods: int | None = None,
) -> pd.DataFrame:
    """Append rolling-window aggregate columns ``{col}_rolling_{agg}_{window}``.

    Thin wrapper over ``pandas.Series.rolling``. ``agg`` is one of
    ``"mean"``/``"sum"``/``"std"``/``"min"``/``"max"``. Returns an augmented copy; never
    mutates ``df``.
    """
    _validate_columns(df, columns)
    if agg not in _ROLLING_AGGS:
        raise ValueError(f"unknown agg {agg!r}; expected one of {list(_ROLLING_AGGS)!r}.")
    if window < 1:
        raise ValueError(f"window must be >= 1; got {window}.")
    result = df.copy()
    for col in columns:
        rolling = df[col].rolling(window, min_periods=min_periods)
        result[f"{col}_rolling_{agg}_{window}"] = getattr(rolling, agg)()
    return result


@public_op(name="ef.timeseries.difference")
def difference(
    df: pd.DataFrame,
    *,
    columns: list[str],
    periods: int = 1,
    seasonal_periods: int | None = None,
) -> pd.DataFrame:
    """Append first-difference (and optionally seasonal-difference) columns.

    Thin wrapper over ``pandas.Series.diff``. Appends ``{col}_diff_{periods}``; with
    ``seasonal_periods`` given, also appends ``{col}_seasonal_diff_{seasonal_periods}``.
    Returns an augmented copy; never mutates ``df``.
    """
    _validate_columns(df, columns)
    if periods < 1:
        raise ValueError(f"periods must be >= 1; got {periods}.")
    if seasonal_periods is not None and seasonal_periods < 1:
        raise ValueError(f"seasonal_periods must be >= 1; got {seasonal_periods}.")
    result = df.copy()
    for col in columns:
        result[f"{col}_diff_{periods}"] = df[col].diff(periods)
        if seasonal_periods is not None:
            result[f"{col}_seasonal_diff_{seasonal_periods}"] = df[col].diff(seasonal_periods)
    return result


def _linear_weighted_mean(values: np.ndarray) -> float:
    n = len(values)
    weights = np.arange(1, n + 1, dtype=float)
    return float(np.average(values, weights=weights))


def _exponential_weighted_mean(values: np.ndarray) -> float:
    n = len(values)
    weights = _EXPONENTIAL_DECAY_ALPHA ** np.arange(n - 1, -1, -1, dtype=float)
    return float(np.average(values, weights=weights))


@public_op(name="ef.timeseries.time_weighted_aggregate")
def time_weighted_aggregate(
    df: pd.DataFrame,
    *,
    columns: list[str],
    date_col: str,
    decay: str = "linear",
    window: int | None = None,
) -> pd.DataFrame:
    """Append recency-weighted rolling-mean columns ``{col}_tw_{decay}``.

    ``decay="linear"`` weights observations ``1, 2, ..., n`` (most recent highest);
    ``decay="exponential"`` weights them ``alpha**(n-1), ..., 1`` with a fixed
    ``alpha=0.5``. With ``window`` given, the weighting is computed over a trailing
    rolling window; otherwise it is computed over all preceding rows (expanding).
    ``date_col`` must exist and establishes row order is assumed to already be
    chronological. Returns an augmented copy; never mutates ``df``.
    """
    _validate_columns(df, columns)
    if date_col not in df.columns:
        raise ValueError(f"unknown date_col {date_col!r}; expected one of {list(df.columns)!r}.")
    if decay not in _DECAY_METHODS:
        raise ValueError(f"decay must be one of {list(_DECAY_METHODS)!r}; got {decay!r}.")
    if window is not None and window < 1:
        raise ValueError(f"window must be >= 1; got {window}.")

    fn = _linear_weighted_mean if decay == "linear" else _exponential_weighted_mean
    result = df.copy()
    for col in columns:
        if window is not None:
            weighted = df[col].rolling(window, min_periods=window).apply(fn, raw=True)
        else:
            weighted = df[col].expanding().apply(fn, raw=True)
        result[f"{col}_tw_{decay}"] = weighted
    return result
