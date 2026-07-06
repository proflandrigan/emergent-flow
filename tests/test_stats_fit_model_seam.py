"""Seam tests for ``ef.stats.fit_model`` and the model allow-list registry (Epic 12, Story 2).

Covers the single fit-model seam every archetype node routes through: typed errors on bad
model/spec, determinism, no input-frame mutation, and the ``FittedStatsModel`` result-payload
degrade path (live statsmodels results object never serialized). The seed model is ``"OLS"``;
GLM/MixedLM/GAM/Bayesian are later stories.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from emergentflow.api import PUBLIC_OPS, is_inspectable
from emergentflow.server.payload import to_payload
from emergentflow.stats import FittedStatsModel, fit_model
from emergentflow.stats.errors import (
    InvalidModelSpecError,
    MissingOptionalDependencyError,
    UnknownModelError,
)
from emergentflow.stats.registry import ModelSpec, register_model
from emergentflow.stats.shapes import COEFFICIENT_COLUMNS


def _make_regression_df(seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    x = rng.normal(size=40)
    return pd.DataFrame({"x": x, "y": 2.0 * x + 1.0 + rng.normal(scale=0.1, size=40)})


def test_fit_model_is_registered_public_op():
    assert "ef.stats.fit_model" in PUBLIC_OPS


def test_fit_ols_returns_inspectable_fitted_stats_model():
    df = _make_regression_df()
    fm = fit_model(df, model="OLS", spec={"target": "y", "fixed_effects": ["x"]})
    assert isinstance(fm, FittedStatsModel)
    assert is_inspectable(fm)
    assert list(fm.coefficients.columns) == list(COEFFICIENT_COLUMNS)
    assert list(fm.coefficients["term"]) == ["Intercept", "x"]
    assert {"rsquared", "aic", "bic", "loglik", "n_obs", "converged"} <= set(fm.fit_stats)


def test_fit_ols_slope_recovered():
    df = _make_regression_df()
    fm = fit_model(df, model="OLS", spec={"target": "y", "fixed_effects": ["x"]})
    slope = float(fm.coefficients.set_index("term").loc["x", "estimate"])
    assert slope == pytest.approx(2.0, abs=0.1)


def test_unknown_model_key_raises():
    df = _make_regression_df()
    with pytest.raises(UnknownModelError):
        fit_model(df, model="NotAModel", spec={"target": "y"})


def test_missing_required_spec_field_raises():
    df = _make_regression_df()
    with pytest.raises(InvalidModelSpecError):
        fit_model(df, model="OLS", spec={"fixed_effects": ["x"]})


def test_unknown_spec_field_raises():
    df = _make_regression_df()
    with pytest.raises(InvalidModelSpecError):
        fit_model(df, model="OLS", spec={"target": "y", "bogus": 1})


def test_target_not_a_column_raises():
    df = _make_regression_df()
    with pytest.raises(InvalidModelSpecError):
        fit_model(df, model="OLS", spec={"target": "nope", "fixed_effects": ["x"]})


def test_fixed_effect_not_a_column_raises():
    df = _make_regression_df()
    with pytest.raises(InvalidModelSpecError):
        fit_model(df, model="OLS", spec={"target": "y", "fixed_effects": ["z"]})


def test_fit_model_is_deterministic():
    df = _make_regression_df()
    a = fit_model(df, model="OLS", spec={"target": "y", "fixed_effects": ["x"]})
    b = fit_model(df, model="OLS", spec={"target": "y", "fixed_effects": ["x"]})
    pd.testing.assert_frame_equal(a.coefficients, b.coefficients)
    assert a.fit_stats == b.fit_stats


def test_fit_model_does_not_mutate_input():
    df = _make_regression_df()
    before = df.copy(deep=True)
    fit_model(df, model="OLS", spec={"target": "y", "fixed_effects": ["x"]})
    pd.testing.assert_frame_equal(df, before)


def test_live_results_object_never_serialized_in_payload():
    df = _make_regression_df()
    fm = fit_model(df, model="OLS", spec={"target": "y", "fixed_effects": ["x"]})
    payload = to_payload(fm)
    assert payload["kind"] == "record"
    # the live statsmodels results object degrades, the tidy frames render as tables
    assert payload["fields"]["results"]["kind"] == "unsupported"
    assert payload["fields"]["coefficients"]["kind"] == "table"
    assert payload["fields"]["fit_stats"]["kind"] == "json"


def test_missing_optional_dependency_raises_typed_error(monkeypatch):
    # Register a throwaway model that needs the [bayes] extra (absent in the base env), then
    # confirm fit_model raises the typed MissingOptionalDependencyError, not an opaque ImportError.
    def _never_called(df, spec):  # pragma: no cover - must not run
        raise AssertionError("fitter must not run when the required extra is absent")

    register_model(
        ModelSpec(
            key="_TestBayesModel",
            archetype="bayesian_fit",
            fitter=_never_called,
            required_spec_fields=("target",),
            requires_extra="emergentflow[bayes]",
        )
    )
    try:
        df = _make_regression_df()
        with pytest.raises(MissingOptionalDependencyError):
            fit_model(df, model="_TestBayesModel", spec={"target": "y"})
    finally:
        # keep the module-level registry clean for other tests
        from emergentflow.stats import registry as _reg

        _reg._REGISTRY.pop("_TestBayesModel", None)
