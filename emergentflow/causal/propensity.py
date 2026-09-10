"""
emergentflow.causal.propensity
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Propensity-score fitting + balancing diagnostics (issue #164 Gap 1).

``ef.causal.fit_propensity`` fits a binary-treatment model on covariates, returns the
per-row propensity scores and IPW (ATE or ATT) weights, and -- crucially -- reports the
balance table and overlap/support diagnostics that make propensity methods defensible.
The balance and overlap frames are the *whole* value of the method, so they are always
computed and returned, never optional (the issue's design note #2).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from emergentflow.api import public_op
from emergentflow.causal.errors import CausalError, InvalidTreatmentError

__all__ = ["PropensityResult", "fit_propensity", "propensity_scores"]

_PROPENSITY_ESTIMATORS = {"LogisticRegression": LogisticRegression}


@dataclass
class PropensityResult:
    """Structured, inspectable result of a propensity-model fit.

    Attributes
    ----------
    scores: per-row P(treat=1 | covariates), clipped to the ``trim`` bounds
        (``pd.Series``, aligned to the input frame's index).
    weights: per-row IPW (``"ATE"``) or ATT weights, trimmed per ``trim``
        (``pd.Series``, aligned to the input frame's index).
    balance: tidy frame, one row per covariate: standardized mean difference
        before/after weighting plus variance ratio before/after.
    overlap: common-support summary, one row per arm: min/max/mean score and the
        percentage of rows outside the ``trim`` support.
    effective_n: Kish effective sample size per arm after weighting.
    """

    scores: pd.Series
    weights: pd.Series
    balance: pd.DataFrame
    overlap: pd.DataFrame
    effective_n: pd.DataFrame


def _validate_binary_treatment(df: pd.DataFrame, treatment: str) -> pd.Series:
    """Validate *treatment* names a binary 0/1 column and return it as 0/1 ints."""
    if treatment not in df.columns:
        raise CausalError(f"unknown treatment {treatment!r}; expected one of {list(df.columns)!r}.")
    t = df[treatment]
    vals = pd.unique(t.dropna())
    if not set(vals).issubset({0, 1}):
        raise InvalidTreatmentError(
            f"treatment {treatment!r} must be binary (0/1 or True/False); "
            f"found values {sorted(vals)!r}."
        )
    return t.astype(int)


def _propensity_design(df: pd.DataFrame, covariates: list[str]) -> pd.DataFrame:
    """Build a numeric design matrix for the propensity model.

    Numeric covariates pass through unchanged; non-numeric covariates are one-hot
    encoded with ``drop_first=True`` so the matrix is full rank for logistic
    regression. Column names: numeric keep their name; encoded levels are named
    ``<covariate>_<level>``.
    """
    if not covariates:
        raise CausalError("covariates must be a non-empty list of column names.")
    unknown = [c for c in covariates if c not in df.columns]
    if unknown:
        raise CausalError(f"unknown covariates {unknown!r}; expected one of {list(df.columns)!r}.")
    pieces: list[pd.DataFrame] = []
    for col in covariates:
        s = df[col]
        if pd.api.types.is_numeric_dtype(s):
            pieces.append(df[[col]])
        else:
            dummies = pd.get_dummies(
                s.astype(str), prefix=col, drop_first=True, dummy_na=False
            ).astype(float)
            dummies.columns = [c for c in dummies.columns]
            pieces.append(dummies)
    design = pd.concat(pieces, axis=1)
    # Get_dummies on an all-null categorical yields an empty frame; collapse to a
    # single informative column so the model matrix never loses rank silently.
    if design.shape[1] == 0:
        raise CausalError(
            f"covariates produced an empty numeric design matrix; check {covariates!r}."
        )
    return design


def _weighted_net_stats(
    scores: pd.Series, treatment: pd.Series, effect: str
) -> tuple[pd.Series, pd.Series]:
    """Return ``(scores_clipped, weights)`` per the requested *effect* scheme.

    ``"ATE"``: IPW weights ``1/p`` for treated, ``1/(1-p)`` for control.
    ``"ATT"``: treated weight 1, control weight ``p/(1-p)``.
    Scores are clipped to the (already-validated) trim bounds upstream.
    """
    p = scores
    if effect == "ATE":
        weights = np.where(treatment == 1, 1.0 / p, 1.0 / (1.0 - p))
    elif effect == "ATT":
        weights = np.where(treatment == 1, 1.0, p / (1.0 - p))
    else:
        raise CausalError(f"unknown effect {effect!r}; expected 'ATE' or 'ATT'.")
    return scores, pd.Series(weights, index=treatment.index)


def _balance_frame(
    design: pd.DataFrame,
    treatment: pd.Series,
    weights: pd.Series,
) -> pd.DataFrame:
    """Per-covariate balance: standardized mean difference + variance ratio."""
    rows: list[dict[str, Any]] = []
    treated = treatment == 1
    control = ~treated
    for col in design.columns:
        x = design[col]
        xt = x[treated]
        xc = x[control]
        mt, mc = float(xt.mean()), float(xc.mean())
        vt, vc = float(xt.var(ddof=1)), float(xc.var(ddof=1))
        pooled = np.sqrt((vt + vc) / 2.0)
        smd_before = (mt - mc) / pooled if pooled > 0 else float("nan")
        vr_before = vt / vc if vc > 0 else float("nan")

        wt = weights[treated]
        wc = weights[control]
        swmt = float(np.average(xt, weights=wt))
        swmc = float(np.average(xc, weights=wc))
        swt = float(
            np.average((xt - swmt) ** 2, weights=wt) * (len(wt) / (len(wt) - 1))
            if len(wt) > 1
            else float("nan")
        )
        swc = float(
            np.average((xc - swmc) ** 2, weights=wc) * (len(wc) / (len(wc) - 1))
            if len(wc) > 1
            else float("nan")
        )
        spooled = np.sqrt((swt + swc) / 2.0) if np.isfinite(swt) and np.isfinite(swc) else np.nan
        smd_after = (swmt - swmc) / spooled if spooled and spooled > 0 else float("nan")
        vr_after = swt / swc if (np.isfinite(swc) and swc > 0) else float("nan")
        rows.append(
            {
                "covariate": col,
                "smd_before": smd_before,
                "smd_after": smd_after,
                "var_ratio_before": vr_before,
                "var_ratio_after": vr_after,
            }
        )
    return pd.DataFrame(rows)


def _overlap_frame(
    scores: pd.Series, treatment: pd.Series, trim: tuple[float, float]
) -> pd.DataFrame:
    """Common-support summary: one row per arm with score min/max/mean + trim pct."""
    t = treatment == 1
    rows = []
    for label, mask in (("treated", t), ("control", ~t)):
        s = scores[mask]
        outside = float(((s < min(trim)) | (s > max(trim))).mean()) if len(s) else float("nan")
        rows.append(
            {
                "arm": label,
                "n": int(len(s)),
                "score_min": float(s.min()) if len(s) else float("nan"),
                "score_max": float(s.max()) if len(s) else float("nan"),
                "score_mean": float(s.mean()) if len(s) else float("nan"),
                "pct_outside_support": outside,
            }
        )
    return pd.DataFrame(rows)


def _kish_effective_n(weights: pd.Series, treatment: pd.Series) -> pd.DataFrame:
    """Kish effective sample size per arm after weighting: (sum w)^2 / sum(w^2)."""
    rows = []
    for label, mask in (("treated", treatment == 1), ("control", treatment != 1)):
        w = weights[mask]
        eff = float(w.sum() ** 2 / (w**2).sum()) if len(w) and w.sum() > 0 else float("nan")
        rows.append({"arm": label, "n": int(len(w)), "effective_n": eff})
    return pd.DataFrame(rows)


def propensity_scores(
    df: pd.DataFrame,
    *,
    treatment: str,
    covariates: list[str],
    estimator: str = "LogisticRegression",
    params: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Fit a propensity model and return the numeric design matrix + fitted scores.

    Returns a frame containing the design columns (already one-hot encoded as needed)
    plus a trailing ``_propensity`` column holding ``P(treat=1 | covariates)``.
    """
    if estimator not in _PROPENSITY_ESTIMATORS:
        raise CausalError(
            f"unknown propensity estimator {estimator!r}; expected one of "
            f"{sorted(_PROPENSITY_ESTIMATORS)!r}."
        )
    _validate_binary_treatment(df, treatment)
    design = _propensity_design(df, covariates)
    t = df[treatment].astype(int)
    est_cls = _PROPENSITY_ESTIMATORS[estimator]
    est = est_cls(max_iter=1000, **(params or {}))
    est.fit(design, t)
    probs = est.predict_proba(design)[:, 1]
    result = design.copy()
    result["_propensity"] = probs
    return result


@public_op(name="ef.causal.fit_propensity")
def fit_propensity(
    df: pd.DataFrame,
    *,
    treatment: str,
    covariates: list[str],
    estimator: str = "LogisticRegression",
    params: dict[str, Any] | None = None,
    trim: tuple[float, float] | None = (0.01, 0.99),
    effect: str = "ATE",
) -> PropensityResult:
    """Fit a propensity model; return scores, IPW/ATT weights, balance, overlap.

    ``treatment`` must be a binary 0/1 (or True/False) column. ``covariates`` are the
    adjustment set; non-numeric covariates are one-hot encoded for the model and their
    indicators appear in the balance table. ``estimator`` is ``"LogisticRegression"``
    (the only curated model in this family's MVP); ``params`` are constructor kwargs.

    ``effect="ATE"`` returns IPW weights ``1/P(treat)`` under the Horvitz-Thompson /
    Hajek weighting; ``"ATT"`` returns ATT weights (treated weight 1, control
    ``p/(1-p)``). ``trim`` winsorizes the propensity scores to the given support before
    computing weights (``None`` disables trimming).

    Returns a :class:`PropensityResult` whose ``balance`` frame is the essential
    diagnostic: per-covariate standardized mean difference before/after weighting plus
    variance ratio, so a user can see whether weighting removed the imbalance before
    trusting any effect estimate. Never mutates ``df``.
    """
    if trim is not None:
        lo, hi = trim
        if not (0.0 <= lo < hi <= 1.0):
            raise CausalError(f"trim must satisfy 0 <= lo < hi <= 1; got {trim!r}.")
    if effect not in ("ATE", "ATT"):
        raise CausalError(f"unknown effect {effect!r}; expected 'ATE' or 'ATT'.")

    t = _validate_binary_treatment(df, treatment)
    if t.nunique() < 2:
        raise InvalidTreatmentError(
            f"treatment {treatment!r} must contain both 0 and 1 to fit a propensity model."
        )
    if estimator not in _PROPENSITY_ESTIMATORS:
        raise CausalError(
            f"unknown propensity estimator {estimator!r}; expected one of "
            f"{sorted(_PROPENSITY_ESTIMATORS)!r}."
        )

    design = _propensity_design(df, covariates)
    est_cls = _PROPENSITY_ESTIMATORS[estimator]
    est = est_cls(max_iter=1000, **(params or {}))
    est.fit(design, t)
    scores_raw = pd.Series(est.predict_proba(design)[:, 1], index=df.index)

    if trim is not None:
        lo, hi = trim
        scores = scores_raw.clip(lo, hi)
    else:
        scores = scores_raw

    _scores_clipped, weights = _weighted_net_stats(scores, t, effect)
    balance = _balance_frame(design, t, weights)
    overlap = _overlap_frame(scores_raw, t, trim if trim is not None else (0.0, 1.0))
    eff_n = _kish_effective_n(weights, t)

    return PropensityResult(
        scores=cast(pd.Series, scores_raw),
        weights=weights,
        balance=balance,
        overlap=overlap,
        effective_n=eff_n,
    )
