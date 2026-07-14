"""
ADR-0002 equivalence tests for the timeseries node family: running the code from
``compile_to_code``/``preview`` (codegen path) must produce artifacts equivalent to
``execute`` (the reference interpreter path), for every ``timeseries.*`` node.

Forecasting/decomposition nodes (``ForecastArima``, ``ForecastEts``, ``SeasonalDecompose``)
return a dataclass (``ForecastResult``/``DecomposeResult``); those are compared field-by-field
(the DataFrame field with ``pd.testing.assert_frame_equal``, the rest with plain equality).
Transform nodes return a DataFrame directly via the ``result`` OUT port; those are compared
in full with ``pd.testing.assert_frame_equal``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from emergentflow.nodes.examples import (
    ForecastArima,
    ForecastEts,
    SeasonalDecompose,
    TsDifference,
    TsEwma,
    TsLagFeatures,
    TsRollingAggregate,
    TsTimeWeightedAggregate,
)


def _run_codegen(definition, node, scope):
    """exec a node's preview fragment in *scope* and return the updated scope."""
    frag = definition.preview(node)
    exec(frag.render(), scope)  # noqa: S102 -- test-only, on our own emitted code
    return scope


def _ts_df(seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = 60
    dates = pd.date_range("2020-01-01", periods=n, freq="D")
    return pd.DataFrame(
        {
            "date": dates,
            "value": rng.normal(100, 10, size=n).cumsum(),
            "other": rng.normal(50, 5, size=n),
        }
    )


# ---------------------------------------------------------------------------
# Forecasting / decomposition nodes -- dataclass output.
# ---------------------------------------------------------------------------


@pytest.mark.equivalence
def test_forecast_arima_equivalence():
    df = _ts_df()
    defn = ForecastArima()
    node = defn.instantiate(target="value", order=[1, 0, 0], seasonal_order=[0, 0, 0, 0], horizon=5)

    executed = defn.execute(node, inputs={"frame": df.copy()})["result"]
    scope = _run_codegen(defn, node, {"frame": df.copy()})
    codegen_result = scope["result"]

    pd.testing.assert_frame_equal(executed.forecast, codegen_result.forecast)
    assert executed.fit_stats == codegen_result.fit_stats
    assert executed.model == codegen_result.model == "ARIMA"


@pytest.mark.equivalence
def test_forecast_ets_equivalence():
    df = _ts_df()
    defn = ForecastEts()
    node = defn.instantiate(target="value", trend="add", horizon=5)

    executed = defn.execute(node, inputs={"frame": df.copy()})["result"]
    scope = _run_codegen(defn, node, {"frame": df.copy()})
    codegen_result = scope["result"]

    pd.testing.assert_frame_equal(executed.forecast, codegen_result.forecast)
    assert executed.fit_stats == codegen_result.fit_stats
    assert executed.model == codegen_result.model == "ETS"


@pytest.mark.equivalence
def test_seasonal_decompose_equivalence():
    df = _ts_df()
    defn = SeasonalDecompose()
    node = defn.instantiate(target="value", model="additive", period=7)

    executed = defn.execute(node, inputs={"frame": df.copy()})["result"]
    scope = _run_codegen(defn, node, {"frame": df.copy()})
    codegen_result = scope["result"]

    pd.testing.assert_frame_equal(executed.components, codegen_result.components)
    assert executed.model == codegen_result.model == "additive"
    assert executed.period == codegen_result.period == 7


# ---------------------------------------------------------------------------
# Transform nodes -- DataFrame output via the ``result`` OUT port.
# ---------------------------------------------------------------------------


@pytest.mark.equivalence
def test_ewma_equivalence():
    df = _ts_df()
    defn = TsEwma()
    node = defn.instantiate(columns=["value"], span=10)

    executed = defn.execute(node, inputs={"frame": df.copy()})["result"]
    scope = _run_codegen(defn, node, {"frame": df.copy()})
    codegen_result = scope["result"]

    pd.testing.assert_frame_equal(executed, codegen_result)


@pytest.mark.equivalence
def test_lag_features_equivalence():
    df = _ts_df()
    defn = TsLagFeatures()
    node = defn.instantiate(columns=["value"], lags=[1, 3])

    executed = defn.execute(node, inputs={"frame": df.copy()})["result"]
    scope = _run_codegen(defn, node, {"frame": df.copy()})
    codegen_result = scope["result"]

    pd.testing.assert_frame_equal(executed, codegen_result)


@pytest.mark.equivalence
def test_rolling_aggregate_equivalence():
    df = _ts_df()
    defn = TsRollingAggregate()
    node = defn.instantiate(columns=["value"], window=5, agg="mean")

    executed = defn.execute(node, inputs={"frame": df.copy()})["result"]
    scope = _run_codegen(defn, node, {"frame": df.copy()})
    codegen_result = scope["result"]

    pd.testing.assert_frame_equal(executed, codegen_result)


@pytest.mark.equivalence
def test_difference_equivalence():
    df = _ts_df()
    defn = TsDifference()
    node = defn.instantiate(columns=["value"], periods=1)

    executed = defn.execute(node, inputs={"frame": df.copy()})["result"]
    scope = _run_codegen(defn, node, {"frame": df.copy()})
    codegen_result = scope["result"]

    pd.testing.assert_frame_equal(executed, codegen_result)


@pytest.mark.equivalence
def test_time_weighted_aggregate_equivalence():
    df = _ts_df()
    defn = TsTimeWeightedAggregate()
    node = defn.instantiate(columns=["value"], date_col="date", decay="linear", window=5)

    executed = defn.execute(node, inputs={"frame": df.copy()})["result"]
    scope = _run_codegen(defn, node, {"frame": df.copy()})
    codegen_result = scope["result"]

    pd.testing.assert_frame_equal(executed, codegen_result)
