"""
emergentflow.stats.catalog
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Seed model catalog for Emergent Flow's statistics families (Epic 12, Story 2).

Importing this module registers a small, curated set of model allow-list entries into
``emergentflow.stats.registry`` as an import-time side effect, mirroring ``emergentflow.ml.catalog``
and ``emergentflow.types.catalog``.

This is a SEED set so the ``ef.stats.fit_model`` seam and its tests have a representative model to
exercise. It is deliberately NOT the full catalog -- GLM/MixedLM/GAM/diagnostics/Bayesian are
widened across Epic 12 Stories 4-7 as reviewed allow-list changes, not enumerated here.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import statsmodels.formula.api as smf

from emergentflow.stats.models import FittedStatsModel
from emergentflow.stats.registry import ModelSpec, register_model
from emergentflow.stats.shapes import DIAGNOSTIC_COLUMNS
from emergentflow.stats.summaries import ols_coefficient_frame, ols_fit_stats


def _ols_formula(spec: dict[str, Any]) -> str:
    """Assemble a Patsy formula ``target ~ f1 + f2 + ...`` from the structured spec.

    Formula assembly lives HERE (inside the wrapper family), the single place it happens, so
    ``codegen`` and ``execute`` never build the formula differently (Decision 4 / ADR-0002).
    An empty ``fixed_effects`` fits an intercept-only model (``target ~ 1``).
    """
    target = spec["target"]
    fixed = spec.get("fixed_effects") or []
    rhs = " + ".join(fixed) if fixed else "1"
    return f"{target} ~ {rhs}"


def _fit_ols(df: pd.DataFrame, spec: dict[str, Any]) -> FittedStatsModel:
    """Fit an OLS model from a validated structured spec and wrap it in a FittedStatsModel."""
    formula = _ols_formula(spec)
    results = smf.ols(formula, data=df).fit()
    return FittedStatsModel(
        model="OLS",
        spec=dict(spec),
        coefficients=ols_coefficient_frame(results),
        diagnostics=pd.DataFrame(columns=list(DIAGNOSTIC_COLUMNS)),
        fit_stats=ols_fit_stats(results),
        results=results,
    )


register_model(
    ModelSpec(
        key="OLS",
        archetype="fit_model",
        fitter=_fit_ols,
        required_spec_fields=("target",),
        optional_spec_fields=("fixed_effects",),
        description="Ordinary least squares linear regression (statsmodels).",
    )
)
