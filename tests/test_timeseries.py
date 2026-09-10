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
from emergentflow.timeseries.errors import TimeseriesError


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


def test_seasonal_decompose_period_too_large_raises_typed_error(ts_df):
    # A period needing more than two cycles than the series holds must surface as
    # the family's typed TimeseriesError, not a raw statsmodels ValueError.
    with pytest.raises(TimeseriesError, match="at least 2 complete cycles"):
        seasonal_decompose(ts_df, target="value", period=len(ts_df))


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


# --------------------------------------------------------------------------
# date-aware mode (issue #164 Gap 5): half_life / unit / anchor / group_col
# --------------------------------------------------------------------------


def test_twa_halflife_returns_named_column_and_handchecked_values():
    dates = pd.to_datetime(["2024-01-01", "2024-01-08", "2024-01-15", "2024-01-22"])
    df = pd.DataFrame({"date": dates, "value": [10.0, 20.0, 30.0, 40.0]})
    result = time_weighted_aggregate(df, columns=["value"], date_col="date", half_life=7)
    assert "value_tw_halflife" in result.columns
    assert "value_tw_linear" not in result.columns
    # anchor defaults to the partition's max date (2024-01-22); weights are
    # 0.5**(delta/7): row0 0.125, row1 0.25, row2 0.5, row3 1.0. Expanding weighted
    # means: r0=10; r1=(10*0.125+20*0.25)/(0.375); r2=...; r3=...
    assert result["value_tw_halflife"].iloc[0] == pytest.approx(10.0)
    assert result["value_tw_halflife"].iloc[1] == pytest.approx(16.6666667, abs=1e-5)
    assert result["value_tw_halflife"].iloc[2] == pytest.approx(24.2857143, abs=1e-5)
    assert result["value_tw_halflife"].iloc[3] == pytest.approx(32.6666667, abs=1e-5)


def test_twa_halflife_anchor_as_fixed_timestamp():
    dates = pd.to_datetime(["2024-01-01", "2024-01-08", "2024-01-15"])
    df = pd.DataFrame({"date": dates, "value": [10.0, 20.0, 30.0]})
    result = time_weighted_aggregate(
        df, columns=["value"], date_col="date", half_life=7, anchor="2024-01-15"
    )
    # same as default-anchor (max date = 2024-01-15)
    assert result["value_tw_halflife"].iloc[1] == pytest.approx(16.6666667, abs=1e-5)


def test_twa_halflife_anchor_as_column():
    dates = pd.to_datetime(["2024-01-01", "2024-01-08", "2024-01-15"])
    df = pd.DataFrame({"date": dates, "value": [10.0, 20.0, 30.0], "meas": ["2024-01-20"] * 3})
    result = time_weighted_aggregate(
        df, columns=["value"], date_col="date", half_life=7, anchor="meas"
    )
    assert result["value_tw_halflife"].iloc[1] == pytest.approx(16.6666667, abs=1e-5)


def test_twa_halflife_group_col_partitions():
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01", "2024-01-08", "2024-01-01", "2024-01-08"]),
            "value": [10.0, 20.0, 100.0, 200.0],
            "subj": ["a", "a", "b", "b"],
        }
    )
    result = time_weighted_aggregate(
        df, columns=["value"], date_col="date", half_life=7, group_col="subj"
    )
    # subject a: [10, 16.667]; subject b: [100, 166.667] -- independently weighted
    assert result["value_tw_halflife"].tolist() == pytest.approx(
        [10.0, 16.6666667, 100.0, 166.6666667]
    )


def test_twa_halflife_invalid_half_life_raises():
    df = pd.DataFrame({"date": pd.to_datetime(["2024-01-01", "2024-01-08"]), "value": [10.0, 20.0]})
    with pytest.raises(TimeseriesError, match="half_life"):
        time_weighted_aggregate(df, columns=["value"], date_col="date", half_life=0)


def test_twa_halflife_invalid_unit_raises():
    df = pd.DataFrame({"date": pd.to_datetime(["2024-01-01", "2024-01-08"]), "value": [10.0, 20.0]})
    with pytest.raises(TimeseriesError, match="unit"):
        time_weighted_aggregate(df, columns=["value"], date_col="date", half_life=7, unit="bogus")


def _three_weekly_rows() -> pd.DataFrame:
    dates = pd.to_datetime(["2024-01-01", "2024-01-08", "2024-01-15"])
    return pd.DataFrame({"date": dates, "value": [10.0, 20.0, 30.0]})


