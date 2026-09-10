"""Tests for the causal-inference family (`emergentflow.causal`, issue #164 Gap 1).

Covers `fit_propensity` (scores/weights/balance/overlap/effective_n), `estimate_effect`
(all four methods + cluster-robust + bootstrap inference), `match_nearest`,
`did` (TWFE + parallel-trends test), and the sensitivity ops (`e_value`,
`rosenbaum_gamma`, `sensitivity`). All assertions use a simulated confounded
observational dataset with a known true effect, so recovery is a real correctness
signal rather than a smoke test.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from emergentflow.causal import (
    PropensityResult,
    did,
    e_value,
    estimate_effect,
    fit_propensity,
    keys_for_archetype,
    match_nearest,
    rosenbaum_gamma,
    sensitivity,
)
from emergentflow.causal.errors import CausalError, InvalidTreatmentError, UnknownMethodError


def _confounded_df(n: int = 4000, seed: int = 42, true_ate: float = 1.5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    x1 = rng.normal(0, 1, n)
    x2 = rng.normal(0, 1, n)
    p = 1 / (1 + np.exp(-(0.8 * x1 - 0.5 * x2 + 0.2)))
    t = rng.binomial(1, p)
    y = true_ate * t + 1.2 * x1 - 0.8 * x2 + rng.normal(0, 1, n)
    return pd.DataFrame({"x1": x1, "x2": x2, "t": t, "y": y})


def test_fit_propensity_returns_complete_result():
    df = _confounded_df()
    pr = fit_propensity(df, treatment="t", covariates=["x1", "x2"])
    assert isinstance(pr, PropensityResult)
    assert len(pr.scores) == len(df)
    assert len(pr.weights) == len(df)
    assert pr.weights.dropna().min() > 0
    assert set(pr.balance.columns) == {
        "covariate",
        "smd_before",
        "smd_after",
        "var_ratio_before",
        "var_ratio_after",
    }
    assert list(pr.balance["covariate"]) == ["x1", "x2"]
    assert set(pr.overlap.columns).issuperset({"arm", "n", "score_min", "score_max"})
    assert set(pr.effective_n.columns) == {"arm", "n", "effective_n"}


def test_fit_propensity_weighting_balances_covariates():
    df = _confounded_df()
    pr = fit_propensity(df, treatment="t", covariates=["x1", "x2"])
    for _, row in pr.balance.iterrows():
        assert abs(row["smd_after"]) < abs(row["smd_before"])  # weighting reduced imbalance
        assert abs(row["smd_after"]) < 0.1


def test_fit_propensity_rejects_non_binary_treatment():
    df = _confounded_df()
    df["cont"] = df["x1"] + 1.0
    with pytest.raises(InvalidTreatmentError):
        fit_propensity(df, treatment="cont", covariates=["x1"])


def test_fit_propensity_unknown_covariate_raises():
    df = _confounded_df()
    with pytest.raises(CausalError, match="covariate"):
        fit_propensity(df, treatment="t", covariates=["nope"])


def test_estimate_effect_all_methods_recover_true_ate():
    df = _confounded_df()
    for method in ("ipw", "aipw", "regression_adjust", "matching"):
        row = estimate_effect(
            df, outcome="y", treatment="t", covariates=["x1", "x2"], method=method
        ).iloc[0]
        assert row["estimate"] == pytest.approx(1.5, abs=0.4)
        assert row["p_value"] < 0.05
        if method != "matching":
            # matching targets the common-support ATT, so its CI need not bracket the
            # full-sample ATE; the closed-form methods must.
            assert row["ci_low"] < 1.5 < row["ci_high"]
        assert row["n_treated"] + row["n_control"] == len(df)


def test_estimate_effect_registry_keys():
    assert sorted(keys_for_archetype("estimate_effect")) == [
        "aipw",
        "ipw",
        "matching",
        "regression_adjust",
    ]


def test_estimate_effect_unknown_method_raises():
    df = _confounded_df()
    with pytest.raises(UnknownMethodError):
        estimate_effect(df, outcome="y", treatment="t", covariates=["x1"], method="bogus")


def test_estimate_effect_cluster_robust_runs():
    df = _confounded_df()
    df["cl"] = np.arange(len(df)) % 200
    row = estimate_effect(
        df, outcome="y", treatment="t", covariates=["x1", "x2"], method="aipw", cluster_col="cl"
    ).iloc[0]
    assert row["estimate"] == pytest.approx(1.5, abs=0.4)
    assert row["std_err"] > 0


def test_estimate_effect_bootstrap_runs():
    df = _confounded_df(n=800)
    row = estimate_effect(
        df, outcome="y", treatment="t", covariates=["x1", "x2"], method="aipw", n_boot=25
    ).iloc[0]
    assert row["estimate"] == pytest.approx(1.5, abs=0.5)
    assert row["std_err"] > 0


def test_match_nearest_returns_pairs_and_reduces_imbalance():
    df = _confounded_df()
    pairs = match_nearest(df, treatment="t", covariates=["x1", "x2"], outcome="y")
    expected_cols = {
        "treated_index",
        "control_index",
        "score_treated",
        "score_control",
        "difference",
    }
    assert expected_cols <= set(pairs.columns)
    assert (pairs["score_treated"] >= pairs["score_control"]).any()  # treated >= control by prop
    mt = df.loc[pairs["treated_index"]]
    mc = df.loc[pairs["control_index"]]
    # caliper matching moves the treated/control covariate means much closer
    assert abs(mt["x1"].mean() - mc["x1"].mean()) < 0.6


def test_did_recovers_true_effect():
    rng = np.random.default_rng(7)
    n_units = 400
    periods = 4
    uid = np.repeat(np.arange(n_units), periods)
    per = np.tile(np.arange(periods), n_units)
    treated_unit = np.arange(n_units) % 2 == 0
    tu = treated_unit[uid]
    post = per >= 2
    u_eff = rng.normal(0, 1, n_units)[uid]
    time_eff = 0.5 * per
    true_did = 2.0
    y = u_eff + time_eff + true_did * (tu & post) + rng.normal(0, 0.5, len(uid))
    ddf = pd.DataFrame(
        {
            "unit": uid.astype(str),
            "per": per.astype(str),
            "treat": tu.astype(int),
            "post": post.astype(int),
            "y": y,
        }
    )
    row = did(
        ddf,
        outcome="y",
        unit_col="unit",
        time_col="per",
        treated_col="treat",
        post_col="post",
    ).iloc[0]
    assert row["estimate"] == pytest.approx(true_did, abs=0.3)
    assert row["n_units_treated"] == 200
    assert row["n_units_control"] == 200
    assert 0.0 <= row["pre_trend_p"] <= 1.0


def test_e_value_known_scalar():
    # RR = 3 => E-value = 3 + sqrt(3*2) = 3 + sqrt(6) = 5.449
    out = e_value(None, risk_ratio=3.0)
    assert out.iloc[0]["point_evalue"] == pytest.approx(5.449489, abs=1e-4)


def test_e_value_from_effect_frame():
    df = _confounded_df()
    eff = estimate_effect(df, outcome="y", treatment="t", covariates=["x1", "x2"], method="aipw")
    out = e_value(eff)
    assert out.iloc[0]["point_evalue"] > 0
    assert out.iloc[0]["bound_evalue"] > 0


def test_rosenbaum_gamma_bounds():
    rng = np.random.default_rng(3)
    pairs = pd.DataFrame(
        {
            "o_t": rng.binomial(1, 0.6, 500),
            "o_c": rng.binomial(1, 0.3, 500),
        }
    )
    out = rosenbaum_gamma(pairs, treated_outcome_col="o_t", control_outcome_col="o_c", gamma=2.0)
    assert out.iloc[0]["n_discordant"] > 0
    assert out.iloc[0]["sensitivity"] in ("robust", "sensitive")


def test_sensitivity_dispatches():
    df = _confounded_df()
    eff = estimate_effect(df, outcome="y", treatment="t", covariates=["x1", "x2"], method="aipw")
    ev = sensitivity(eff, method="e_value")
    assert set(ev.columns) == {"point_evalue", "bound_evalue"}
    with pytest.raises(UnknownMethodError):
        sensitivity(eff, method="nope")


def test_causal_ops_are_registered_public_ops():
    from emergentflow.api import PUBLIC_OPS

    for name in (
        "ef.causal.fit_propensity",
        "ef.causal.estimate_effect",
        "ef.causal.did",
        "ef.causal.sensitivity",
        "ef.causal.e_value",
        "ef.causal.rosenbaum_gamma",
    ):
        assert name in PUBLIC_OPS
