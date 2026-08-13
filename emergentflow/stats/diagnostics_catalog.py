"""
emergentflow.stats.diagnostics_catalog
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Seed diagnostic catalog for Emergent Flow's statistics diagnostic archetype (Epic 12, Story 6).

Importing this module registers a curated set of diagnostic allow-list entries into
``emergentflow.stats.diagnostics`` as an import-time side effect, mirroring
``emergentflow.stats.catalog``.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import statsmodels.api as sm
from statsmodels.stats.diagnostic import het_breuschpagan
from statsmodels.stats.outliers_influence import variance_inflation_factor
from statsmodels.stats.stattools import durbin_watson, jarque_bera

from emergentflow.stats.diagnostics import DiagnosticSpec, register_diagnostic
from emergentflow.stats.errors import InvalidModelSpecError
from emergentflow.stats.models import FittedStatsModel
from emergentflow.stats.shapes import DIAGNOSTIC_COLUMNS


def _model_resid(model: FittedStatsModel) -> Any:
    """Residuals for a fitted model, tolerating GLM-family results.

    OLS/WLS/GLS/MixedLM results expose ``.resid`` directly; GLM/GAM results (``GLMResults``/
    ``GLMGamResults``) don't define ``.resid`` at all and instead expose ``.resid_response``.
    Bayesian results (an ArviZ ``InferenceData``) expose neither, so this raises a typed error
    rather than letting an ``AttributeError`` leak from deep inside statsmodels.
    """
    results = model.results
    resid = getattr(results, "resid", None)
    if resid is None:
        resid = getattr(results, "resid_response", None)
    if resid is None:
        raise InvalidModelSpecError(
            f"model {model.model!r} does not expose residuals; this diagnostic requires a "
            "fitted OLS/WLS/GLS/GLM/MixedLM/GAM model."
        )
    return resid


def _vif(
    df: pd.DataFrame | None, model: FittedStatsModel | None, spec: dict[str, Any]
) -> pd.DataFrame:
    if df is None:
        raise InvalidModelSpecError("diagnostic 'vif' requires a DataFrame input.")
    columns = spec.get("columns") or list(df.select_dtypes(include="number").columns)
    numeric_cols = set(df.select_dtypes(include="number").columns)
    non_numeric = [col for col in columns if col not in numeric_cols]
    if non_numeric:
        raise InvalidModelSpecError(
            f"diagnostic 'vif' requires numeric columns; got non-numeric column(s) {non_numeric!r}."
        )
    threshold = float(spec.get("threshold", 5.0))
    exog = sm.add_constant(df[columns], has_constant="add").to_numpy()
    rows = []
    for i, col in enumerate(columns, start=1):
        vif = float(variance_inflation_factor(exog, i))
        flag = "above threshold" if vif > threshold else "ok"
        rows.append(
            {
                "diagnostic": "VIF",
                "statistic": vif,
                "p_value": float("nan"),
                "detail": f"{col}: {flag} (threshold={threshold})",
            }
        )
    return pd.DataFrame(rows, columns=list(DIAGNOSTIC_COLUMNS))


register_diagnostic(
    DiagnosticSpec(
        key="vif",
        fn=_vif,
        needs_frame=True,
        needs_model=False,
        optional_spec_fields=("columns", "threshold"),
        description="Variance-inflation factor per numeric column (multicollinearity).",
    )
)


def _normality(
    df: pd.DataFrame | None, model: FittedStatsModel | None, spec: dict[str, Any]
) -> pd.DataFrame:
    if model is None:
        raise InvalidModelSpecError("diagnostic 'normality' requires a fitted StatsModel input.")
    resid = _model_resid(model)
    stat, pvalue, skew, kurtosis = jarque_bera(resid)
    row = {
        "diagnostic": "Jarque-Bera",
        "statistic": float(stat),
        "p_value": float(pvalue),
        "detail": f"skew={float(skew):.4f}, kurtosis={float(kurtosis):.4f}",
    }
    return pd.DataFrame([row], columns=list(DIAGNOSTIC_COLUMNS))


register_diagnostic(
    DiagnosticSpec(
        key="normality",
        fn=_normality,
        needs_frame=False,
        needs_model=True,
        description="Jarque-Bera normality test on a fitted model's residuals.",
    )
)


def _heteroscedasticity(
    df: pd.DataFrame | None, model: FittedStatsModel | None, spec: dict[str, Any]
) -> pd.DataFrame:
    if model is None:
        raise InvalidModelSpecError(
            "diagnostic 'heteroscedasticity' requires a fitted StatsModel input."
        )
    resid = _model_resid(model)
    exog = model.results.model.exog
    if exog.shape[1] < 2:
        raise InvalidModelSpecError(
            "diagnostic 'heteroscedasticity' requires a model with at least one "
            "regressor; the fitted model has only an intercept, so the Breusch-Pagan "
            "test cannot be computed."
        )
    lm_stat, lm_pvalue, f_stat, f_pvalue = het_breuschpagan(resid, exog)
    row = {
        "diagnostic": "Breusch-Pagan",
        "statistic": float(lm_stat),
        "p_value": float(lm_pvalue),
        "detail": f"f_statistic={float(f_stat):.4f}, f_p_value={float(f_pvalue):.4f}",
    }
    return pd.DataFrame([row], columns=list(DIAGNOSTIC_COLUMNS))


register_diagnostic(
    DiagnosticSpec(
        key="heteroscedasticity",
        fn=_heteroscedasticity,
        needs_frame=False,
        needs_model=True,
        description="Breusch-Pagan heteroscedasticity test on a fitted model's residuals.",
    )
)


def _autocorrelation(
    df: pd.DataFrame | None, model: FittedStatsModel | None, spec: dict[str, Any]
) -> pd.DataFrame:
    if model is None:
        raise InvalidModelSpecError(
            "diagnostic 'autocorrelation' requires a fitted StatsModel input."
        )
    resid = _model_resid(model)
    dw = durbin_watson(resid)
    row = {
        "diagnostic": "Durbin-Watson",
        "statistic": float(dw),
        "p_value": float("nan"),  # Durbin-Watson has no simple closed-form p-value.
        "detail": "values near 2.0 indicate no autocorrelation; <2 positive, >2 negative.",
    }
    return pd.DataFrame([row], columns=list(DIAGNOSTIC_COLUMNS))


register_diagnostic(
    DiagnosticSpec(
        key="autocorrelation",
        fn=_autocorrelation,
        needs_frame=False,
        needs_model=True,
        description="Durbin-Watson autocorrelation test on a fitted model's residuals.",
    )
)
