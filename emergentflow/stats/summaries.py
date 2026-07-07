"""
emergentflow.stats.summaries
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Per-family inspectable summary builders for fitted statistical models (Epic 12, Story 2/3).

Each builder takes a live, already-fitted statsmodels results object and returns JSON-native /
tidy-DataFrame data with the canonical schema from ``emergentflow.stats.shapes`` -- never the live
object itself. This is the ``emergentflow.ml.summaries`` analog; it keeps the tidy
coefficient/diagnostic frames uniform across the model catalog so the Results tab and the
equivalence gate key on a stable shape.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from emergentflow.stats.shapes import COEFFICIENT_COLUMNS, POSTERIOR_COLUMNS


def ols_coefficient_frame(results: Any) -> pd.DataFrame:
    """Tidy coefficient frame for an OLS/linear results object, schema COEFFICIENT_COLUMNS.

    One row per model term (including the intercept). ``estimate``/``std_err``/``statistic``/
    ``p_value`` come from statsmodels' ``params``/``bse``/``tvalues``/``pvalues``; ``ci_low``/
    ``ci_high`` from ``conf_int()`` (default 95%).
    """
    conf = results.conf_int()  # DataFrame indexed by term, columns [0, 1]
    rows = []
    for term in results.params.index:
        rows.append(
            {
                "term": str(term),
                "estimate": float(results.params[term]),
                "std_err": float(results.bse[term]),
                "statistic": float(results.tvalues[term]),
                "p_value": float(results.pvalues[term]),
                "ci_low": float(conf.loc[term, 0]),
                "ci_high": float(conf.loc[term, 1]),
            }
        )
    return pd.DataFrame(rows, columns=list(COEFFICIENT_COLUMNS))


def ols_fit_stats(results: Any) -> dict[str, Any]:
    """JSON-native fit statistics for an OLS/linear fit (rsquared/adj/AIC/BIC/loglik/nobs)."""
    return {
        "rsquared": float(results.rsquared),
        "rsquared_adj": float(results.rsquared_adj),
        "aic": float(results.aic),
        "bic": float(results.bic),
        "loglik": float(results.llf),
        "n_obs": int(results.nobs),
        "converged": True,  # OLS is a closed-form solve; always "converged".
    }


def mixedlm_coefficient_frame(results: Any) -> pd.DataFrame:
    """Tidy coefficient frame for a MixedLM fit: fixed effects + variance-component rows.

    Fixed-effect rows use ``fe_params``/``bse_fe`` plus the fixed-effect subset of
    ``tvalues``/``pvalues``/``conf_int()`` (MixedLM's ``params``/``bse`` mix in variance
    components in a reparametrized internal scale that would be misleading to report directly
    -- see ``emergentflow/stats/catalog.py``'s MixedLM fitter docstring). Variance-component rows
    (``"Group Var (...)"`` per random-effect term, ``"Residual Var"``) use the correctly-scaled
    ``cov_re``/``scale`` and leave inferential columns as NaN (not cheaply available in this
    shape from statsmodels).
    """
    fe_index = results.fe_params.index
    conf = results.conf_int().loc[fe_index]
    rows = []
    for term in fe_index:
        rows.append(
            {
                "term": str(term),
                "estimate": float(results.fe_params[term]),
                "std_err": float(results.bse_fe[term]),
                "statistic": float(results.tvalues[term]),
                "p_value": float(results.pvalues[term]),
                "ci_low": float(conf.loc[term, 0]),
                "ci_high": float(conf.loc[term, 1]),
            }
        )
    cov_re = results.cov_re
    for term in cov_re.index:
        rows.append(
            {
                "term": f"Group Var ({term})" if term != "Group" else "Group Var (Intercept)",
                "estimate": float(cov_re.loc[term, term]),
                "std_err": float("nan"),
                "statistic": float("nan"),
                "p_value": float("nan"),
                "ci_low": float("nan"),
                "ci_high": float("nan"),
            }
        )
    rows.append(
        {
            "term": "Residual Var",
            "estimate": float(results.scale),
            "std_err": float("nan"),
            "statistic": float("nan"),
            "p_value": float("nan"),
            "ci_low": float("nan"),
            "ci_high": float("nan"),
        }
    )
    return pd.DataFrame(rows, columns=list(COEFFICIENT_COLUMNS))


def mixedlm_fit_stats(results: Any) -> dict[str, Any]:
    """JSON-native fit statistics for a MixedLM fit, including ICC and convergence status.

    ``icc`` (intraclass correlation) is the random-intercept variance over total variance
    (random-intercept + residual); well-defined for any MixedLM fit since a random intercept is
    always present (statsmodels' default when no ``re_formula`` is given).
    """
    group_var = float(results.cov_re.iloc[0, 0])
    residual_var = float(results.scale)
    total = group_var + residual_var
    icc = group_var / total if total else float("nan")
    return {
        "aic": float(results.aic) if results.aic is not None else float("nan"),
        "bic": float(results.bic) if results.bic is not None else float("nan"),
        "loglik": float(results.llf),
        "n_obs": int(results.nobs),
        "converged": bool(results.converged),
        "icc": icc,
    }


def bayesian_posterior_frame(idata: Any) -> pd.DataFrame:
    """Tidy posterior-summary frame from an ArviZ InferenceData (schema: POSTERIOR_COLUMNS).

    Column names for the two HDI bounds depend on the HDI probability arviz used (e.g.
    ``"hdi_3%"``/``"hdi_97%"`` at the default 94% HDI) -- resolved by position (first two
    ``hdi_``-prefixed columns), not by a hardcoded percentage string, so this doesn't break if
    arviz's default HDI probability ever changes.
    """
    import arviz as az

    summary = pd.DataFrame(az.summary(idata)).reset_index(names="term")
    hdi_cols = [c for c in summary.columns if c.startswith("hdi_")]
    hdi_low_col, hdi_high_col = hdi_cols[0], hdi_cols[1]
    rows = []
    for _, row in summary.iterrows():
        rows.append(
            {
                "term": str(row["term"]),
                "mean": float(row["mean"]),
                "sd": float(row["sd"]),
                "hdi_low": float(row[hdi_low_col]),
                "hdi_high": float(row[hdi_high_col]),
                "r_hat": float(row["r_hat"]),
                "ess_bulk": float(row["ess_bulk"]),
            }
        )
    return pd.DataFrame(rows, columns=list(POSTERIOR_COLUMNS))


def bayesian_fit_stats(idata: Any) -> dict[str, Any]:
    """JSON-native convergence diagnostics for a Bayesian fit (max r_hat, divergences).

    ``converged`` is a simple heuristic (max r_hat < 1.01, the threshold ArviZ's own
    convergence warnings use) -- MCMC convergence is not a single yes/no fact the way a
    closed-form solve is, so this is a documented heuristic, not an authoritative verdict.
    """
    import arviz as az

    summary = az.summary(idata)
    max_r_hat = float(summary["r_hat"].max())
    divergences = int(idata.sample_stats.diverging.sum())
    return {
        "max_r_hat": max_r_hat,
        "divergences": divergences,
        "converged": max_r_hat < 1.01,
        "n_obs": int(idata.observed_data.sizes.get(next(iter(idata.observed_data.sizes)), 0))
        if hasattr(idata, "observed_data")
        else None,
    }


def gam_coefficient_frame(
    results: Any, linear_terms: list[str], smooth_columns: list[str]
) -> pd.DataFrame:
    """Tidy term frame for a GLMGam fit: real stats for linear terms, placeholder rows for
    smooth terms.

    ``results.params``/``.bse``/``.tvalues``/``.pvalues``/``.conf_int()`` are ordered
    ``[const, *linear_terms, <smooth-term basis coefficients...>]`` (statsmodels concatenates the
    linear exog then the spline basis columns) -- the first ``1 + len(linear_terms)`` entries are
    the real, interpretable linear-term stats; everything after that is spline basis coefficients
    with no single interpretable point estimate per smooth term (see the GAM fitter's docstring
    for why this is deferred to Story 9's smooth-plot node, not fabricated here).
    """
    conf = results.conf_int()
    names = ["Intercept", *linear_terms]
    rows = []
    for i, term in enumerate(names):
        rows.append(
            {
                "term": term,
                "estimate": float(results.params.iloc[i]),
                "std_err": float(results.bse.iloc[i]),
                "statistic": float(results.tvalues.iloc[i]),
                "p_value": float(results.pvalues.iloc[i]),
                "ci_low": float(conf.iloc[i, 0]),
                "ci_high": float(conf.iloc[i, 1]),
            }
        )
    for col in smooth_columns:
        rows.append(
            {
                "term": f"s({col})",
                "estimate": float("nan"),
                "std_err": float("nan"),
                "statistic": float("nan"),
                "p_value": float("nan"),
                "ci_low": float("nan"),
                "ci_high": float("nan"),
            }
        )
    return pd.DataFrame(rows, columns=list(COEFFICIENT_COLUMNS))


def gam_fit_stats(results: Any) -> dict[str, Any]:
    """JSON-native fit statistics for a GLMGam fit (AIC/BIC/loglik/nobs/converged)."""
    bic = float(getattr(results, "bic_llf", getattr(results, "bic", float("nan"))))
    return {
        "aic": float(results.aic),
        "bic": bic,
        "loglik": float(results.llf),
        "n_obs": int(results.nobs),
        "converged": bool(results.converged),
    }


def glm_fit_stats(results: Any) -> dict[str, Any]:
    """JSON-native fit statistics for a GLM fit (pseudo-R2/AIC/BIC/loglik/nobs/converged).

    GLM has no closed-form R-squared; ``pseudo_rsquared`` is the McFadden-style
    ``1 - deviance / null_deviance``.
    """
    null_deviance = float(results.null_deviance)
    pseudo_rsquared = (
        1.0 - float(results.deviance) / null_deviance if null_deviance else float("nan")
    )
    bic = float(getattr(results, "bic_llf", getattr(results, "bic", float("nan"))))
    return {
        "pseudo_rsquared": pseudo_rsquared,
        "aic": float(results.aic),
        "bic": bic,
        "loglik": float(results.llf),
        "n_obs": int(results.nobs),
        "converged": bool(results.converged),
    }