def test_twa_halflife_sub_day_units_do_not_underflow():
    df = _three_weekly_rows()
    # half_life = 1 minute on weekly data: older rows are (correctly) negligible, never NaN.
    out = time_weighted_aggregate(df, columns=["value"], date_col="date", half_life=1, unit="min")
    assert np.isfinite(out["value_tw_halflife"]).all()
    assert out["value_tw_halflife"].tolist() == pytest.approx([10.0, 20.0, 30.0], abs=1e-6)
    # ... a huge half-life degrades gracefully to the plain running mean ...
    out = time_weighted_aggregate(df, columns=["value"], date_col="date", half_life=1e5, unit="D")
    assert out["value_tw_halflife"].tolist() == pytest.approx([10.0, 15.0, 20.0], abs=1e-3)
    # ... and one beyond pandas' Timedelta range is a typed error, not an OverflowError.
    with pytest.raises(TimeseriesError, match="half_life"):
        time_weighted_aggregate(df, columns=["value"], date_col="date", half_life=1e9, unit="D")


def test_twa_halflife_matches_pandas_ewm_on_hourly_data():
    rng = np.random.default_rng(0)
    idx = pd.date_range("2024-01-01", periods=17520, freq="h")
    df = pd.DataFrame({"date": idx, "value": rng.normal(size=len(idx)).cumsum()})
    out = time_weighted_aggregate(df, columns=["value"], date_col="date", half_life=6, unit="h")
    expected = df["value"].ewm(halflife=pd.Timedelta(hours=6), times=idx).mean()
    assert out["value_tw_halflife"].notna().all()
    np.testing.assert_allclose(out["value_tw_halflife"].to_numpy(), expected.to_numpy())


def test_twa_halflife_anchor_is_an_as_of_cutoff():
    df = _three_weekly_rows()
    base = time_weighted_aggregate(df, columns=["value"], date_col="date", half_life=7)
    # An anchor at or after every date changes nothing (a constant factor cancels).
    far = time_weighted_aggregate(
        df, columns=["value"], date_col="date", half_life=7, anchor="2100-01-01"
    )
    pd.testing.assert_series_equal(far["value_tw_halflife"], base["value_tw_halflife"])
    # An anchor between rows freezes later rows at the last observation on or before it.
    mid = time_weighted_aggregate(
        df, columns=["value"], date_col="date", half_life=7, anchor="2024-01-08"
    )
    assert mid["value_tw_halflife"].tolist() == pytest.approx([10.0, 16.6666667, 16.6666667])
    # An anchor before every date knows nothing.
    early = time_weighted_aggregate(
        df, columns=["value"], date_col="date", half_life=7, anchor="2000-01-01"
    )
    assert early["value_tw_halflife"].isna().all()


def test_twa_halflife_per_row_anchor_column_is_as_of():
    df = _three_weekly_rows().assign(asof=["2024-01-01", "2024-01-08", "2024-01-08"])
    out = time_weighted_aggregate(
        df, columns=["value"], date_col="date", half_life=7, anchor="asof"
    )
    assert out["value_tw_halflife"].tolist() == pytest.approx([10.0, 16.6666667, 16.6666667])


def test_twa_halflife_sorts_by_date_within_partition():
    df = _three_weekly_rows()
    reversed_df = df.iloc[::-1].reset_index(drop=True)
    out = time_weighted_aggregate(reversed_df, columns=["value"], date_col="date", half_life=7)
    # Row order is irrelevant: the 2024-01-15 row still sees only its past.
    by_date = out.set_index("date")["value_tw_halflife"]
    assert by_date[pd.Timestamp("2024-01-01")] == pytest.approx(10.0)
    assert by_date[pd.Timestamp("2024-01-08")] == pytest.approx(16.6666667, abs=1e-5)
    assert by_date[pd.Timestamp("2024-01-15")] == pytest.approx(24.2857143, abs=1e-5)


def test_twa_halflife_nan_values_are_skipped():
    df = _three_weekly_rows()
    df.loc[1, "value"] = np.nan
    out = time_weighted_aggregate(df, columns=["value"], date_col="date", half_life=7)
    # row1 has only row0 observed; row2 mixes rows 0 and 2 with weights 0.25 and 1.
    assert out["value_tw_halflife"].tolist() == pytest.approx([10.0, 10.0, 26.0], abs=1e-6)


