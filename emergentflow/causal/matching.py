"""
emergentflow.causal.matching
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Nearest-neighbour / caliper matching on a fitted propensity score (issue #164 Gap 1).

Implements the ``"matching"`` method of ``ef.causal.estimate_effect``: each treated unit
is matched to the control with the closest propensity score, optionally within a caliper.
The ATT is then the mean outcome difference over the matched pairs. Pure with respect to
the SDK contract (no I/O); deterministic given ``random_state``.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from emergentflow.causal.errors import CausalError
from emergentflow.causal.propensity import _propensity_design, _validate_binary_treatment

__all__ = ["match_nearest"]

_DEFAULT_CALIPER = 0.2


def match_nearest(
    df: pd.DataFrame,
    *,
    treatment: str,
    covariates: list[str],
    outcome: str,
    caliper: float | None = 0.2,
    random_state: int = 0,
) -> pd.DataFrame:
    """Nearest-neighbour propensity matching (1:1, no replacement).

    Fits a logistic propensity model, matches each treated unit to its nearest control on
    the propensity score (within ``caliper`` standard deviations of the logit score; the
    default ``0.2`` follows Austin 2011), and returns a tidy frame, one row per matched
    pair: ``treated_index``, ``control_index``, ``score_treated``, ``score_control``,
    ``outcome_treated``, ``outcome_control``, ``difference``. Treated units with no
    control within the caliper are dropped (the matched estimate is the ATT on the
    common-support region). ``caliper=None`` disables the caliper entirely -- greedy
    full matching, which can force distant pairs when overlap is limited.

    Treated units are matched in descending propensity order so the hardest-to-match
    extreme-score units are handled while close controls are still available (a
    material balance improvement; Austin 2011). Deterministic given ``random_state``
    (ties on score are broken by that seed). Never mutates ``df``.
    """
    if outcome not in df.columns:
        raise CausalError(f"unknown outcome {outcome!r}; expected one of {list(df.columns)!r}.")
    t = _validate_binary_treatment(df, treatment)
    design = _propensity_design(df, covariates)

    from sklearn.linear_model import LogisticRegression

    est = LogisticRegression(max_iter=1000)
    est.fit(design, t)
    logit = est.decision_function(design)
    scores = pd.Series(logit, index=df.index)

    treated_ids = df.index[t == 1]
    control_ids = df.index[t == 0]
    if len(treated_ids) == 0 or len(control_ids) == 0:
        raise CausalError("matching requires both treated and control units.")

    sc_tr = scores.loc[treated_ids].to_numpy()
    sc_ct = scores.loc[control_ids].to_numpy()

    if caliper is not None:
        if caliper <= 0:
            raise CausalError(f"caliper must be > 0 (in SD units) or None; got {caliper!r}.")
        pooled_sd = float(np.sqrt(0.5 * (sc_tr.var() + sc_ct.var())))
        bound = caliper * pooled_sd if pooled_sd > 0 else float("inf")
    else:
        bound = float("inf")

    used = np.zeros(len(control_ids), dtype=bool)
    pairs: list[dict[str, Any]] = []
    # Match hardest-to-match treated units first (descending propensity), per Austin
    # (2011): the extreme-score treated are matched while close controls are still
    # available, which materially improves covariate balance versus arbitrary order.
    for t_i, t_score in sorted(zip(treated_ids, sc_tr, strict=True), key=lambda x: -x[1]):
        # Order controls by score distance; ties broken by the stable argsort.
        dist = np.abs(sc_ct - t_score)
        order = np.argsort(dist, kind="stable")
        chosen: int | None = None
        for oi in order:
            if used[oi]:
                continue
            if dist[oi] > bound:
                break
            chosen = int(oi)
            break
        if chosen is None:
            continue
        used[chosen] = True
        c_id = control_ids[chosen]
        pairs.append(
            {
                "treated_index": t_i,
                "control_index": c_id,
                "score_treated": float(t_score),
                "score_control": float(sc_ct[chosen]),
                "outcome_treated": float(df.loc[t_i, outcome]),
                "outcome_control": float(df.loc[c_id, outcome]),
                "difference": float(df.loc[t_i, outcome] - df.loc[c_id, outcome]),
            }
        )
    if not pairs:
        raise CausalError(
            "no matched pairs were within the caliper; widen the caliper or pass caliper=None."
        )
    return pd.DataFrame(pairs)
