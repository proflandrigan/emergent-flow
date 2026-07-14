"""Unit tests for `emergentflow.timeseries` public ops."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from emergentflow.timeseries import (
    DecomposeResult,
    ForecastResult,
    difference,
    ewma,
    forecast_arima,
    forecast_ets,
    lag_features,
    rolling_aggregate,
    seasonal_decompose,
    time_weighted_aggregate,
)


@pytest.fixture
def ts_df() -> pd.DataFrame:
    """Simple 60-row time-series DataFrame for testing."""
    rng = np.random.default_rng(42)
    n = 60
    dates = pd.date_range("2020-01-01", periods=n, freq="D")
    return pd.DataFrame(
        {
            "date": dates,
            "value": rng.normal(100, 10, size=n).cumsum(),
            "other": rng.normal(50, 5, size=n),
        }
    )


# --------------------------------------------------------------------------
# forecast_arima
# --------------------------------------------------------------------------


def test_forecast_arima_basic(ts_df):
    result = forecast_arima(ts_df, target="value")
    assert isinstance(result, ForecastResult)
    assert result.model == "ARIMA"
    assert len(result.forecast) == 10  # default horizon
    assert list(result.forecast.columns) == ["step", "forecast", "lower_ci", "upper_ci"]
    assert set(result.fit_stats.keys()) >= {"aic", "bic", "loglik"}


def test_forecast_arima_with_date_col(ts_df):
    result = forecast_arima(ts_df, target="value", date_col="date", horizon=5)
    assert isinstance(result, ForecastResult)
    assert result.model == "ARIMA"
    assert len(result.forecast) == 5
    assert list(result.forecast.columns) == ["step", "forecast", "lower_ci", "upper_ci"]
    assert set(result.fit_stats.keys()) >= {"aic", "bic", "loglik"}


def test_forecast_arima_unknown_target(ts_df):
    with pytest.raises(ValueError):
        forecast_arima(ts_df, target="nope")


def test_forecast_arima_invalid_order(ts_df):
    with pytest.raises(ValueError):
        forecast_arima(ts_df, target="value", order=(1, 0))


def test_forecast_arima_no_mutation(ts_df):
    before = ts_df.copy(deep=True)
    forecast_arima(ts_df, target="value", date_col="date")
    pd.testing.assert_frame_equal(ts_df, before)


# --------------------------------------------------------------------------
# forecast_ets
# --------------------------------------------------------------------------


def test_forecast_ets_basic(ts_df):
    result = forecast_ets(ts_df, target="value", horizon=8)
    assert isinstance(result, ForecastResult)
    assert result.model == "ETS"
    assert len(result.forecast) == 8
    assert result.forecast["lower_ci"].isna().all()
    assert result.forecast["upper_ci"].isna().all()


def test_forecast_ets_unknown_target(ts_df):
    with pytest.raises(ValueError):
        forecast_ets(ts_df, target="nope")


def test_forecast_ets_seasonal_requires_periods(ts_df):
    with pytest.raises(ValueError):
        forecast_ets(ts_df, target="value", seasonal="add", seasonal_periods=None)


# --------------------------------------------------------------------------
# seasonal_decompose
# --------------------------------------------------------------------------


def test_seasonal_decompose_basic(ts_df):
    result = seasonal_decompose(ts_df, target="value", period=7)
    assert isinstance(result, DecomposeResult)
    assert result.period == 7
    assert result.model == "additive"
    assert list(result.components.columns) == ["observed", "trend", "seasonal", "residual"]
    assert len(result.components) == len(ts_df)


def test_seasonal_decompose_no_period(ts_df):
    with pytest.raises(ValueError):
        seasonal_decompose(ts_df, target="value")


def test_seasonal_decompose_invalid_model(ts_df):
    with pytest.raises(ValueError):
        seasonal_decompose(ts_df, target="value", period=7, model="bogus")


# --------------------------------------------------------------------------
# ewma
# --------------------------------------------------------------------------


def test_ewma_span(ts_df):
    result = ewma(ts_df, columns=["value"], span=10)
    assert isinstance(result, pd.DataFrame)
    assert "value_ewma" in result.columns
    assert len(result) == len(ts_df)
    pd.testing.assert_series_equal(result["value"], ts_df["value"])


def test_ewma_no_param(ts_df):
    with pytest.raises(ValueError):
        ewma(ts_df, columns=["value"])


def test_ewma_two_params(ts_df):
    with pytest.raises(ValueError):
        ewma(ts_df, columns=["value"], span=10, alpha=0.3)


def test_ewma_no_mutation(ts_df):
    before = ts_df.copy(deep=True)
    ewma(ts_df, columns=["value"], span=10)
    pd.testing.assert_frame_equal(ts_df, before)


def test_ewma_unknown_column(ts_df):
    with pytest.raises(ValueError):
        ewma(ts_df, columns=["nope"], span=10)


# --------------------------------------------------------------------------
# lag_features
# --------------------------------------------------------------------------


def test_lag_features_basic(ts_df):
    result = lag_features(ts_df, columns=["value"], lags=[1, 3])
    assert "value_lag_1" in result.columns
    assert "value_lag_3" in result.columns
    assert pd.isna(result["value_lag_1"].iloc[0])
    assert result["value_lag_1"].iloc[1] == ts_df["value"].iloc[0]


def test_lag_features_empty_lags(ts_df):
    with pytest.raises(ValueError):
        lag_features(ts_df, columns=["value"], lags=[])


def test_lag_features_negative_lag(ts_df):
    with pytest.raises(ValueError):
        lag_features(ts_df, columns=["value"], lags=[0])


# --------------------------------------------------------------------------
# rolling_aggregate
# --------------------------------------------------------------------------


def test_rolling_mean(ts_df):
    result = rolling_aggregate(ts_df, columns=["value"], window=5, agg="mean")
    assert "value_rolling_mean_5" in result.columns
    assert len(result) == len(ts_df)


def test_rolling_invalid_agg(ts_df):
    with pytest.raises(ValueError):
        rolling_aggregate(ts_df, columns=["value"], window=5, agg="median")


def test_rolling_invalid_window(ts_df):
    with pytest.raises(ValueError):
        rolling_aggregate(ts_df, columns=["value"], window=0)


# --------------------------------------------------------------------------
# difference
# --------------------------------------------------------------------------


def test_difference_basic(ts_df):
    result = difference(ts_df, columns=["value"], periods=1)
    assert "value_diff_1" in result.columns
    assert pd.isna(result["value_diff_1"].iloc[0])


def test_difference_with_seasonal(ts_df):
    result = difference(ts_df, columns=["value"], periods=1, seasonal_periods=7)
    assert "value_diff_1" in result.columns
    assert "value_seasonal_diff_7" in result.columns


def test_difference_invalid_periods(ts_df):
    with pytest.raises(ValueError):
        difference(ts_df, columns=["value"], periods=0)


# --------------------------------------------------------------------------
# time_weighted_aggregate
# --------------------------------------------------------------------------


def test_twa_linear(ts_df):
    result = time_weighted_aggregate(
        ts_df, columns=["value"], date_col="date", decay="linear", window=5
    )
    assert "value_tw_linear" in result.columns
    assert len(result) == len(ts_df)


def test_twa_exponential(ts_df):
    result = time_weighted_aggregate(
        ts_df, columns=["value"], date_col="date", decay="exponential", window=5
    )
    assert "value_tw_exponential" in result.columns


def test_twa_invalid_decay(ts_df):
    with pytest.raises(ValueError):
        time_weighted_aggregate(ts_df, columns=["value"], date_col="date", decay="bogus")


def test_twa_unknown_date_col(ts_df):
    with pytest.raises(ValueError):
        time_weighted_aggregate(ts_df, columns=["value"], date_col="nope")


def test_twa_no_mutation(ts_df):
    before = ts_df.copy(deep=True)
    time_weighted_aggregate(ts_df, columns=["value"], date_col="date", decay="linear", window=5)
    pd.testing.assert_frame_equal(ts_df, before)


# --------------------------------------------------------------------------
# output column collisions -- must raise rather than silently overwrite,
# mirroring emergentflow.ml.fit_transform's collision check.
# --------------------------------------------------------------------------


def test_ewma_raises_on_existing_output_column(ts_df):
    ts_df["value_ewma"] = "should-not-be-overwritten"
    with pytest.raises(ValueError):
        ewma(ts_df, columns=["value"], span=10)


def test_lag_features_raises_on_existing_output_column(ts_df):
    ts_df["value_lag_1"] = "should-not-be-overwritten"
    with pytest.raises(ValueError):
        lag_features(ts_df, columns=["value"], lags=[1, 3])


def test_rolling_aggregate_raises_on_existing_output_column(ts_df):
    ts_df["value_rolling_mean_5"] = "should-not-be-overwritten"
    with pytest.raises(ValueError):
        rolling_aggregate(ts_df, columns=["value"], window=5, agg="mean")


def test_difference_raises_on_existing_output_column(ts_df):
    ts_df["value_diff_1"] = "should-not-be-overwritten"
    with pytest.raises(ValueError):
        difference(ts_df, columns=["value"], periods=1)


def test_time_weighted_aggregate_raises_on_existing_output_column(ts_df):
    ts_df["value_tw_linear"] = "should-not-be-overwritten"
    with pytest.raises(ValueError):
        time_weighted_aggregate(ts_df, columns=["value"], date_col="date", decay="linear", window=5)
