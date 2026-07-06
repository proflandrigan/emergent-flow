"""
emergentflow.stats.shapes
~~~~~~~~~~~~~~~~~~~~~~~~~~
Canonical tidy-frame column schemas for the stats families (Epic 12, Story 3).

Defined once here so every family's summary builder produces frames with a stable, uniform
schema, and the golden/equivalence tests can key on it. The frequentist coefficient frame and the
Bayesian posterior-summary frame are separate shapes because their columns differ in kind
(SE/statistic/p-value vs. posterior sd/HDI/r_hat/ess).
"""

from __future__ import annotations

#: Frequentist fixed-effect / coefficient frame (OLS/WLS/GLS, GLM, MixedLM fixed effects, GAM).
COEFFICIENT_COLUMNS: tuple[str, ...] = (
    "term",
    "estimate",
    "std_err",
    "statistic",
    "p_value",
    "ci_low",
    "ci_high",
)

#: Diagnostic frame (VIF, normality/heteroscedasticity/autocorrelation tests, etc.).
DIAGNOSTIC_COLUMNS: tuple[str, ...] = (
    "diagnostic",
    "statistic",
    "p_value",
    "detail",
)

#: Bayesian posterior-summary frame (arviz.summary-derived; Story 7).
POSTERIOR_COLUMNS: tuple[str, ...] = (
    "term",
    "mean",
    "sd",
    "hdi_low",
    "hdi_high",
    "r_hat",
    "ess_bulk",
)
