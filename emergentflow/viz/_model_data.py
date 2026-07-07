"""
emergentflow.viz._model_data
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Private helpers extracting plot-ready residuals/fitted-values from a fitted ``StatsModel``'s
live results object (Epic 12, Story 9). Shared by the residual, Q-Q, and ACF/PACF model-aware
plots.

Mirrors the residual-fallback logic in ``emergentflow.stats.diagnostics_catalog._model_resid``
(OLS/WLS/GLS/MixedLM expose ``.resid`` directly; GLM/GAM expose ``.resid_response`` instead) --
duplicated here rather than imported, since that function is a private implementation detail of
the diagnostic archetype's own module and this is a separate archetype (viz) reading the same
live results object for a different purpose (plot data, not a diagnostic test statistic).
"""

from __future__ import annotations

from typing import Any

from emergentflow.stats.models import FittedStatsModel
from emergentflow.viz.errors import VizError


def model_residuals(model: FittedStatsModel) -> Any:
    """Residuals for a fitted model, tolerating GLM-family results.

    OLS/WLS/GLS/MixedLM results expose ``.resid`` directly; GLM/GAM results (``GLMResults``/
    ``GLMGamResults``) expose ``.resid_response`` instead. Bayesian results expose neither, so
    this raises a typed :class:`~emergentflow.viz.errors.VizError` rather than letting an
    ``AttributeError`` leak from deep inside statsmodels.
    """
    results = model.results
    resid = getattr(results, "resid", None)
    if resid is None:
        resid = getattr(results, "resid_response", None)
    if resid is None:
        raise VizError(
            f"model {model.model!r} does not expose residuals; this plot requires a fitted "
            "OLS/WLS/GLS/GLM/MixedLM/GAM model."
        )
    return resid


def model_fitted(model: FittedStatsModel) -> Any:
    """Fitted values for a fitted model; raises a typed VizError if unavailable."""
    fitted = getattr(model.results, "fittedvalues", None)
    if fitted is None:
        raise VizError(
            f"model {model.model!r} does not expose fitted values; this plot requires a "
            "fitted OLS/WLS/GLS/GLM/MixedLM/GAM model."
        )
    return fitted
