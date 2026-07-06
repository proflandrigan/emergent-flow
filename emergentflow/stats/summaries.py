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

from emergentflow.stats.shapes import COEFFICIENT_COLUMNS


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
