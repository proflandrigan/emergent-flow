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
from emergentflow.stats.models import FittedStatsModel
from emergentflow.stats.shapes import DIAGNOSTIC_COLUMNS


def _vif(
    df: pd.DataFrame | None, model: FittedStatsModel | None, spec: dict[str, Any]
) -> pd.DataFrame:
    assert df is not None  # enforced by the shared gate (needs_frame=True)
    columns = spec.get("columns") or list(df.select_dtypes(include="number").columns)
    threshold = float(spec.get("threshold", 5.0))
    exog = sm.add_constant(df[columns]).to_numpy()
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
    assert model is not None  # enforced by the shared gate (needs_model=True)
    resid = model.results.resid
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
    assert model is not None  # enforced by the shared gate (needs_model=True)
    resid = model.results.resid
    exog = model.results.model.exog
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
    assert model is not None  # enforced by the shared gate (needs_model=True)
    resid = model.results.resid
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
