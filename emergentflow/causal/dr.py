"""
emergentflow.causal.dr
~~~~~~~~~~~~~~~~~~~~~~~~
Doubly-robust and IPW effect estimation with honest uncertainty (issue #164 Gap 1).

``ef.causal.estimate_effect`` computes an average treatment effect on an observational
sample with acknowledged selection bias, via one of four methods:

* ``"ipw"``               -- inverse-probability weighting (Hajek / self-normalised estimator).
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

import warnings
from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import stats as scipy_stats
from sklearn.linear_model import LogisticRegression

from emergentflow.api import public_op
from emergentflow.causal.errors import CausalError, InvalidTreatmentError
from emergentflow.causal.matching import _DEFAULT_CALIPER, match_nearest
from emergentflow.causal.propensity import _propensity_design, _validate_binary_treatment
from emergentflow.causal.registry import get_estimator_spec
from emergentflow.stats.catalog import _cov_kwargs, _patsy_term

__all__ = ["estimate_effect"]

_Z = 1.959963984540054  # z_{0.975}
_P_CLIP = 1e-6


def _treat_param_name(results: Any, treatment: str) -> str:
    """Return the exact coefficient name for *treatment* in a statsmodels result.

    patsy keeps the bare column name for a plain identifier and wraps a non-identifier
    column as ``Q('...')``; a categorical treatment would be mangled, but this family
    requires binary 0/1 so one of those two forms is expected.
    """
    for candidate in (treatment, _patsy_term(treatment)):
        if candidate in results.params.index:
            return candidate
    for name in results.params.index:
        if name.startswith(f"{treatment}[") or name.startswith(f"{_patsy_term(treatment)}["):
            return name
    raise CausalError(
        f"could not locate the treatment coefficient for {treatment!r} in "
        f"{list(results.params.index)!r}."
    )


def _regression_formula(outcome: str, treatment: str, covariates: list[str] | None) -> str:
    rhs = [_patsy_term(treatment)] + [_patsy_term(c) for c in (covariates or [])]
    return f"{_patsy_term(outcome)} ~ " + " + ".join(rhs)


def _fit_propensity_probs(design: pd.DataFrame, t: np.ndarray) -> np.ndarray:
    """Logistic propensity scores, clipped away from 0/1 so the IPW weights stay finite."""
    est = LogisticRegression(max_iter=1000).fit(design, t)
    return est.predict_proba(design)[:, 1].clip(_P_CLIP, 1 - _P_CLIP)


def _hajek(y: np.ndarray, tt: np.ndarray, p: np.ndarray) -> tuple[float, np.ndarray]:
    """Hajek (self-normalised) IPW ATE and its per-unit influence function.

    ``mu1 = sum(w1 y) / sum(w1)`` and ``mu0 = sum(w0 y) / sum(w0)`` with ``w1 = t/p`` and
    ``w0 = (1-t)/(1-p)``. Unlike the Horvitz-Thompson form ``mean((t/p - (1-t)/(1-p)) y)``
    the weights are normalised within each arm, so the estimate is invariant to shifting
    ``y`` by a constant. The influence function of each ratio estimator is
    ``w (y - mu) / mean(w)``.
    """
    w1 = tt / p
    w0 = (1.0 - tt) / (1.0 - p)
    mu1 = float((w1 * y).sum() / w1.sum())
    mu0 = float((w0 * y).sum() / w0.sum())
    infl = w1 * (y - mu1) / w1.mean() - w0 * (y - mu0) / w0.mean()
    return mu1 - mu0, infl


def _aipw(
    y: np.ndarray, tt: np.ndarray, p: np.ndarray, design: pd.DataFrame
) -> tuple[float, np.ndarray]:
    """Doubly-robust (AIPW) ATE and its per-unit influence function.

    Fits per-arm linear outcome models on *design* and returns ``(mean(DR_i), DR_i - mean)``.
    """
    X = sm.add_constant(design)
    mu1 = sm.OLS(y[tt == 1], X.iloc[tt == 1]).fit()
    mu0 = sm.OLS(y[tt == 0], X.iloc[tt == 0]).fit()
    m1 = np.asarray(mu1.predict(X), dtype=float)
    m0 = np.asarray(mu0.predict(X), dtype=float)
    dr = (tt / p * (y - m1) + m1) - ((1.0 - tt) / (1.0 - p) * (y - m0) + m0)
    point = float(dr.mean())
    return point, dr - point


def _point_model(
    *,
    outcome: str,
    treatment: str,
    covariates: list[str] | None,
    method: str,
    caliper: float | None,
    random_state: int,
) -> Callable[[pd.DataFrame], float]:
    """Return a callable computing just the point estimate on any compatible frame."""
    covs = covariates or []

    if method == "matching":

        def _matching_point(d2: pd.DataFrame) -> float:
            pairs = match_nearest(
                d2,
                treatment=treatment,
                covariates=covs,
                outcome=outcome,
                caliper=caliper,
                random_state=random_state,
            )
            return float(pairs["difference"].mean())

        return _matching_point

    if method == "regression_adjust":
        formula = _regression_formula(outcome, treatment, covariates)

        def _regress_point(d2: pd.DataFrame) -> float:
            r = smf.ols(formula, data=d2).fit()
            return float(r.params[_treat_param_name(r, treatment)])

        return _regress_point

    def _score_point(d2: pd.DataFrame) -> float:
        tt2 = _validate_binary_treatment(d2, treatment).to_numpy()
        design2 = _propensity_design(d2, covs)
        y2 = d2[outcome].to_numpy(dtype=float)
        p2 = _fit_propensity_probs(design2, tt2)
        if method == "aipw":
            return _aipw(y2, tt2, p2, design2)[0]
        return _hajek(y2, tt2, p2)[0]

    return _score_point


def _closed_form(
    df: pd.DataFrame,
    *,
    outcome: str,
    treatment: str,
    covariates: list[str] | None,
    method: str,
    cluster_col: str | None,
    p: np.ndarray | None,
    pairs: pd.DataFrame | None,
) -> tuple[float, float, float, float]:
    """Analytical ``(point, se, ci_low, ci_high)`` with no resampling.

    *p* (propensity scores) is pre-fitted by the caller for ``ipw``/``aipw``; *pairs* is the
    pre-computed match frame for ``matching``.
    """
    t = _validate_binary_treatment(df, treatment)
    n = len(df)

    if method == "regression_adjust":
        formula = _regression_formula(outcome, treatment, covariates)
        spec: dict[str, object] = {"cov_type": "nonrobust"}
        if cluster_col is not None:
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
        assert pairs is not None  # supplied by estimate_effect
        diffs = pairs["difference"].to_numpy(dtype=float)
        point = float(diffs.mean())
        se = float(diffs.std(ddof=1) / np.sqrt(len(diffs))) if len(diffs) > 1 else float("nan")
        return point, se, point - _Z * se, point + _Z * se

    # ipw / aipw: influence-function sandwich.
    assert p is not None  # supplied by estimate_effect
    y = df[outcome].to_numpy(dtype=float)
    tt = t.to_numpy()
    if method == "ipw":
        point, infl_arr = _hajek(y, tt, p)
    else:
        point, infl_arr = _aipw(y, tt, p, _propensity_design(df, covariates or []))
    infl = pd.Series(infl_arr, index=df.index, dtype=float)

    if cluster_col is not None:
        cluster_sums = infl.groupby(df[cluster_col].to_numpy(), sort=False).sum()
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
    """Bootstrap ``(se, lo, hi)``; cluster bootstrap when ``cluster_col`` is given.

    Draws that fail (e.g. a resample with no matchable pair) are dropped and counted; if any
    were dropped a ``RuntimeWarning`` reports how many, and if all failed a ``CausalError``
    is raised.
    """
    rng = np.random.default_rng(random_state)
    boot: list[float] = []
    n_failed = 0
    if cluster_col is not None:
        clusters = df[cluster_col].unique()
        for _ in range(n_boot):
            picked = rng.choice(clusters, size=len(clusters), replace=True)
            boot_df = pd.concat([df[df[cluster_col] == c] for c in picked], ignore_index=True)
            try:
                boot.append(float(point_fn(boot_df)))
            except Exception:  # noqa: BLE001 - a dropped draw is not fatal
                n_failed += 1
    else:
        idx = np.arange(len(df))
        for _ in range(n_boot):
            # reset_index: a resample carries duplicate labels, which must not fan out in
            # any label-based lookup downstream.
            sample = df.iloc[rng.choice(idx, size=len(idx), replace=True)].reset_index(drop=True)
            try:
                boot.append(float(point_fn(sample)))
            except Exception:  # noqa: BLE001
                n_failed += 1
    if not boot:
        raise CausalError("all bootstrap draws failed; cannot compute a bootstrap interval.")
    if n_failed:
        warnings.warn(
            f"{n_failed} of {n_boot} bootstrap draws failed and were dropped; the interval is "
            f"based on {len(boot)} draws.",
            RuntimeWarning,
            stacklevel=3,
        )
    boot_arr = np.asarray(boot)
    se = float(boot_arr.std(ddof=1)) if len(boot_arr) > 1 else float("nan")
    lo, hi = float(np.percentile(boot_arr, 2.5)), float(np.percentile(boot_arr, 97.5))
    return se, lo, hi


def _kish_effective_n(weights: np.ndarray) -> float:
    """Kish effective sample size ``(sum w)^2 / sum(w^2)``."""
    return float(weights.sum() ** 2 / (weights**2).sum())


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
    caliper: float | None = _DEFAULT_CALIPER,
) -> pd.DataFrame:
    """Estimate an average treatment effect with honest uncertainty.

    ``method`` is one of the registered ``estimate_effect`` estimators (see
    ``ef.causal.keys_for_archetype("estimate_effect")``): ``"aipw"`` (default; doubly
    robust), ``"ipw"`` (Hajek / self-normalised inverse-probability weighting -- invariant
    to shifting the outcome by a constant), ``"matching"`` (1:1 nearest-neighbour
    propensity matching within ``caliper`` SDs of the logit score; ``caliper=None`` disables
    the caliper; ``random_state`` breaks exact ties), or ``"regression_adjust"``.
    ``covariates`` is the adjustment set; non-numeric covariates are one-hot encoded for the
    models. ``treatment`` must be a binary 0/1 column with both arms present; ``outcome``
    any continuous column. Missing values in the outcome, treatment or covariates raise.

    Inference honours nested/clustered data:

    * ``cluster_col`` computes a cluster-robust (sandwich) SE over whole groups, so
      repeated measures per subject get honest SEs without a second mechanism
      (``regression_adjust`` reuses the ``cov_type="cluster"`` path from
      ``ef.stats.fit_model``). The closed-form ``matching`` SE has no cluster form: pass
      ``n_boot > 0`` to get a cluster bootstrap instead.
    * ``n_boot`` > 0 runs a bootstrap (cluster bootstrap over ``cluster_col`` when
      given, row bootstrap otherwise) and returns the 95% percentile CI. With
      ``n_boot=0`` a closed-form SE is used (sandwich for ``ipw``/``aipw``, fitted-model
      SE for ``regression_adjust``, paired-difference SE for ``matching``).

    Returns a one-row, tidy ``pd.DataFrame`` with columns ``estimate``, ``std_err``,
    ``ci_low``, ``ci_high``, ``p_value``, ``method``, ``n_treated``, ``n_control`` (sample
    counts), and ``effective_n``: the Kish effective sample size of the IPW weights for
    ``ipw``/``aipw``, the number of matched pairs for ``matching``, and the sample size for
    ``regression_adjust``. Never mutates ``df``.
    """
    get_estimator_spec(method, "estimate_effect")  # raises UnknownMethodError
    if outcome not in df.columns:
        raise CausalError(f"unknown outcome {outcome!r}; expected one of {list(df.columns)!r}.")
    for col in covariates or []:
        if col not in df.columns:
            raise CausalError(f"unknown covariate {col!r}; expected one of {list(df.columns)!r}.")
    if cluster_col is not None and cluster_col not in df.columns:
        raise CausalError(
            f"unknown cluster_col {cluster_col!r}; expected one of {list(df.columns)!r}."
        )
    if cluster_col is not None and df[cluster_col].isna().any():
        raise CausalError(
            f"cluster_col {cluster_col!r} contains missing values; a row without a cluster would "
            "silently drop out of the cluster-robust variance. Drop or fill them first."
        )
    if cluster_col is not None and method == "matching" and n_boot == 0:
        raise CausalError(
            "cluster_col has no closed-form SE for method='matching'; pass n_boot > 0 to run a "
            "cluster bootstrap over cluster_col instead."
        )
    t = _validate_binary_treatment(df, treatment)
    n_treated = int((t == 1).sum())
    n_control = int(len(df) - n_treated)
    if n_treated == 0 or n_control == 0:
        raise InvalidTreatmentError(
            f"treatment {treatment!r} must contain both treated (1) and control (0) units; "
            f"found n_treated={n_treated}, n_control={n_control}."
        )
    if df[outcome].isna().any():
        raise CausalError(
            f"outcome {outcome!r} contains missing values; drop or impute them before "
            "estimating an effect."
        )
    na_covs = [c for c in covariates or [] if df[c].isna().any()]
    if na_covs:
        raise CausalError(
            f"covariates {na_covs!r} contain missing values; drop or impute them before "
            "estimating an effect."
        )

    p: np.ndarray | None = None
    pairs: pd.DataFrame | None = None
    if method in ("ipw", "aipw"):
        design = _propensity_design(df, covariates or [])
        p = _fit_propensity_probs(design, t.to_numpy())
        tt = t.to_numpy()
        effective_n = _kish_effective_n(tt / p + (1.0 - tt) / (1.0 - p))
    elif method == "matching":
        pairs = match_nearest(
            df,
            treatment=treatment,
            covariates=covariates or [],
            outcome=outcome,
            caliper=caliper,
            random_state=random_state,
        )
        effective_n = float(len(pairs))
    else:
        effective_n = float(len(df))

    if n_boot > 0:
        point_fn = _point_model(
            outcome=outcome,
            treatment=treatment,
            covariates=covariates,
            method=method,
            caliper=caliper,
            random_state=random_state,
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
            p=p,
            pairs=pairs,
        )

    p_value = (
        float(2.0 * scipy_stats.norm.sf(abs(point / se)))
        if np.isfinite(se) and se > 0
        else float("nan")
    )

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