def test_twa_halflife_rolling_window_span_guard():
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2000-01-01", "2020-01-01", "2024-01-01"]),
            "value": [1.0, 2.0, 3.0],
        }
    )
    with pytest.raises(TimeseriesError, match="half-lives"):
        time_weighted_aggregate(
            df, columns=["value"], date_col="date", half_life=1, unit="s", window=2
        )
    # A well-conditioned rolling window matches the hand computation.
    out = time_weighted_aggregate(
        _three_weekly_rows(), columns=["value"], date_col="date", half_life=7, window=2
    )
    assert np.isnan(out["value_tw_halflife"].iloc[0])
    assert out["value_tw_halflife"].iloc[1] == pytest.approx((10 * 0.5 + 20) / 1.5)
    assert out["value_tw_halflife"].iloc[2] == pytest.approx((20 * 0.5 + 30) / 1.5)


def test_twa_positional_group_col_tolerates_duplicate_index():
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01", "2024-01-08", "2024-01-01", "2024-01-08"]),
            "value": [10.0, 20.0, 100.0, 200.0],
            "subj": ["a", "a", "b", "b"],
        },
        index=[0, 0, 1, 1],
    )
    out = time_weighted_aggregate(df, columns=["value"], date_col="date", group_col="subj")
    # linear weights 1..n per subject: [10, (10*1 + 20*2)/3], [100, (100 + 400)/3]
    assert out["value_tw_linear"].tolist() == pytest.approx([10.0, 16.6666667, 100.0, 166.6666667])


def test_twa_group_col_categorical_with_unused_categories():
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01", "2024-01-08", "2024-01-01", "2024-01-08"]),
            "value": [10.0, 20.0, 100.0, 200.0],
            "subj": pd.Categorical(["a", "a", "b", "b"], categories=["a", "b", "c"]),
        }
    )
    pos = time_weighted_aggregate(df, columns=["value"], date_col="date", group_col="subj")
    assert pos["value_tw_linear"].notna().all()
    dated = time_weighted_aggregate(
        df, columns=["value"], date_col="date", half_life=7, group_col="subj"
    )
    assert dated["value_tw_halflife"].tolist() == pytest.approx(
        [10.0, 16.6666667, 100.0, 166.6666667]
    )


def test_twa_halflife_tz_aware_dates_with_anchor():
    naive = _three_weekly_rows()
    aware = naive.assign(date=naive["date"].dt.tz_localize("America/New_York"))
    expected = time_weighted_aggregate(
        naive, columns=["value"], date_col="date", half_life=7, anchor="2024-01-08"
    )
    out = time_weighted_aggregate(
        aware, columns=["value"], date_col="date", half_life=7, anchor="2024-01-08"
    )
    assert out["value_tw_halflife"].tolist() == pytest.approx(
        expected["value_tw_halflife"].tolist()
    )


def test_twa_halflife_empty_frame():
    df = pd.DataFrame({"date": pd.to_datetime([]), "value": pd.Series([], dtype=float)})
    out = time_weighted_aggregate(df, columns=["value"], date_col="date", half_life=7)
    assert list(out.columns) == ["date", "value", "value_tw_halflife"]
    assert out.empty


def test_twa_halflife_nat_dates_raise():
    df = _three_weekly_rows()
    df.loc[1, "date"] = pd.NaT
    with pytest.raises(TimeseriesError, match="NaT"):
        time_weighted_aggregate(df, columns=["value"], date_col="date", half_life=7)


@pytest.mark.parametrize("bad", ["7", float("nan"), float("inf"), -1, 0, True])
def test_twa_halflife_rejects_bad_half_life(bad):
    with pytest.raises(TimeseriesError, match="half_life"):
        time_weighted_aggregate(
            _three_weekly_rows(), columns=["value"], date_col="date", half_life=bad
        )


@pytest.mark.parametrize("bad_unit", [1, None, "", "bogus"])
def test_twa_halflife_rejects_bad_unit(bad_unit):
    with pytest.raises(TimeseriesError, match="unit"):
        time_weighted_aggregate(
            _three_weekly_rows(), columns=["value"], date_col="date", half_life=7, unit=bad_unit
        )


def test_twa_halflife_mistyped_anchor_column_raises_typed_error():
    df = _three_weekly_rows().assign(measurement=["2024-01-20"] * 3)
    with pytest.raises(TimeseriesError, match="anchor"):
        time_weighted_aggregate(
            df, columns=["value"], date_col="date", half_life=7, anchor="measurment"
        )
