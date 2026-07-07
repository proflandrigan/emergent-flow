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

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from statsmodels.gam.api import BSplines, GLMGam

from emergentflow.stats.errors import InvalidModelSpecError
from emergentflow.stats.models import FittedStatsModel
from emergentflow.stats.registry import ModelSpec, register_model
from emergentflow.stats.shapes import DIAGNOSTIC_COLUMNS
from emergentflow.stats.summaries import (
    bayesian_fit_stats,
    bayesian_posterior_frame,
    gam_coefficient_frame,
    gam_fit_stats,
    glm_fit_stats,
    mixedlm_coefficient_frame,
    mixedlm_fit_stats,
    ols_coefficient_frame,
    ols_fit_stats,
)

_GLM_FAMILIES: dict[str, Any] = {
    "gaussian": sm.families.Gaussian,
    "binomial": sm.families.Binomial,
    "poisson": sm.families.Poisson,
    "negativebinomial": sm.families.NegativeBinomial,
    "gamma": sm.families.Gamma,
}

_GLM_LINKS: dict[str, dict[str, Any]] = {
    "gaussian": {
        "identity": sm.families.links.Identity,
        "log": sm.families.links.Log,
        "inverse": sm.families.links.InversePower,
    },
    "binomial": {
        "logit": sm.families.links.Logit,
        "probit": sm.families.links.Probit,
        "cloglog": sm.families.links.CLogLog,
    },
    "poisson": {
        "log": sm.families.links.Log,
        "identity": sm.families.links.Identity,
        "sqrt": sm.families.links.Sqrt,
    },
    "negativebinomial": {
        "log": sm.families.links.Log,
        "identity": sm.families.links.Identity,
    },
    "gamma": {
        "inverse": sm.families.links.InversePower,
        "log": sm.families.links.Log,
        "identity": sm.families.links.Identity,
    },
}


def _patsy_term(column: str) -> str:
    """Render *column* as a Patsy formula term, quoting via ``Q()`` only when required.

    A bare identifier-like column name (e.g. ``"x"``) is used as-is so the fitted term name
    matches the column name exactly (the coefficient frame and callers key on it). A column name
    containing spaces or Patsy operator characters (``+ - * / ~ ( )``) is not a valid bare
    identifier and would otherwise be silently misparsed as formula syntax even though it passed
    the "column exists in the frame" check; ``Q(repr(column))`` treats it as a literal reference.
    """
    return column if column.isidentifier() else f"Q({column!r})"


def _ols_formula(spec: dict[str, Any]) -> str:
    """Assemble a Patsy formula ``target ~ f1 + f2 + ...`` from the structured spec.

    Formula assembly lives HERE (inside the wrapper family), the single place it happens, so
    ``codegen`` and ``execute`` never build the formula differently (Decision 4 / ADR-0002).
    An empty ``fixed_effects`` fits an intercept-only model (``target ~ 1``).
    """
    target = spec["target"]
    fixed = spec.get("fixed_effects") or []
    rhs = " + ".join(_patsy_term(col) for col in fixed) if fixed else "1"
    return f"{_patsy_term(target)} ~ {rhs}"


