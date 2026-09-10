"""
emergentflow.causal.sensitivity
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Unmeasured-confounding sensitivity analysis (issue #164 Gap 1).

``ef.causal.sensitivity`` answers the question a causal estimate leaves open: *how strong
would unmeasured confounding have to be to explain the observed effect away?* The MVP
implements the E-value (VanderWeele & Ding, 2017) plus classic Rosenbaum bounds on a
matched binary-outcome sample. Both return tidy, inspectable frames.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from emergentflow.api import public_op
from emergentflow.causal.errors import CausalError, UnknownMethodError

__all__ = ["sensitivity", "e_value", "rosenbaum_gamma"]

_SENSITIVITY_METHODS = ("e_value", "rosenbaum")
_EVALUE_SCALES = ("risk_ratio", "difference")
#: VanderWeele & Ding (2017), continuous outcomes: a standardized mean difference ``d``
#: maps to an approximate risk ratio ``exp(0.91 * d)``.
_SMD_TO_LOG_RR = 0.91


def _evalue_one(risk_ratio: float) -> float:
    """E-value for a single risk ratio (VanderWeele & Ding 2017).

    ``E = RR* + sqrt(RR* (RR* - 1))`` with ``RR* = RR`` for ``RR >= 1`` and ``RR* = 1 / RR``
    for a protective effect (``RR < 1``): the E-value is symmetric on the log scale, so a 75%
    risk reduction needs exactly as strong a confounder as a 4x risk increase. ``RR == 1``
    maps to ``1.0`` (no confounding needed); a non-finite or non-positive input is ``nan``.
    Mirrors the ``EValue`` package's scalar computation.
    """
    if not np.isfinite(risk_ratio) or risk_ratio <= 0:
        return float("nan")
    rr = float(risk_ratio)
    if rr < 1.0:
        rr = 1.0 / rr
    return float(rr + np.sqrt(rr * (rr - 1.0)))


def _validate_scale(scale: str, sd: float | None) -> None:
    if scale not in _EVALUE_SCALES:
        raise CausalError(f"unknown scale {scale!r}; expected one of {list(_EVALUE_SCALES)!r}.")
    if scale == "difference":
        if sd is None:
            raise CausalError(
                "scale='difference' requires sd (the outcome's standard deviation) to convert a "
                "mean difference into an approximate risk ratio (VanderWeele & Ding 2017, "
                "RR ~ exp(0.91 * d / sd)). The frames from ef.causal.estimate_effect and "
                "ef.causal.did are on the difference scale."
            )
        if not np.isfinite(sd) or sd <= 0:
            raise CausalError(f"sd must be a finite number > 0; got {sd!r}.")


def _to_risk_ratio(value: float, *, scale: str, sd: float | None) -> float:
    """Map *value* onto the risk-ratio scale (identity for ``scale="risk_ratio"``)."""
    if scale == "risk_ratio":
        return float(value)
    assert sd is not None  # validated by _validate_scale
    return float(np.exp(_SMD_TO_LOG_RR * float(value) / float(sd)))


@public_op(name="ef.causal.e_value")
def e_value(
    effect: pd.DataFrame | None,
    *,
    risk_ratio: float | None = None,
    scale: str = "risk_ratio",
    sd: float | None = None,
) -> pd.DataFrame:
    """E-value for an already-estimated effect: strength a confounder needs to explain it.

    ``effect`` is a one-row tidy frame carrying ``estimate`` and, when present,
    ``ci_low``/``ci_high``. ``scale`` says what that estimate is: ``"risk_ratio"`` (default;
    an RR/OR/HR, which must be > 0) or ``"difference"`` (a mean difference -- the frames from
    :func:`ef.causal.estimate_effect` and :func:`ef.causal.did`), in which case ``sd`` (the
    outcome's standard deviation) is required and the difference is converted to an
    approximate RR via ``exp(0.91 * d / sd)`` (VanderWeele & Ding 2017). An E-value is
    scale-free by construction; feeding a raw mean difference in as a ratio is not.
    Alternatively pass the effect directly via ``risk_ratio`` (interpreted per ``scale``).

    Protective effects (RR < 1) are inverted (``1 / RR``) before the E-value formula, so a
    75% risk reduction reports the same E-value as a 4x risk increase.

    Returns a one-row DataFrame with ``point_evalue`` (the E-value for the point estimate)
    and ``bound_evalue`` (the E-value for the confidence bound nearest the null -- the
    conservative "this effect could be explained by confounding of magnitude X" number;
    ``1.0`` when the interval covers the null, ``nan`` when no interval is given). Never
    mutates ``effect``.
    """
    _validate_scale(scale, sd)
    if risk_ratio is not None:
        if scale == "risk_ratio" and risk_ratio <= 0:
            raise CausalError(
                f"risk_ratio must be > 0 on the risk-ratio scale; got {risk_ratio!r}."
            )
        point_rr = _to_risk_ratio(float(risk_ratio), scale=scale, sd=sd)
        return pd.DataFrame([{"point_evalue": _evalue_one(point_rr), "bound_evalue": float("nan")}])

    if not isinstance(effect, pd.DataFrame) or "estimate" not in effect.columns:
        raise CausalError(
            "e_value requires an effect frame with an 'estimate' column "
            "(e.g. the output of ef.causal.estimate_effect)."
        )
    if effect.empty:
        raise CausalError("e_value requires a non-empty effect frame.")
    row = effect.iloc[0]
    point = float(row["estimate"])
    if scale == "risk_ratio" and not point > 0:
        raise CausalError(
            f"estimate must be > 0 on the risk-ratio scale; got {point!r}. For a mean-"
            "difference estimate (ef.causal.estimate_effect / ef.causal.did) pass "
            "scale='difference' together with sd."
        )
    point_rr = _to_risk_ratio(point, scale=scale, sd=sd)

    if {"ci_low", "ci_high"} <= set(effect.columns):
        lo_rr = _to_risk_ratio(float(row["ci_low"]), scale=scale, sd=sd)
        hi_rr = _to_risk_ratio(float(row["ci_high"]), scale=scale, sd=sd)
        if not (np.isfinite(lo_rr) and np.isfinite(hi_rr)):
            bound_ev = float("nan")
        elif point_rr >= 1.0:
            # Harmful direction: the lower bound is the one nearest the null.
            bound_ev = 1.0 if lo_rr <= 1.0 else _evalue_one(lo_rr)
        else:
            # Protective direction: the upper bound is the one nearest the null.
            bound_ev = 1.0 if hi_rr >= 1.0 else _evalue_one(hi_rr)
    else:
        bound_ev = float("nan")
    return pd.DataFrame([{"point_evalue": _evalue_one(point_rr), "bound_evalue": bound_ev}])


@public_op(name="ef.causal.rosenbaum_gamma")
def rosenbaum_gamma(
    matched: pd.DataFrame,
    *,
    treated_outcome_col: str,
    control_outcome_col: str,
    gamma: float = 2.0,
) -> pd.DataFrame:
    """Rosenbaum sensitivity bounds on matched-pair binary outcomes.

    ``matched`` is the pair frame from :func:`ef.causal.match_nearest` (or any tidy frame
    with one treated and one control binary outcome per row). Under unmeasured confounding
    of magnitude ``gamma`` (the maximum odds ratio by which two matched units may differ in
    their odds of treatment; ``gamma=1`` is no hidden bias), the one-sided sign-test p-value
    over the discordant pairs is bounded between two binomial tails (Rosenbaum 2002, §4):
    ``p_low`` (best case: hidden bias working *against* the observed direction) and
    ``p_high`` (worst case). The test is evaluated in the *observed* direction --
    ``direction`` reports ``"treated_higher"`` or ``"treated_lower"`` -- so a protective
    effect is judged exactly as strictly as a harmful one.

    Returns a one-row frame with ``gamma``, ``n_discordant``, ``direction``, ``p_low``,
    ``p_high`` and ``sensitivity`` = ``"robust"`` when even the worst case ``p_high < 0.05``,
    else ``"sensitive"``. This evaluates one ``gamma``; call it over a grid of ``gamma``
    values to find where ``p_high`` first crosses 0.05. Never mutates ``matched``.
    """
    if not np.isfinite(gamma) or gamma < 1.0:
        raise CausalError(f"gamma must be a finite number >= 1.0; got {gamma!r}.")
    for col in (treated_outcome_col, control_outcome_col):
        if col not in matched.columns:
            raise CausalError(f"unknown column {col!r}; expected one of {list(matched.columns)!r}.")
    t = matched[treated_outcome_col].to_numpy(dtype=float)
    c = matched[control_outcome_col].to_numpy(dtype=float)
    if not set(np.concatenate([t, c])).issubset({0.0, 1.0}):
        raise CausalError("Rosenbaum bounds require binary treated/control outcomes.")

    # Discordant pairs: those that can flip direction under unmeasured confounding.
    d = int(((t - c) != 0).sum())
    if d == 0:
        return pd.DataFrame(
            [
                {
                    "gamma": float(gamma),
                    "n_discordant": 0,
                    "direction": "none",
                    "p_low": 1.0,
                    "p_high": 1.0,
                    "sensitivity": "no discordant pairs",
                }
            ]
        )

    from scipy import stats as scipy_stats

    n_pos = int(((t - c) > 0).sum())
    n_neg = d - n_pos
    treated_higher = n_pos >= n_neg
    k = n_pos if treated_higher else n_neg
    # Best/worst case Binomial tail bounds (Rosenbaum 2002, eq. 4.3) in the observed direction.
    p_low = float(scipy_stats.binom.sf(k - 1, d, 1.0 / (gamma + 1.0)))
    p_high = float(scipy_stats.binom.sf(k - 1, d, gamma / (gamma + 1.0)))

    return pd.DataFrame(
        [
            {
                "gamma": float(gamma),
                "n_discordant": int(d),
                "direction": "treated_higher" if treated_higher else "treated_lower",
                "p_low": p_low,
                "p_high": p_high,
                "sensitivity": "robust" if p_high < 0.05 else "sensitive",
            }
        ]
    )


@public_op(name="ef.causal.sensitivity")
def sensitivity(
    effect: pd.DataFrame | None = None,
    *,
    method: str = "e_value",
    risk_ratio: float | None = None,
    scale: str = "risk_ratio",
    sd: float | None = None,
    matched: pd.DataFrame | None = None,
    treated_outcome_col: str | None = None,
    control_outcome_col: str | None = None,
    gamma: float = 2.0,
) -> pd.DataFrame:
    """Unmeasured-confounding sensitivity analysis for a causal estimate.

    Simplifies the family: ``method="e_value"`` (default) computes the E-value for an
    effect frame (or a ``risk_ratio``) on the given ``scale`` (``"risk_ratio"`` or
    ``"difference"`` + ``sd``; see :func:`e_value`), answering "how strong must unmeasured
    confounding be to explain the estimate away". ``method="rosenbaum"`` computes Rosenbaum
    bounds on ``(treated_outcome_col, control_outcome_col)`` pairs of ``matched`` at ``gamma``.

    Supply exactly the inputs the chosen method needs; the other kwargs are ignored.

    Returns a tidy one-row DataFrame (columns depend on the method). Never mutates inputs.
    """
    if method not in _SENSITIVITY_METHODS:
        raise UnknownMethodError(
            f"unknown sensitivity method {method!r}; expected one of "
            f"{list(_SENSITIVITY_METHODS)!r}."
        )
    if method == "e_value":
        return e_value(effect, risk_ratio=risk_ratio, scale=scale, sd=sd)
    if matched is None or treated_outcome_col is None or control_outcome_col is None:
        raise CausalError(
            "rosenbaum requires matched, treated_outcome_col, and control_outcome_col."
        )
    return rosenbaum_gamma(
        matched,
        treated_outcome_col=treated_outcome_col,
        control_outcome_col=control_outcome_col,
        gamma=gamma,
    )
