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


def test_reliability_kr20_requires_binary_items():
    items = _two_factor_items()
    with pytest.raises(PsychometricsError, match="dichotomous"):
        reliability(items, item_cols=list(items.columns), method="kr20")


def test_reliability_long_format_refuses_duplicate_pairs():
    long = pd.DataFrame(
        {
            "subject": ["s0", "s0", "s0", "s1", "s1"],
            "item": ["q0", "q1", "q0", "q0", "q1"],
            "score": [1.0, 2.0, 3.0, 1.0, 2.0],
        }
    )
    with pytest.raises(PsychometricsError, match="duplicate"):
        reliability(long, subject_col="subject", item_col="item", score_col="score")


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
    assert not row["out_of_range"]


def test_disattenuate_with_ci():
    out = disattenuate(0.42, reliability_x=0.9, reliability_y=0.8, n=200)
    row = out.iloc[0]
    for col in ("ci_low", "ci_high"):
        assert not pd.isna(row[col])
    assert row["ci_low"] < row["corrected_r"] < row["ci_high"]


def test_disattenuate_ci_matches_fisher_z():
    # With perfect reliabilities corrected_r == observed_r, so the CI must be the textbook
    # Fisher-z interval: r=0.42, n=100 -> (0.2437, 0.5694); r=0.90, n=100 -> (0.8547, 0.9317).
    row = disattenuate(0.42, reliability_x=1.0, reliability_y=1.0, n=100).iloc[0]
    assert (row["ci_low"], row["ci_high"]) == pytest.approx((0.2437, 0.5694), abs=1e-3)
    row = disattenuate(0.90, reliability_x=1.0, reliability_y=1.0, n=100).iloc[0]
    assert (row["ci_low"], row["ci_high"]) == pytest.approx((0.8547, 0.9317), abs=1e-3)
    assert -1.0 <= row["ci_low"] < row["ci_high"] <= 1.0
    # Disattenuated endpoints scale by the same denominator as the point estimate.
    row = disattenuate(0.42, reliability_x=0.9, reliability_y=0.8, n=100).iloc[0]
    denom = (0.9 * 0.8) ** 0.5
    assert row["ci_low"] == pytest.approx(0.2437 / denom, abs=1e-3)
    assert row["ci_high"] == pytest.approx(0.5694 / denom, abs=1e-3)


def test_disattenuate_perfect_correlation_has_degenerate_ci():
    row = disattenuate(1.0, reliability_x=1.0, reliability_y=1.0, n=50).iloc[0]
    assert row["ci_low"] == row["ci_high"] == 1.0


def test_disattenuate_attenuation_ratio_is_signed_and_flags_out_of_range():
    row = disattenuate(-0.42, reliability_x=0.9, reliability_y=0.8).iloc[0]
    assert row["attenuation_ratio"] < 0
    assert not row["out_of_range"]
    row = disattenuate(0.9, reliability_x=0.5, reliability_y=0.5).iloc[0]
    assert row["corrected_r"] == pytest.approx(1.8)
    assert row["out_of_range"]


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


def test_fit_irt_accepts_float_ids_and_keeps_distinct_types():
    long = _binary_irt_long(n_subj=60)
    as_float = long.assign(subject=long["subject"].astype(float))
    result = fit_irt(as_float, subject_col="subject", item_col="item", score_col="score")
    assert result.abilities.shape[0] == 60
    # int 1 and str "1" are different subjects, not one merged subject
    mixed = long.copy()
    mixed["subject"] = mixed["subject"].astype(object)
    mixed.loc[mixed["subject"] == 1, "subject"] = "1"
    extra = long[long["subject"] == 1].copy()
    extra["subject"] = 1
    extra["score"] = 1 - extra["score"]
    result = fit_irt(
        pd.concat([mixed, extra]), subject_col="subject", item_col="item", score_col="score"
    )
    assert result.abilities.shape[0] == 61


def test_fit_irt_accepts_missing_scores():
    long = _binary_irt_long(n_subj=60).astype({"score": float})
    long.loc[long.index[:5], "score"] = np.nan
    result = fit_irt(long, subject_col="subject", item_col="item", score_col="score")
    assert result.abilities.shape[0] == 60


def test_fit_irt_refuses_duplicate_pairs():
    long = _binary_irt_long(n_subj=60)
    dup = pd.concat([long, long.iloc[:3]])
    with pytest.raises(PsychometricsError, match="duplicate"):
        fit_irt(dup, subject_col="subject", item_col="item", score_col="score")


def test_fit_irt_reports_dropped_constant_items():
    long = _binary_irt_long(n_subj=60)
    long.loc[long["item"] == 3, "score"] = 1
    result = fit_irt(long, subject_col="subject", item_col="item", score_col="score")
    assert result.dropped_items == ["3"]
    assert "3" not in set(result.items["item"])
    assert result.items.shape[0] == 19


def test_fit_irt_theta_se_is_finite_and_positive():
    long = _binary_irt_long(n_subj=80)
    result = fit_irt(long, subject_col="subject", item_col="item", score_col="score")
    se = result.abilities["theta_se"]
    assert se.notna().all()
    assert (se > 0).all()
    # More extreme abilities carry less information -> larger SE.
    theta = result.abilities["theta"]
    assert se[theta.abs().idxmax()] > se[theta.abs().idxmin()]


def test_fit_irt_mle_perfect_score_does_not_blank_infit():
    long = _binary_irt_long(n_subj=80)
    long.loc[long["subject"] == 0, "score"] = 1  # a perfect scorer -> MLE theta is non-finite
    result = fit_irt(
        long, subject_col="subject", item_col="item", score_col="score", ability_method="mle"
    )
    assert result.fit["infit"].notna().all()
    assert result.abilities.loc[result.abilities["subject"] == "0", "theta_se"].isna().all()


def test_psychometrics_ops_registered_as_public_ops():
    from emergentflow.api import PUBLIC_OPS

    for name in (
        "ef.psychometrics.fit_irt",
        "ef.psychometrics.reliability",
        "ef.psychometrics.disattenuate",
    ):
        assert name in PUBLIC_OPS
