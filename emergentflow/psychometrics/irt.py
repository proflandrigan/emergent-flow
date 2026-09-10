"""
emergentflow.psychometrics.irt
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Item-response-theory ability estimation (issue #164 Gap 3a).

``ef.psychometrics.fit_irt`` fits a unidimensional dichotomous IRT model to long-format
item responses and returns per-subject ability estimates, per-item parameters, and
per-item fit summaries. Backed by ``girth`` (marginal maximum likelihood); requires the
optional ``emergentflow[psychometrics]`` extra. ``model`` is ``"rasch"`` (discrimination
fixed at 1), ``"2pl"``, or ``"3pl"``.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from emergentflow.api import public_op
from emergentflow.psychometrics.errors import MissingOptionalDependencyError, PsychometricsError

__all__ = ["IRTResult", "fit_irt"]

_EXTRA = "emergentflow[psychometrics]"
_IRT_MODELS = ("rasch", "2pl", "3pl")


def _require_girth() -> Any:
    if importlib.util.find_spec("girth") is None:
        raise MissingOptionalDependencyError(_EXTRA)
    import girth  # type: ignore[import-untyped]

    return girth


@dataclass
class IRTResult:
    """Structured, inspectable result of an IRT fit.

    Attributes
    ----------
    model: the fitted IRT model ("rasch"/"2pl"/"3pl").
    abilities: tidy frame, one row per subject: ``subject``, ``theta`` (EAP ability
        estimate), and ``theta_se`` when the backend reports an SE.
    items: tidy frame, one row per item: ``item``, ``difficulty``, ``discrimination``
        (1 for rasch), and ``p_correct`` (observed proportion correct).
    fit: tidy frame, one row per item: ``infit`` and ``outfit`` mean-square statistics
        (values far from 1 flag misfitting items worth dropping).
    """

    model: str
    abilities: pd.DataFrame
    items: pd.DataFrame
    fit: pd.DataFrame


def _long_to_matrix(
    responses: pd.DataFrame,
    *,
    subject_col: str,
    item_col: str,
    score_col: str,
) -> tuple[np.ndarray, list[str], list[str]]:
    """Validate *responses* and return ``(responses_matrix, subjects, items)``.

    Long format (one row per subject-item) is the expected landing shape from a warehouse.
    The matrix is ``items x subjects`` ints with ``girth.INVALID_RESPONSE`` (-99999) marking
    missing cells, matching girth's native missing-data convention. Constant items (all
    correct or all incorrect) are dropped since MML cannot estimate their difficulty.
    """
    for col in (subject_col, item_col, score_col):
        if col not in responses.columns:
            raise PsychometricsError(
                f"unknown column {col!r}; expected one of {list(responses.columns)!r}."
            )
    scores = responses[score_col]
    if not scores.dropna().isin([0, 1, True, False]).all():
        raise PsychometricsError(f"score_col {score_col!r} must be binary (0/1 or True/False).")
    work = responses[[subject_col, item_col, score_col]].copy()
    work[score_col] = work[score_col].astype(int)
    work = work.dropna(subset=[subject_col, item_col, score_col])
    if work.empty:
        raise PsychometricsError("no complete subject-item responses.")
    items_seen = work.groupby(item_col).size()
    keep_items = [str(i) for i in items_seen.index]

    subjects = [str(s) for s in work[subject_col].drop_duplicates()]
    n = len(subjects)
    k = len(keep_items)
    import girth as _girth

    matrix = np.full((k, n), _girth.INVALID_RESPONSE, dtype=int)
    subj_index = {s: i for i, s in enumerate(subjects)}
    item_index = {str(i): j for j, i in enumerate(keep_items)}
    for _, row in work.iterrows():
        si = subj_index[str(row[subject_col])]
        ii = item_index[str(row[item_col])]
        matrix[ii, si] = int(row[score_col])

    # Drop constant items (MML cannot estimate them).
    non_const = []
    for j in range(k):
        valid = matrix[j][matrix[j] != _girth.INVALID_RESPONSE]
        if len(valid) > 0 and valid.min() != valid.max():
            non_const.append(j)
    if not non_const:
        raise PsychometricsError(
            "every item is constant (all subjects responded identically); cannot fit an IRT model."
        )
    matrix = matrix[non_const]
    keep_items = [keep_items[j] for j in non_const]
    return matrix, subjects, keep_items


@public_op(name="ef.psychometrics.fit_irt")
def fit_irt(
    responses: pd.DataFrame,
    *,
    subject_col: str,
    item_col: str,
    score_col: str,
    model: str = "rasch",
    ability_method: str = "eap",
) -> IRTResult:
    """Fit an IRT model to long-format binary item responses.

    ``responses`` has one row per subject-item: ``subject_col`` names the subject,
    ``item_col`` the item, ``score_col`` the binary 0/1 score. ``model`` is ``"rasch"``
    (default), ``"2pl"``, or ``"3pl"``. Requires the optional ``emergentflow[psychometrics]``
    extra (raises typed ``MissingOptionalDependencyError`` otherwise).

    Returns an :class:`IRTResult` with per-subject ability estimates (``abilities``),
    per-item difficulty/discrimination/guessing (``items``), and per-item infit/outfit
    mean-square statistics (``fit``) so misfitting items can be dropped. Never mutates
    ``responses``.
    """
    if model not in _IRT_MODELS:
        raise PsychometricsError(f"unknown model {model!r}; expected one of {list(_IRT_MODELS)!r}.")
    if ability_method not in ("eap", "map", "mle"):
        raise PsychometricsError(
            f"unknown ability_method {ability_method!r}; expected 'eap', 'map', or 'mle'."
        )
    girth = _require_girth()

    matrix, subjects, items = _long_to_matrix(
        responses, subject_col=subject_col, item_col=item_col, score_col=score_col
    )
    invalid = girth.INVALID_RESPONSE

    model_lower = model.lower()
    if model_lower == "rasch":
        est = girth.rasch_mml(matrix)
        discrimination = np.full(matrix.shape[0], 1.0)
        guessing = np.full(matrix.shape[0], 0.0)
    elif model_lower == "2pl":
        est = girth.twopl_mml(matrix)
        discrimination = np.asarray(est["Discrimination"], dtype=float)
        guessing = np.full(matrix.shape[0], 0.0)
    else:  # 3pl
        est = girth.threepl_mml(matrix)
        discrimination = np.asarray(est["Discrimination"], dtype=float)
        guessing = np.asarray(est["Guessing"], dtype=float)
    difficulty = np.asarray(est["Difficulty"], dtype=float)

    from girth.unidimensional.dichotomous.ability_estimation import (  # type: ignore[import-untyped]
        ability_eap,
        ability_map,
        ability_mle,
    )

    fn = {"eap": ability_eap, "map": ability_map, "mle": ability_mle}[ability_method]
    thetas = np.asarray(fn(matrix, difficulty, discrimination), dtype=float)

    # Items frame (treat the -99999 markers as missing).
    p_correct = np.asarray(
        [
            float(np.nanmean(np.where(matrix[j] != invalid, matrix[j], np.nan)))
            for j in range(matrix.shape[0])
        ],
        dtype=float,
    )
    items_frame = pd.DataFrame(
        {
            "item": items,
            "difficulty": difficulty,
            "discrimination": discrimination,
            "guessing": guessing,
            "p_correct": p_correct,
        }
    )
    abilities_frame = pd.DataFrame({"subject": subjects, "theta": thetas, "theta_se": float("nan")})

    # Fit statistics: infit/outfit mean-square from standardized residuals, computed over
    # the 1PL/2PL-consistent P(x=1) using the fitted parameters.
    fit_rows = []
    for j, item in enumerate(items):
        aj = float(discrimination[j])
        bj = float(difficulty[j])
        cj = float(guessing[j])
        pjx = cj + (1 - cj) / (1 + np.exp(-aj * (thetas - bj)))
        y = matrix[j].astype(float)
        valid = y != invalid
        y = y[valid]
        p = pjx[valid]
        resid = y - p
        w = p * (1 - p)
        with np.errstate(divide="ignore", invalid="ignore"):
            infit = float(np.sum(resid**2) / np.sum(w)) if w.sum() > 0 else float("nan")
            eff = np.divide(resid**2, w, out=np.full_like(w, np.nan), where=w > 0)
            outfit = float(np.nanmean(eff)) if np.isfinite(np.nanmean(eff)) else float("nan")
        fit_rows.append({"item": item, "infit": infit, "outfit": outfit})
    fit_frame = pd.DataFrame(fit_rows)

    return IRTResult(model=model, abilities=abilities_frame, items=items_frame, fit=fit_frame)
