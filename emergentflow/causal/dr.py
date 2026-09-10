"""
emergentflow.causal.dr
~~~~~~~~~~~~~~~~~~~~~~~~
Doubly-robust and IPW effect estimation with honest uncertainty (issue #164 Gap 1).

``ef.causal.estimate_effect`` computes an average treatment effect on an observational
sample with acknowledged selection bias, via one of four methods:

* ``"ipw"``               -- inverse-probability weighting (Hajek estimator).
* ``"aipw"``              -- doubly robust augmentation; consistent if EITHER the
    propensity model OR the outcome model is correctly specified.
* ``"matching"``          -- 1:1 nearest-neighbour propensity matching (see matching.py).
* ``"regression_adjust"`` -- OLS of outcome on treatment + covariates.

Inference honours nested/clustered data: ``cluster_col`` routes the SE through the
cluster-robust covariance machinery already built for ``ef.stats.fit_model`` (the
``_cov_kwargs`` path), and ``n_boot`` adds a cluster- or row-bootstrap interval. When
``n_boot=0`` a closed-form SE is used (cluster-robust sandwich across ``cluster_col``
for ``ipw``/``aipw``; the fitted-model SE for ``regression_adjust``; the paired
difference for ``matching``).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import stats as scipy_stats
from sklearn.linear_model import LogisticRegression

from emergentflow.api import public_op
from emergentflow.causal.errors import CausalError, UnknownMethodError
from emergentflow.causal.matching import match_nearest
from emergentflow.causal.propensity import _propensity_design, _validate_binary_treatment
from emergentflow.stats.catalog import _cov_kwargs

__all__ = ["estimate_effect"]

_EFFECT_METHODS = ("ipw", "aipw", "matching", "regression_adjust")
_Z = 1.959963984540054  # z_{0.975}


def _treat_param_name(results: Any, treatment: str) -> str:
    """Return the exact coefficient name for *treatment* in a statsmodels result.

    patsy keeps the bare column name for a plain identifier; a categorical treatment
    would be mangled, but this family requires binary 0/1 so the bare name is expected.
    """
    if treatment in results.params.index:
        return treatment
    for name in results.params.index:
        if name == treatment or name.startswith(f"{treatment}["):
            return name
    raise CausalError(
        f"could not locate the treatment coefficient for {treatment!r} in "
        f"{list(results.params.index)!r}."
    )


def _regression_formula(outcome: str, treatment: str, covariates: list[str] | None) -> str:
    if covariates:
        return f"{outcome} ~ {treatment} + " + " + ".join(covariates)
    return f"{outcome} ~ {treatment}"


def _point_model(
    df: pd.DataFrame,
    *,
    outcome: str,
    treatment: str,
    covariates: list[str] | None,
    method: str,
) -> Callable[[pd.DataFrame], float]:
    """Return a callable computing just the point estimate on any compatible frame."""
    if method == "matching":
        covs = covariates or []

        def _matching_point(d2: pd.DataFrame) -> float:
            pairs = match_nearest(d2, treatment=treatment, covariates=covs, outcome=outcome)
            return float(pairs["difference"].mean())

        return _matching_point

    if method == "regression_adjust":
        formula = _regression_formula(outcome, treatment, covariates)

        def _regress_point(d2: pd.DataFrame) -> float:
            r = smf.ols(formula, data=d2).fit()
            return float(r.params[_treat_param_name(r, treatment)])

        return _regress_point

    covs = covariates or []

    def _score_point(d2: pd.DataFrame) -> float:
        t2 = _validate_binary_treatment(d2, treatment)
        design2 = _propensity_design(d2, covs)
        if method == "aipw":
            return float(_aipw_point(d2, t2, design2, outcome))
        est = LogisticRegression(max_iter=1000).fit(design2, t2)
        p2 = est.predict_proba(design2)[:, 1]
        y2 = d2[outcome].to_numpy()
        tt2 = t2.to_numpy()
        score = (tt2 / np.clip(p2, 1e-6, 1) - (1 - tt2) / np.clip(1 - p2, 1e-6, 1)) * y2
        return float(score.mean())

    return _score_point


def _aipw_point(
    df: pd.DataFrame,
    t: pd.Series,
    design: pd.DataFrame,
    outcome: str,
) -> float:
    """Doubly-robust score averaged over *df* using already-fit inputs' structure.

    Fits per-arm linear outcome models on ``design`` and returns
    ``mean(DR_i)``. Re-fits the propensity model inside (nothing is reused across
    calls, keeping the bootstrap path self-contained).
    """
    from sklearn.linear_model import LogisticRegression

    y = df[outcome].to_numpy()
    tt = t.to_numpy()
    est = LogisticRegression(max_iter=1000).fit(design, t)
    p = est.predict_proba(design)[:, 1]
    X = sm.add_constant(design)
    mu1 = sm.OLS(y[tt == 1], X.iloc[tt == 1]).fit()
    mu0 = sm.OLS(y[tt == 0], X.iloc[tt == 0]).fit()
    m1 = mu1.predict(X)
    m0 = mu0.predict(X)
    dr = (tt / np.clip(p, 1e-6, 1) * (y - m1) + m1) - (
        (1 - tt) / np.clip(1 - p, 1e-6, 1) * (y - m0) + m0
    )
    return float(dr.mean())


def _closed_form(
    df: pd.DataFrame,
    *,
    outcome: str,
    treatment: str,
    covariates: list[str] | None,
    method: str,
    cluster_col: str | None,
) -> tuple[float, float, float, float]:
    """Analytical ``(point, se, ci_low, ci_high)`` with no resampling."""
    t = _validate_binary_treatment(df, treatment)
    n = len(df)

    if method == "regression_adjust":
        formula = _regression_formula(outcome, treatment, covariates)
        spec: dict[str, object] = {"cov_type": "nonrobust"}
        if cluster_col is not None:
            if cluster_col not in df.columns:
                raise CausalError(
                    f"unknown cluster_col {cluster_col!r}; expected one of {list(df.columns)!r}."
                )
            spec = {"cov_type": "cluster", "cov_group": cluster_col}
        cov_kwargs = _cov_kwargs(df, spec)
        results = smf.ols(formula, data=df).fit(**cov_kwargs)
        name = _treat_param_name(results, treatment)
        point = float(results.params[name])
        se = float(results.bse[name])
        lo = float(results.conf_int().loc[name, 0])
        hi = float(results.conf_int().loc[name, 1])
        return point, se, lo, hi

    if method == "matching":
        pairs = match_nearest(df, treatment=treatment, covariates=covariates or [], outcome=outcome)
        diffs = pairs["difference"].to_numpy()
        point = float(diffs.mean())
        se = float(diffs.std(ddof=1) / np.sqrt(len(diffs))) if len(diffs) > 1 else float("nan")
        return point, se, point - _Z * se, point + _Z * se

    # ipw / aipw: influence-function sandwich.
    covs = covariates or []
    design = _propensity_design(df, covs)
    y = df[outcome].to_numpy()
    tt = t.to_numpy()
    est = LogisticRegression(max_iter=1000).fit(design, t)
    p = est.predict_proba(design)[:, 1].clip(1e-6, 1 - 1e-6)

    if method == "ipw":
        score = (tt / p - (1 - tt) / (1 - p)) * y
        point = float(score.mean())
        infl = pd.Series(score - point, index=df.index, dtype=float)
    elif method == "aipw":
        X = sm.add_constant(design)
        mu1 = sm.OLS(y[tt == 1], X.iloc[tt == 1]).fit()
        mu0 = sm.OLS(y[tt == 0], X.iloc[tt == 0]).fit()
        m1 = mu1.predict(X)
        m0 = mu0.predict(X)
        dr = (tt / p * (y - m1) + m1) - ((1 - tt) / (1 - p) * (y - m0) + m0)
        point = float(dr.mean())
        infl = pd.Series(dr - point, index=df.index, dtype=float)
    else:  # pragma: no cover - guarded by _EFFECT_METHODS
        raise UnknownMethodError(f"unknown method {method!r}.")

    if cluster_col is not None:
        if cluster_col not in df.columns:
            raise CausalError(
                f"unknown cluster_col {cluster_col!r}; expected one of {list(df.columns)!r}."
            )
        cluster_sums = infl.groupby(df[cluster_col], sort=False).sum()
        var = float((cluster_sums**2).sum()) / (n * (n - 1))
    else:
        var = float((infl**2).sum()) / (n * (n - 1))
    se = float(np.sqrt(var))
    return point, se, point - _Z * se, point + _Z * se


def _bootstrap_ci(
    df: pd.DataFrame,
    point_fn: Callable[[pd.DataFrame], float],
    *,
    cluster_col: str | None,
    n_boot: int,
    random_state: int,
) -> tuple[float, float, float]:
    """Bootstrap ``(se, lo, hi)``; cluster bootstrap when ``cluster_col`` is given."""
    rng = np.random.default_rng(random_state)
    boot: list[float] = []
    if cluster_col is not None:
        clusters = df[cluster_col].unique()
        for _ in range(n_boot):
            picked = rng.choice(clusters, size=len(clusters), replace=True)
            boot_df = pd.concat([df[df[cluster_col] == c] for c in picked], ignore_index=True)
            try:
                boot.append(float(point_fn(boot_df)))
            except Exception:  # noqa: BLE001 - a dropped draw is not fatal
                continue
    else:
        idx = np.arange(len(df))
        for _ in range(n_boot):
            sample = df.iloc[rng.choice(idx, size=len(idx), replace=True)]
            try:
                boot.append(float(point_fn(sample)))
            except Exception:  # noqa: BLE001
                continue
    if not boot:
        raise CausalError("all bootstrap draws failed; cannot compute a bootstrap interval.")
    boot_arr = np.asarray(boot)
    se = float(boot_arr.std(ddof=1))
    lo, hi = float(np.percentile(boot_arr, 2.5)), float(np.percentile(boot_arr, 97.5))
    return se, lo, hi


@public_op(name="ef.causal.estimate_effect")
def estimate_effect(
    df: pd.DataFrame,
    *,
    outcome: str,
    treatment: str,
    covariates: list[str] | None = None,
    method: str = "aipw",
    cluster_col: str | None = None,
    n_boot: int = 0,
    random_state: int = 0,
) -> pd.DataFrame:
    """Estimate an average treatment effect with honest uncertainty.

    ``method`` is one of ``"aipw"`` (default; doubly robust), ``"ipw"``,
    ``"matching"``, or ``"regression_adjust"``. ``covariates`` is the adjustment set;
    non-numeric covariates are one-hot encoded for the models. ``treatment`` must be a
    binary 0/1 column; ``outcome`` any continuous column.

    Inference honours nested/clustered data:

    * ``cluster_col`` computes a cluster-robust (sandwich) SE over whole groups, so
      repeated measures per subject get honest SEs without a second mechanism
      (``regression_adjust`` reuses the ``cov_type="cluster"`` path from
      ``ef.stats.fit_model``).
    * ``n_boot`` > 0 runs a bootstrap (cluster bootstrap over ``cluster_col`` when
      given, row bootstrap otherwise) and returns the 95% percentile CI. With
      ``n_boot=0`` a closed-form SE is used (sandwich for ``ipw``/``aipw``, fitted-model
      SE for ``regression_adjust``, paired-difference SE for ``matching``).

    Returns a one-row, tidy ``pd.DataFrame`` with columns ``estimate``, ``std_err``,
    ``ci_low``, ``ci_high``, ``p_value``, ``method``, ``n_treated``, ``n_control``,
    ``effective_n``. Never mutates ``df``.
    """
    if outcome not in df.columns:
        raise CausalError(f"unknown outcome {outcome!r}; expected one of {list(df.columns)!r}.")
    if method not in _EFFECT_METHODS:
        raise UnknownMethodError(
            f"unknown method {method!r}; expected one of {list(_EFFECT_METHODS)!r}."
        )
    for col in covariates or []:
        if col not in df.columns:
            raise CausalError(f"unknown covariate {col!r}; expected one of {list(df.columns)!r}.")
    t = _validate_binary_treatment(df, treatment)
    n_treated = int((t == 1).sum())
    n_control = int(len(df) - n_treated)

    if n_boot > 0:
        point_fn = _point_model(
            df, outcome=outcome, treatment=treatment, covariates=covariates, method=method
        )
        point = float(point_fn(df))
        se, lo, hi = _bootstrap_ci(
            df, point_fn, cluster_col=cluster_col, n_boot=n_boot, random_state=random_state
        )
    else:
        point, se, lo, hi = _closed_form(
            df,
            outcome=outcome,
            treatment=treatment,
            covariates=covariates,
            method=method,
            cluster_col=cluster_col,
        )

    p_value = float(
        2.0 * (1.0 - scipy_stats.norm.cdf(abs(point / se))) if se and se > 0 else float("nan")
    )
    effective_n = float(min(n_treated, n_control))

    return pd.DataFrame(
        [
            {
                "estimate": float(point),
                "std_err": float(se),
                "ci_low": float(lo),
                "ci_high": float(hi),
                "p_value": p_value,
                "method": method,
                "n_treated": n_treated,
                "n_control": n_control,
                "effective_n": effective_n,
            }
        ]
    )
