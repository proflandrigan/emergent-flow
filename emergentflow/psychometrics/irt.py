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
from dataclasses import dataclass, field
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
    import girth

    return girth


@dataclass
class IRTResult:
    """Structured, inspectable result of an IRT fit.

    Attributes
    ----------
    model: the fitted IRT model ("rasch"/"2pl"/"3pl").
    abilities: tidy frame, one row per subject: ``subject``, ``theta`` (ability estimate per
        ``ability_method``), and ``theta_se`` -- the conditional standard error
        ``1 / sqrt(I(theta))`` from the test information at the estimate over the items the
        subject answered (``nan`` when ``theta`` is non-finite, e.g. an MLE perfect score).
    items: tidy frame, one row per item: ``item``, ``difficulty``, ``discrimination``
        (1 for rasch), ``guessing`` (0 unless 3pl), and ``p_correct`` (observed proportion correct).
    fit: tidy frame, one row per item: ``infit`` and ``outfit`` mean-square statistics
        (values far from 1 flag misfitting items worth dropping).
    dropped_items: item labels dropped before fitting because every observed response was
        identical (MML cannot estimate a constant item's difficulty).
    """

    model: str
    abilities: pd.DataFrame
    items: pd.DataFrame
    fit: pd.DataFrame
    dropped_items: list[str] = field(default_factory=list)


def _long_to_matrix(
    responses: pd.DataFrame,
    *,
    subject_col: str,
    item_col: str,
    score_col: str,
) -> tuple[np.ndarray, list[str], list[str], list[str]]:
    """Validate *responses*; return ``(matrix, subjects, items, dropped_items)``.

    Long format (one row per subject-item) is the expected landing shape from a warehouse.
    The matrix is ``items x subjects`` ints with ``girth.INVALID_RESPONSE`` (-99999) marking
    missing cells (girth's native missing-data convention). Rows whose subject, item or score
    is missing are dropped first. Subjects keep first-appearance order; items are sorted.
    Ids are matched on their actual values via ``pd.factorize`` -- no ``str()`` round-trip, so
    a float-typed id column works and ``1`` / ``"1"`` stay distinct. Duplicate
    ``(subject, item)`` pairs are refused (silently keeping one would hide a data problem).
    Constant items (all observed responses identical) are dropped since MML cannot estimate
    their difficulty; their labels are returned as ``dropped_items``.
    """
    for col in (subject_col, item_col, score_col):
        if col not in responses.columns:
            raise PsychometricsError(
                f"unknown column {col!r}; expected one of {list(responses.columns)!r}."
            )
    scores = responses[score_col]
    if not scores.dropna().isin([0, 1, True, False]).all():
        raise PsychometricsError(f"score_col {score_col!r} must be binary (0/1 or True/False).")
    work = responses[[subject_col, item_col, score_col]].dropna()
    if work.empty:
        raise PsychometricsError("no complete subject-item responses.")
    dup = work.duplicated(subset=[subject_col, item_col])
    if dup.any():
        raise PsychometricsError(
            f"{int(dup.sum())} duplicate (subject, item) response(s) found; each subject may "
            "answer each item once. Aggregate or drop the duplicates before fitting."
        )
    score_codes = work[score_col].astype(int).to_numpy()
    subj_codes, subj_uniques = pd.factorize(work[subject_col], sort=False)
    item_codes, item_uniques = pd.factorize(work[item_col], sort=True)
    subjects = [str(s) for s in subj_uniques]
    items = [str(i) for i in item_uniques]

    import girth as _girth

    matrix = np.full((len(items), len(subjects)), _girth.INVALID_RESPONSE, dtype=int)
    matrix[item_codes, subj_codes] = score_codes

    # Drop constant items (MML cannot estimate them), reporting which ones.
    observed = matrix != _girth.INVALID_RESPONSE
    row_min = np.where(observed, matrix, 1).min(axis=1)
    row_max = np.where(observed, matrix, 0).max(axis=1)
    non_const = observed.any(axis=1) & (row_min != row_max)
    if not non_const.any():
        raise PsychometricsError(
            "every item is constant (all subjects responded identically); cannot fit an IRT model."
        )
    dropped = [name for name, keep in zip(items, non_const, strict=True) if not keep]
    kept = [name for name, keep in zip(items, non_const, strict=True) if keep]
    return matrix[non_const], subjects, kept, dropped


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
    mean-square statistics (``fit``) so misfitting items can be dropped. Missing scores
    (NaN) are dropped row-wise; duplicate ``(subject, item)`` pairs raise. Constant items
    are dropped before fitting and listed in ``dropped_items``. Never mutates ``responses``.
    """
    if model not in _IRT_MODELS:
        raise PsychometricsError(f"unknown model {model!r}; expected one of {list(_IRT_MODELS)!r}.")
    if ability_method not in ("eap", "map", "mle"):
        raise PsychometricsError(
            f"unknown ability_method {ability_method!r}; expected 'eap', 'map', or 'mle'."
        )
    girth = _require_girth()

    matrix, subjects, items, dropped_items = _long_to_matrix(
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

    from girth.unidimensional.dichotomous.ability_estimation import (
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
    finite_theta = np.isfinite(thetas)
    observed = matrix != invalid  # items x subjects

    # Conditional SE of theta from the test information at the estimate: for the 3PL
    # I_ij = a_j^2 * ((p_ij - c_j) / (1 - c_j))^2 * (1 - p_ij) / p_ij, summed over the items
    # the subject answered (reduces to sum a^2 p(1-p) for 2PL and sum p(1-p) for Rasch).
    a_col = discrimination[:, None]
    b_col = difficulty[:, None]
    c_col = guessing[:, None]
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        p_all = c_col + (1.0 - c_col) / (1.0 + np.exp(-a_col * (thetas[None, :] - b_col)))
        info = a_col**2 * ((p_all - c_col) / (1.0 - c_col)) ** 2 * (1.0 - p_all) / p_all
        info = np.where(observed & finite_theta[None, :], info, 0.0).sum(axis=0)
        theta_se = np.where(finite_theta & (info > 0), 1.0 / np.sqrt(info), np.nan)
    abilities_frame = pd.DataFrame({"subject": subjects, "theta": thetas, "theta_se": theta_se})

    # Fit statistics: infit/outfit mean-square from standardized residuals, computed over
    # the 1PL/2PL-consistent P(x=1) using the fitted parameters.
    fit_rows = []
    for j, item in enumerate(items):
        aj = float(discrimination[j])
        bj = float(difficulty[j])
        cj = float(guessing[j])
        pjx = cj + (1 - cj) / (1 + np.exp(-aj * (thetas - bj)))
        y = matrix[j].astype(float)
        # Mask unanswered cells AND subjects with a non-finite ability (e.g. an MLE perfect
        # score), otherwise one NaN theta blanks the whole infit column.
        valid = (y != invalid) & finite_theta
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

    return IRTResult(
        model=model,
        abilities=abilities_frame,
        items=items_frame,
        fit=fit_frame,
        dropped_items=dropped_items,
    )
