"""Tests for the psychometrics family (`emergentflow.psychometrics`, issue #164 Gap 3).

Covers `reliability` (Cronbach's alpha / KR-20 / per-item-dropped alpha),
`disattenuate` (measurement-error correction + attainable ceiling), and `fit_irt`
(Rasch/2PL/3PL ability estimation; gated on the optional `girth` dependency via
`pytest.importorskip`, matching the repo's optional-extra test pattern).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from emergentflow.psychometrics import (
    IRTResult,
    disattenuate,
    fit_irt,
    reliability,
)
from emergentflow.psychometrics.errors import MissingOptionalDependencyError, PsychometricsError

girth = pytest.importorskip("girth")  # noqa: F401 - gates the IRT tests below


def _two_factor_items(n_subj: int = 200, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    true = rng.normal(size=n_subj)
    return pd.DataFrame({f"i{k}": true + rng.normal(scale=1.0, size=n_subj) for k in range(8)})


def _binary_irt_long(n_items: int = 20, n_subj: int = 200, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    theta = rng.normal(0, 1, n_subj)
    diff = np.linspace(-2, 2, n_items)
    p = 1 / (1 + np.exp(-(theta[None, :] - diff[:, None])))
    resp = (rng.random((n_items, n_subj)) < p).astype(int)
    subjects = np.repeat(np.arange(n_subj), n_items)
    items = np.tile(np.arange(n_items), n_subj)
    return pd.DataFrame({"subject": subjects, "item": items, "score": resp.T.ravel()})


# ---------------------------------------------------------------------------
# reliability
# ---------------------------------------------------------------------------


def test_reliability_alpha_and_if_dropped():
    items = _two_factor_items()
    result = reliability(items, item_cols=list(items.columns))
    assert set(result.columns) == {
        "item",
        "alpha_if_dropped",
        "n_items",
        "n_subjects",
        "alpha",
        "kr20",
    }
    assert 0.0 < result["alpha"].iloc[0] < 1.0
    assert result["n_items"].iloc[0] == 8
    assert result["n_subjects"].iloc[0] == 200
    assert result["kr20"].iloc[0] != result["kr20"].iloc[0]  # non-binary => nan


def test_reliability_long_format_pivot():
    rng = np.random.default_rng(2)
    n_subj, n_items = 100, 6
    true = rng.normal(size=n_subj)
    long_rows = []
    for s in range(n_subj):
        for it in range(n_items):
            long_rows.append(
                {"subject": f"s{s}", "item": f"q{it}", "score": true[s] + rng.normal()}
            )
    long = pd.DataFrame(long_rows)
    result = reliability(long, subject_col="subject", item_col="item", score_col="score")
    assert 0.0 < result["alpha"].iloc[0] < 1.0
    assert result["n_items"].iloc[0] == n_items


def test_reliability_binary_kr20():
    rng = np.random.default_rng(3)
    n_subj, n_items = 150, 10
    theta = rng.normal(size=n_subj)
    p = 1 / (1 + np.exp(-(theta[:, None] - np.linspace(-1, 1, n_items)[None, :])))
    matrix = pd.DataFrame((rng.random((n_subj, n_items)) < p).astype(int))
    result = reliability(matrix, item_cols=list(matrix.columns))
    assert 0.0 < result["kr20"].iloc[0] <= 1.0


def test_reliability_needs_two_items():
    items = pd.DataFrame({"a": [1, 2, 3], "b": [1, 2, 3]})
    with pytest.raises(PsychometricsError, match="two items"):
        reliability(items, item_cols=["a"])


def test_reliability_unknown_item_raises():
    items = _two_factor_items()
    with pytest.raises(PsychometricsError, match="item columns"):
        reliability(items, item_cols=["nope", "also_nope"])


# ---------------------------------------------------------------------------
# disattenuate
# ---------------------------------------------------------------------------


def test_disattenuate_known_values():
    # r=0.42, rel_x=0.9, rel_y=0.8 -> corrected = 0.42/sqrt(0.72) = 0.49497;
    # max_attainable = sqrt(0.72) = 0.84853.
    out = disattenuate(0.42, reliability_x=0.9, reliability_y=0.8)
    row = out.iloc[0]
    assert row["corrected_r"] == pytest.approx(0.494975, abs=1e-4)
    assert row["max_attainable_r"] == pytest.approx(0.848528, abs=1e-4)
    assert row["attenuation_ratio"] == pytest.approx(0.494975, abs=1e-4)


def test_disattenuate_with_ci():
    out = disattenuate(0.42, reliability_x=0.9, reliability_y=0.8, n=200)
    row = out.iloc[0]
    for col in ("ci_low", "ci_high"):
        assert not pd.isna(row[col])
    assert row["ci_low"] < row["corrected_r"] < row["ci_high"]


def test_disattenuate_invalid_reliability_raises():
    with pytest.raises(PsychometricsError, match="reliability"):
        disattenuate(0.5, reliability_x=1.5, reliability_y=0.8)
    with pytest.raises(PsychometricsError, match="reliability"):
        disattenuate(0.5, reliability_x=0.0, reliability_y=0.8)


# ---------------------------------------------------------------------------
# fit_irt
# ---------------------------------------------------------------------------


def test_fit_irt_rasch_recovers_abilities():
    long = _binary_irt_long()
    result = fit_irt(long, subject_col="subject", item_col="item", score_col="score")
    assert isinstance(result, IRTResult)
    assert result.model == "rasch"
    assert result.abilities.shape == (200, 3)
    assert set(result.abilities.columns) == {"subject", "theta", "theta_se"}
    assert result.items.shape[0] == 20
    assert result.fit.shape[0] == 20
    # abilities correlate strongly with the generating theta
    rng = np.random.default_rng(1)
    theta = rng.normal(0, 1, 200)
    assert np.corrcoef(result.abilities["theta"], theta)[0, 1] > 0.7


@pytest.mark.parametrize("model", ["rasch", "2pl", "3pl"])
def test_fit_irt_model_variants(model):
    long = _binary_irt_long(n_subj=150, seed=4)
    result = fit_irt(long, subject_col="subject", item_col="item", score_col="score", model=model)
    assert result.model == model
    assert result.items.shape[1] == 5  # item, difficulty, discrimination, guessing, p_correct
    assert not result.items["difficulty"].isna().all()


def test_fit_irt_unknown_model_raises():
    long = _binary_irt_long(n_subj=50)
    with pytest.raises(PsychometricsError, match="model"):
        fit_irt(long, subject_col="subject", item_col="item", score_col="score", model="nope")


def test_fit_irt_non_binary_score_raises():
    long = _binary_irt_long(n_subj=50)
    long["score"] = long["score"] * 2
    with pytest.raises(PsychometricsError, match="binary"):
        fit_irt(long, subject_col="subject", item_col="item", score_col="score")


def test_fit_irt_missing_extra_raises_typed(monkeypatch):
    import importlib.util

    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *a, **k: None)
    long = _binary_irt_long(n_subj=50)
    with pytest.raises(MissingOptionalDependencyError):
        fit_irt(long, subject_col="subject", item_col="item", score_col="score")


def test_psychometrics_ops_registered_as_public_ops():
    from emergentflow.api import PUBLIC_OPS

    for name in (
        "ef.psychometrics.fit_irt",
        "ef.psychometrics.reliability",
        "ef.psychometrics.disattenuate",
    ):
        assert name in PUBLIC_OPS