def _fit_ols(df: pd.DataFrame, spec: dict[str, Any]) -> FittedStatsModel:
    """Fit an OLS model from a validated structured spec and wrap it in a FittedStatsModel."""
    formula = _ols_formula(spec)
    results = smf.ols(formula, data=df).fit()
    fixed = spec.get("fixed_effects") or []
    # Undo Q()-quoting in the fitted term names so the tidy coefficient frame reports the raw
    # column name a caller passed in, not the internal Patsy formula artifact.
    term_map = {_patsy_term(col): col for col in fixed}
    coefficients = ols_coefficient_frame(results)
    coefficients["term"] = coefficients["term"].map(lambda t: term_map.get(t, t))
    return FittedStatsModel(
        model="OLS",
        spec=dict(spec),
        coefficients=coefficients,
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


def _fit_wls(df: pd.DataFrame, spec: dict[str, Any]) -> FittedStatsModel:
    """Fit a WLS model from a validated structured spec."""
    formula = _ols_formula(spec)
    weights = df[spec["weights"]]
    results = smf.wls(formula, data=df, weights=weights).fit()
    fixed = spec.get("fixed_effects") or []
    term_map = {_patsy_term(col): col for col in fixed}
    coefficients = ols_coefficient_frame(results)
    coefficients["term"] = coefficients["term"].map(lambda t: term_map.get(t, t))
    return FittedStatsModel(
        model="WLS",
        spec=dict(spec),
        coefficients=coefficients,
        diagnostics=pd.DataFrame(columns=list(DIAGNOSTIC_COLUMNS)),
        fit_stats=ols_fit_stats(results),
        results=results,
    )


register_model(
    ModelSpec(
        key="WLS",
        archetype="fit_model",
        fitter=_fit_wls,
        required_spec_fields=("target", "weights"),
        optional_spec_fields=("fixed_effects",),
        description="Weighted least squares linear regression (statsmodels).",
    )
)


def _fit_gls(df: pd.DataFrame, spec: dict[str, Any]) -> FittedStatsModel:
    """Fit a GLS model with the default (identity) covariance structure.

    Custom sigma/covariance structure is deferred (see docs/stats-viz-design.md); this entry
    exists so GLS is a selectable, distinct model key using statsmodels' own GLS estimator.
    """
    formula = _ols_formula(spec)
    results = smf.gls(formula, data=df).fit()
    fixed = spec.get("fixed_effects") or []
    term_map = {_patsy_term(col): col for col in fixed}
    coefficients = ols_coefficient_frame(results)
    coefficients["term"] = coefficients["term"].map(lambda t: term_map.get(t, t))
    return FittedStatsModel(
        model="GLS",
        spec=dict(spec),
        coefficients=coefficients,
        diagnostics=pd.DataFrame(columns=list(DIAGNOSTIC_COLUMNS)),
        fit_stats=ols_fit_stats(results),
        results=results,
    )


register_model(
    ModelSpec(
        key="GLS",
        archetype="fit_model",
        fitter=_fit_gls,
        required_spec_fields=("target",),
        optional_spec_fields=("fixed_effects",),
        description="Generalized least squares, default covariance (statsmodels).",
    )
)


def _fit_glm(df: pd.DataFrame, spec: dict[str, Any]) -> FittedStatsModel:
    """Fit a GLM model from a validated structured spec."""
    formula = _ols_formula(spec)
    family_key = spec["family"]
    family_cls = _GLM_FAMILIES[family_key]
    link_key = spec.get("link") or next(iter(_GLM_LINKS[family_key]))
    link_cls = _GLM_LINKS[family_key][link_key]
    glm_kwargs: dict[str, Any] = {"family": family_cls(link=link_cls())}
    if "weights" in spec and spec["weights"] is not None:
        glm_kwargs["var_weights"] = df[spec["weights"]]
    results = smf.glm(formula, data=df, **glm_kwargs).fit()
    fixed = spec.get("fixed_effects") or []
    term_map = {_patsy_term(col): col for col in fixed}
    coefficients = ols_coefficient_frame(results)
    coefficients["term"] = coefficients["term"].map(lambda t: term_map.get(t, t))
    return FittedStatsModel(
        model="GLM",
        spec=dict(spec),
        coefficients=coefficients,
        diagnostics=pd.DataFrame(columns=list(DIAGNOSTIC_COLUMNS)),
        fit_stats=glm_fit_stats(results),
        results=results,
    )


register_model(
    ModelSpec(
        key="GLM",
        archetype="fit_model",
        fitter=_fit_glm,
        required_spec_fields=("target", "family"),
        optional_spec_fields=("fixed_effects", "link", "weights"),
        description="Generalized linear model (Gaussian/Binomial/Poisson/NegativeBinomial/Gamma "
        "families, statsmodels).",
    )
)


def _mixedlm_re_formula(random_effects: list[str] | None) -> str | None:
    """Build the ``re_formula`` for random slopes; ``None`` means random-intercept-only
    (statsmodels' default when ``re_formula`` is omitted)."""
    if not random_effects:
        return None
    return "~ " + " + ".join(_patsy_term(col) for col in random_effects)


def _fit_mixedlm(df: pd.DataFrame, spec: dict[str, Any]) -> FittedStatsModel:
    """Fit a MixedLM (hierarchical/multilevel) model: fixed + random effects, grouped.

    Uses REML (statsmodels' default ``.fit()``, no ``reml=False`` override) -- see this
    module's docstring / docs/stats-viz-design.md for why AIC/BIC may be NaN under REML, and
    why the generic ``ols_coefficient_frame`` helper is NOT reused here (MixedLM's ``.params``
    mixes in variance components at the wrong scale; see ``mixedlm_coefficient_frame``).
    """
    formula = _ols_formula(spec)
    random_effects = spec.get("random_effects") or []
    re_formula = _mixedlm_re_formula(random_effects)
    groups = df[spec["groups"]]
    model = smf.mixedlm(formula, data=df, groups=groups, re_formula=re_formula)
    results = model.fit()

    fixed = spec.get("fixed_effects") or []
    term_map = {_patsy_term(col): col for col in fixed}
    coefficients = mixedlm_coefficient_frame(results)
    coefficients["term"] = coefficients["term"].map(lambda t: term_map.get(t, t))
    return FittedStatsModel(
        model="MixedLM",
        spec=dict(spec),
        coefficients=coefficients,
        diagnostics=pd.DataFrame(columns=list(DIAGNOSTIC_COLUMNS)),
        fit_stats=mixedlm_fit_stats(results),
        results=results,
    )


register_model(
    ModelSpec(
        key="MixedLM",
        archetype="fit_model",
        fitter=_fit_mixedlm,
        required_spec_fields=("target", "groups"),
        optional_spec_fields=("fixed_effects", "random_effects"),
        description="Linear mixed-effects / hierarchical model with random intercepts and "
        "slopes, grouped (statsmodels MixedLM).",
    )
)


def _fit_gam(df: pd.DataFrame, spec: dict[str, Any]) -> FittedStatsModel:
    """Fit an (unpenalized) GAM: linear terms + B-spline smooth terms (statsmodels GLMGam).

    No smoothing-penalty selection (no ``alpha``/``select_penweight``) -- see this module's
    GAM section docstring / docs/stats-viz-design.md for why that's deferred, not a bug.
    """
    smooth_terms = spec["smooth_terms"]
    if not isinstance(smooth_terms, (list, tuple)) or not smooth_terms:
        raise InvalidModelSpecError(
            "GAM 'smooth_terms' must be a non-empty list of "
            "{'column': str, 'df': int, 'degree': int} dicts."
        )
    smooth_columns: list[str] = []
    smooth_dfs: list[int] = []
    smooth_degrees: list[int] = []
    for term in smooth_terms:
        if not isinstance(term, dict) or "column" not in term:
            raise InvalidModelSpecError(
                f"each GAM smooth term must be a dict with a 'column' key, got {term!r}."
            )
        col = term["column"]
        if col not in df.columns:
            raise InvalidModelSpecError(
                f"GAM smooth term column {col!r} is not in the input frame; "
                f"available columns: {sorted(df.columns)!r}."
            )
        smooth_columns.append(col)
        smooth_dfs.append(int(term.get("df", 4)))
        smooth_degrees.append(int(term.get("degree", 3)))

    linear_terms = list(spec.get("linear_terms") or [])
    target = spec["target"]

    family_key = spec.get("family") or "gaussian"
    family_cls = _GLM_FAMILIES[family_key]
    link_key = spec.get("link") or next(iter(_GLM_LINKS[family_key]))
    link_cls = _GLM_LINKS[family_key][link_key]

    x_spline = df[smooth_columns].to_numpy()
    bs = BSplines(x_spline, df=smooth_dfs, degree=smooth_degrees)
    if linear_terms:
        exog_linear = sm.add_constant(df[linear_terms])
    else:
        exog_linear = pd.DataFrame({"const": np.ones(len(df))}, index=df.index)

    model = GLMGam(df[target], exog=exog_linear, smoother=bs, family=family_cls(link=link_cls()))
    results = model.fit()

    coefficients = gam_coefficient_frame(results, linear_terms, smooth_columns)
    return FittedStatsModel(
        model="GAM",
        spec=dict(spec),
        coefficients=coefficients,
        diagnostics=pd.DataFrame(columns=list(DIAGNOSTIC_COLUMNS)),
        fit_stats=gam_fit_stats(results),
        results=results,
    )


register_model(
    ModelSpec(
        key="GAM",
        archetype="fit_model",
        fitter=_fit_gam,
        required_spec_fields=("target", "smooth_terms"),
        optional_spec_fields=("linear_terms", "family", "link"),
        description="Generalized additive model: linear terms + B-spline smooth terms "
        "(statsmodels GLMGam, unpenalized).",
    )
)


_BAMBI_FAMILIES: dict[str, str] = {
    "gaussian": "gaussian",
    "binomial": "bernoulli",
    "poisson": "poisson",
    "negativebinomial": "negativebinomial",
    "gamma": "gamma",
}


def _bayesian_formula(spec: dict[str, Any]) -> str:
    """Assemble a bambi formula: fixed effects + an optional ``(re_terms | groups)`` random
    part, reusing ``_ols_formula`` for the fixed-effects RHS and the same ``groups``/
    ``random_effects`` structured-spec fields ``MixedLM`` uses (Story 5)."""
    base = _ols_formula(spec)
    groups = spec.get("groups")
    if not groups:
        return base
    random_effects = spec.get("random_effects") or []
    re_term = " + ".join(_patsy_term(c) for c in random_effects) if random_effects else "1"
    return f"{base} + ({re_term} | {_patsy_term(groups)})"


def _fit_bayesian_glm(df: pd.DataFrame, spec: dict[str, Any]) -> FittedStatsModel:
    """Fit a Bayesian GLM (optionally hierarchical) via bambi/PyMC, summarized with ArviZ.

    Requires ``emergentflow[bayes]`` (checked by ``fit_model`` before this fitter ever runs).
    ``seed``/``draws``/``tune``/``chains`` are all REQUIRED spec fields (not defaulted) so the
    ADR-0002 equivalence gate can pin exact MCMC reproducibility -- see
    docs/stats-viz-design.md Decision 5. No prior-override surface, no custom link -- bambi's
    own defaults are used (deferred enhancements, not shipped here).
    """
    import bambi as bmb

    formula = _bayesian_formula(spec)
    family_key = spec.get("family") or "gaussian"
    bambi_family = _BAMBI_FAMILIES[family_key]

    model = bmb.Model(formula, df, family=bambi_family)
    idata = model.fit(
        draws=int(spec["draws"]),
        tune=int(spec["tune"]),
        chains=int(spec["chains"]),
        random_seed=int(spec["seed"]),
        progressbar=False,
    )

    return FittedStatsModel(
        model="BayesianGLM",
        spec=dict(spec),
        coefficients=bayesian_posterior_frame(idata),
        diagnostics=pd.DataFrame(columns=list(DIAGNOSTIC_COLUMNS)),
        fit_stats=bayesian_fit_stats(idata),
        results=idata,
    )


register_model(
    ModelSpec(
        key="BayesianGLM",
        archetype="bayesian_fit",
        fitter=_fit_bayesian_glm,
        required_spec_fields=("target", "seed", "draws", "tune", "chains"),
        optional_spec_fields=("fixed_effects", "random_effects", "groups", "family"),
        requires_extra="emergentflow[bayes]",
        description="Bayesian GLM (optionally hierarchical: random intercepts/slopes via "
        "random_effects/groups), fit via bambi/PyMC, summarized with ArviZ.",
    )
)
