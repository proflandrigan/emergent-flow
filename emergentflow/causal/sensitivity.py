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


def _evalue_one(risk_ratio: float) -> float:
    """E-value for a single risk ratio (VanderWeele & Ding 2017).

    E-value = RR + sqrt(RR * (RR - 1)) for an RR on [1, inf); an effect at or below the
    null maps to ``1.0`` (an unmeasured confounder would need no association at all).
    Mirrors the ``EValue`` package's scalar computation.
    """
    if not np.isfinite(risk_ratio):
        return float("nan")
    rr = abs(float(risk_ratio))
    if rr <= 1.0:
        return 1.0
    return float(rr + np.sqrt(rr * (rr - 1.0)))


@public_op(name="ef.causal.e_value")
def e_value(
    effect: pd.DataFrame,
    *,
    risk_ratio: float | None = None,
) -> pd.DataFrame:
    """E-value for an already-estimated effect: strength a confounder needs to explain it.

    ``effect`` is the one-row tidy frame from :func:`ef.causal.estimate_effect` (or any
    frame carrying ``estimate`` and, when present, ``ci_low``/``ci_high`` on a risk-ratio
    scale). To interpret a **difference**-scale estimate as a risk ratio, pass it directly
    via ``risk_ratio`` instead (or supply a frame whose ``estimate`` is already an RR/OR).

    Returns a one-row DataFrame with ``point_evalue`` (the E-value for the point estimate)
    and ``bound_evalue`` (the E-value for the confidence bound nearest the null -- the
    conservative "this effect could be explained by confounding of magnitude X" number).
    Never mutates ``effect``.
    """
    if risk_ratio is not None:
        if risk_ratio <= 0:
            raise CausalError(f"risk_ratio must be > 0; got {risk_ratio!r}.")
        point = abs(float(risk_ratio))
        return pd.DataFrame([{"point_evalue": _evalue_one(point), "bound_evalue": float("nan")}])

    if not isinstance(effect, pd.DataFrame) or "estimate" not in effect.columns:
        raise CausalError(
            "e_value requires an effect frame with an 'estimate' column "
            "(e.g. the output of ef.causal.estimate_effect)."
        )
    row = effect.iloc[0]
    point = abs(float(row["estimate"]))
    if {"ci_low", "ci_high"} <= set(effect.columns):
        lo, hi = float(row["ci_low"]), float(row["ci_high"])
        # The bound nearest the null is the harder to explain; that is the one to quote.
        bound = (lo if lo >= 0 and lo < point else hi) if point >= 1.0 else (hi if hi >= 0 else lo)
        bound_ev = _evalue_one(float(bound))
    else:
        bound_ev = float("nan")
    return pd.DataFrame([{"point_evalue": _evalue_one(point), "bound_evalue": bound_ev}])


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
    with one treated and one control binary outcome per row). Returns a one-row frame with
    ``gamma``, ``n_discordant``, ``p_low`` / ``p_high`` (the worst/best-case p-values at
    this ``gamma``) and ``sensitivity`` = ``"p_high < 0.05"`` / ``"p_high >= 0.05"``.

    The classic result (Rosenbaum 2002, §4): under unmeasured confounding of magnitude
    ``gamma``, the significance of a McNemar-style sign test is bounded between two
    binomial tails over the discordant pairs. This tells a user at what ``gamma`` their
    matched result would no longer be ``p < 0.05``.
    """
    if gamma < 1.0:
        raise CausalError(f"gamma must be >= 1.0; got {gamma!r}.")
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
                    "gamma": gamma,
                    "n_discordant": 0,
                    "p_low": 1.0,
                    "p_high": 1.0,
                    "sensitivity": "no discordant pairs",
                }
            ]
        )

    from scipy import stats as scipy_stats

    n_pos = int(((t - c) > 0).sum())
    # Worst/best case Binomial tail bounds (Rosenbaum 2002, eq. 4.3).
    p_low = float(1 - scipy_stats.binom.cdf(n_pos - 1, d, 1 / (gamma + 1)))
    p_high = float(1 - scipy_stats.binom.cdf(n_pos - 1, d, gamma / (gamma + 1)))

    return pd.DataFrame(
        [
            {
                "gamma": float(gamma),
                "n_discordant": int(d),
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
    matched: pd.DataFrame | None = None,
    treated_outcome_col: str | None = None,
    control_outcome_col: str | None = None,
    gamma: float = 2.0,
) -> pd.DataFrame:
    """Unmeasured-confounding sensitivity analysis for a causal estimate.

    Simplifies the family: ``method="e_value"`` (default) computes the E-value for an
    effect frame (or a ``risk_ratio``), answering "how strong must unmeasured confounding
    be to explain the estimate away". ``method="rosenbaum"`` computes Rosenbaum bounds on
    ``(treated_outcome_col, control_outcome_col)`` pairs at ``gamma``.

    Supply exactly the inputs the chosen method needs; the other kwargs are ignored.

    Returns a tidy one-row DataFrame (columns depend on the method). Never mutates inputs.
    """
    if method not in _SENSITIVITY_METHODS:
        raise UnknownMethodError(
            f"unknown sensitivity method {method!r}; expected one of "
            f"{list(_SENSITIVITY_METHODS)!r}."
        )
    if method == "e_value":
        return e_value(effect, risk_ratio=risk_ratio)
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
