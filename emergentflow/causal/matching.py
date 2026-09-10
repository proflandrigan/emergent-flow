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
from sklearn.linear_model import LogisticRegression

from emergentflow.causal.errors import CausalError
from emergentflow.causal.propensity import _propensity_design, _validate_binary_treatment

__all__ = ["match_nearest"]

#: Default caliper in SD units of the logit propensity score (Austin 2011).
_DEFAULT_CALIPER = 0.2


def match_nearest(
    df: pd.DataFrame,
    *,
    treatment: str,
    covariates: list[str],
    outcome: str,
    caliper: float | None = _DEFAULT_CALIPER,
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
    material balance improvement; Austin 2011). Controls are shuffled once with
    ``random_state`` before the stable nearest-distance sort, so exact ties on score are
    broken by that seed (deterministic given ``random_state``). Everything is positional:
    a frame with a duplicated index (e.g. a bootstrap resample) matches correctly, and
    ``treated_index``/``control_index`` report the original index labels. Never mutates
    ``df``.
    """
    if outcome not in df.columns:
        raise CausalError(f"unknown outcome {outcome!r}; expected one of {list(df.columns)!r}.")
    t = _validate_binary_treatment(df, treatment).to_numpy()
    design = _propensity_design(df, covariates)

    est = LogisticRegression(max_iter=1000)
    est.fit(design, t)
    logit = np.asarray(est.decision_function(design), dtype=float)
    y = df[outcome].to_numpy(dtype=float)
    labels = np.asarray(df.index)

    pos_t = np.flatnonzero(t == 1)
    pos_c = np.flatnonzero(t == 0)
    if len(pos_t) == 0 or len(pos_c) == 0:
        raise CausalError("matching requires both treated and control units.")

    # Seeded shuffle of the controls: the stable argsort below then breaks exact score ties
    # by this order, which makes `random_state` the documented tie-breaker.
    rng = np.random.default_rng(random_state)
    pos_c = pos_c[rng.permutation(len(pos_c))]

    sc_tr = logit[pos_t]
    sc_ct = logit[pos_c]

    if caliper is not None:
        if caliper <= 0:
            raise CausalError(f"caliper must be > 0 (in SD units) or None; got {caliper!r}.")
        pooled_sd = float(np.sqrt(0.5 * (sc_tr.var() + sc_ct.var())))
        bound = caliper * pooled_sd if pooled_sd > 0 else float("inf")
    else:
        bound = float("inf")

    used = np.zeros(len(pos_c), dtype=bool)
    pairs: list[dict[str, Any]] = []
    # Match hardest-to-match treated units first (descending propensity), per Austin (2011).
    for ti in np.argsort(-sc_tr, kind="stable"):
        t_pos = pos_t[ti]
        t_score = sc_tr[ti]
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
        c_pos = pos_c[chosen]
        pairs.append(
            {
                "treated_index": labels[t_pos],
                "control_index": labels[c_pos],
                "score_treated": float(t_score),
                "score_control": float(sc_ct[chosen]),
                "outcome_treated": float(y[t_pos]),
                "outcome_control": float(y[c_pos]),
                "difference": float(y[t_pos] - y[c_pos]),
            }
        )
    if not pairs:
        raise CausalError(
            "no matched pairs were within the caliper; widen the caliper or pass caliper=None."
        )
    return pd.DataFrame(pairs)
