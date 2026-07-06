"""
emergentflow.stats.models
~~~~~~~~~~~~~~~~~~~~~~~~~~
The shared inspectable representation for fitted statistical models (Epic 12, Story 2).

``FittedStatsModel`` is the ONE dataclass every fit-model archetype (OLS/GLM/MixedLM/GAM and the
optional Bayesian family) rides inside, mirroring ``emergentflow.ml.FittedModel``. The live
statsmodels/Bambi results object rides in the ``results`` field so the model can flow
fit -> plot/diagnostic in-memory (execute) and as a plain variable (compiled code); the dataclass
is inspectable under the ``@public_op`` contract, and on the result-payload contract the
``results`` field degrades to ``{"kind": "unsupported"}`` automatically (``to_payload`` recurses
dataclass fields), while the tidy frames render as tables.

The per-family column *shapes* of ``coefficients``/``diagnostics`` are defined once in
``emergentflow.stats.spec`` (Story 3). Bayesian posterior summaries ride in the same
``coefficients`` frame with family-specific columns (mean/sd/hdi/r_hat/ess); a dedicated
posterior-summary type is deferred to Story 7 if the shared frame proves insufficient.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass
class FittedStatsModel:
    """A fitted statistical model plus inspectable metadata (the Epic 12 model representation).

    Attributes
    ----------
    model: the curated model key that produced this fit (e.g. ``"OLS"``).
    spec: a JSON-native echo of the structured spec used to fit (target, fixed_effects, ...),
        so the fit is self-describing on the result-payload contract.
    coefficients: tidy coefficient/summary frame (per-family columns; see ``stats.spec``).
    diagnostics: tidy diagnostics frame; empty (no rows) when a family surfaces none at fit time.
    fit_stats: JSON-native fit statistics (AIC/BIC/loglik/converged/n_obs/rsquared, ...).
    results: the live statsmodels/Bambi results object; not JSON-serialized -- degrades to
        ``{"kind": "unsupported"}`` on the result-payload contract, never rendered directly.
    """

    model: str
    spec: dict[str, Any]
    coefficients: pd.DataFrame
    diagnostics: pd.DataFrame
    fit_stats: dict[str, Any] = field(default_factory=dict)
    results: Any = None  # live statsmodels/Bambi results object; not JSON-serialized
