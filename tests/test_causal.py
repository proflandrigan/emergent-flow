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


@pytest.mark.parametrize(
    ("rr", "expected"),
    [(3.0, 5.449490), (0.8, 1.809017), (0.5, 3.414214), (0.25, 7.464102)],
)
def test_e_value_inverts_protective_effects(rr, expected):
    # VanderWeele & Ding 2017: RR < 1 is inverted first, so 0.25 needs the same confounder as 4.0.
    out = e_value(None, risk_ratio=rr)
    assert out.iloc[0]["point_evalue"] == pytest.approx(expected, abs=1e-4)


def _effect_frame(est: float, lo: float, hi: float) -> pd.DataFrame:
    return pd.DataFrame([{"estimate": est, "ci_low": lo, "ci_high": hi}])


def test_e_value_bound_selected_on_ratio_scale():
    # A null-crossing interval can be explained by no confounding at all.
    assert e_value(_effect_frame(0.6, 0.3, 1.4)).iloc[0]["bound_evalue"] == 1.0
    assert e_value(_effect_frame(1.6, 0.9, 2.4)).iloc[0]["bound_evalue"] == 1.0
    # Protective: the upper bound is nearest the null -> E(1 / 0.7).
    bound = e_value(_effect_frame(0.5, 0.4, 0.7)).iloc[0]["bound_evalue"]
    assert bound == pytest.approx(2.2110, abs=1e-3)
    # Harmful: the lower bound is nearest the null -> E(1.5).
    bound = e_value(_effect_frame(2.0, 1.5, 2.7)).iloc[0]["bound_evalue"]
    assert bound == pytest.approx(2.3660, abs=1e-3)


def test_e_value_difference_scale_is_scale_free():
    eff = _effect_frame(1.5, 1.0, 2.0)
    out = e_value(eff, scale="difference", sd=3.0).iloc[0]
    # d = 0.5 -> RR = exp(0.91 * 0.5) = 1.5762 -> E = 2.5291
    assert out["point_evalue"] == pytest.approx(2.5291, abs=1e-3)
    scaled = e_value(eff * 100.0, scale="difference", sd=300.0).iloc[0]
    assert scaled["point_evalue"] == pytest.approx(out["point_evalue"])
    assert scaled["bound_evalue"] == pytest.approx(out["bound_evalue"])
    with pytest.raises(CausalError, match="sd"):
        e_value(eff, scale="difference")
    with pytest.raises(CausalError, match="scale"):
        e_value(eff, scale="odds")


def test_e_value_rejects_nonpositive_ratio_estimate():
    with pytest.raises(CausalError, match="risk-ratio scale"):
        e_value(_effect_frame(-0.2, -0.5, 0.1))


def test_rosenbaum_gamma_is_direction_symmetric():
    rng = np.random.default_rng(3)
    o_t = rng.binomial(1, 0.6, 500)
    o_c = rng.binomial(1, 0.3, 500)
    harmful = pd.DataFrame({"o_t": o_t, "o_c": o_c})
    protective = pd.DataFrame({"o_t": o_c, "o_c": o_t})
    kw = {"treated_outcome_col": "o_t", "control_outcome_col": "o_c", "gamma": 1.5}
    h = rosenbaum_gamma(harmful, **kw).iloc[0]
    p = rosenbaum_gamma(protective, **kw).iloc[0]
    assert h["direction"] == "treated_higher"
    assert p["direction"] == "treated_lower"
    assert p["p_high"] == pytest.approx(h["p_high"])
    assert p["p_low"] == pytest.approx(h["p_low"])
    assert h["p_low"] <= h["p_high"]
    with pytest.raises(CausalError, match="gamma"):
        rosenbaum_gamma(harmful, **{**kw, "gamma": float("nan")})


_KW = {"outcome": "y", "treatment": "t", "covariates": ["x1", "x2"]}


def test_ipw_is_hajek_and_location_invariant():
    df = _confounded_df(n=3000, seed=11)
    base = estimate_effect(df, method="ipw", **_KW).iloc[0]
    shifted = estimate_effect(df.assign(y=df["y"] + 1000.0), method="ipw", **_KW).iloc[0]
    assert base["estimate"] == pytest.approx(1.5, abs=0.3)
    assert shifted["estimate"] == pytest.approx(base["estimate"], abs=1e-6)
    assert shifted["std_err"] == pytest.approx(base["std_err"], rel=1e-6)


def test_matching_bootstrap_and_duplicate_index_work():
    df = _confounded_df(n=600, seed=5)
    row = estimate_effect(df, method="matching", n_boot=10, **_KW).iloc[0]
    assert np.isfinite(row["std_err"]) and row["std_err"] > 0
    plain = estimate_effect(df, method="matching", **_KW).iloc[0]
    dup = df.copy()
    dup.index = np.zeros(len(dup), dtype=int)
    row2 = estimate_effect(dup, method="matching", **_KW).iloc[0]
    assert row2["estimate"] == pytest.approx(plain["estimate"])
    assert 0 < row2["effective_n"] <= min(row2["n_treated"], row2["n_control"])


def test_estimate_effect_requires_both_arms():
    df = _confounded_df(n=200).assign(t=1)
    for method in ("ipw", "aipw", "matching", "regression_adjust"):
        with pytest.raises(InvalidTreatmentError, match="both"):
            estimate_effect(df, method=method, **_KW)


def test_estimate_effect_rejects_missing_values_and_bad_cluster_col():
    df = _confounded_df(n=300)
    hole = df.index != 3
    with pytest.raises(CausalError, match="missing"):
        estimate_effect(df.assign(y=df["y"].where(hole)), method="aipw", **_KW)
    with pytest.raises(CausalError, match="missing"):
        estimate_effect(df.assign(x1=df["x1"].where(hole)), method="aipw", **_KW)
    with pytest.raises(InvalidTreatmentError, match="missing"):
        estimate_effect(df.assign(t=df["t"].where(hole)), method="aipw", **_KW)
    with pytest.raises(CausalError, match="cluster_col"):
        estimate_effect(df, method="matching", cluster_col="nope", **_KW)
    holey = df.assign(cl=np.where(hole, np.arange(len(df)) % 20, np.nan))
    with pytest.raises(CausalError, match="cluster_col"):
        estimate_effect(holey, method="aipw", cluster_col="cl", **_KW)
    with pytest.raises(CausalError, match="n_boot"):
        estimate_effect(
            df.assign(cl=np.arange(len(df)) % 20), method="matching", cluster_col="cl", **_KW
        )


def test_effective_n_is_kish_for_ipw_and_pairs_for_matching():
    df = _confounded_df(n=800, seed=2)
    ipw = estimate_effect(df, method="ipw", **_KW).iloc[0]
    w = fit_propensity(df, treatment="t", covariates=["x1", "x2"], trim=None).weights.to_numpy()
    assert ipw["effective_n"] == pytest.approx(w.sum() ** 2 / (w**2).sum(), rel=1e-6)
    m = estimate_effect(df, method="matching", **_KW).iloc[0]
    pairs = match_nearest(df, treatment="t", covariates=["x1", "x2"], outcome="y")
    assert m["effective_n"] == len(pairs)
    ra = estimate_effect(df, method="regression_adjust", **_KW).iloc[0]
    assert ra["effective_n"] == len(df)


def test_estimate_effect_caliper_is_plumbed_through():
    df = _confounded_df(n=800, seed=2)
    wide = estimate_effect(df, method="matching", caliper=None, **_KW).iloc[0]
    narrow = estimate_effect(df, method="matching", caliper=0.01, **_KW).iloc[0]
    assert narrow["effective_n"] < wide["effective_n"]


def test_estimate_effect_methods_come_from_the_registry():
    assert set(keys_for_archetype("estimate_effect")) == {
        "ipw",
        "aipw",
        "matching",
        "regression_adjust",
    }


def test_p_value_does_not_underflow_to_zero():
    df = _confounded_df(n=4000, true_ate=0.5)
    row = estimate_effect(df, method="regression_adjust", **_KW).iloc[0]
    assert 0.0 < row["p_value"] < 1e-30


def test_propensity_balance_zero_variance_covariate_is_nan():
    df = _confounded_df(n=500).assign(const=1.0)
    pr = fit_propensity(df, treatment="t", covariates=["x1", "const"])
    row = pr.balance.set_index("covariate").loc["const"]
    assert np.isnan(row["smd_before"]) and np.isnan(row["smd_after"])


def test_match_nearest_random_state_only_breaks_ties():
    df = _confounded_df(n=400, seed=9)
    a = match_nearest(df, treatment="t", covariates=["x1", "x2"], outcome="y", random_state=0)
    b = match_nearest(df, treatment="t", covariates=["x1", "x2"], outcome="y", random_state=1)
    # Continuous scores have no exact ties, so the seed must not change the result.
    pd.testing.assert_frame_equal(a, b)


_DID_KW = {
    "outcome": "y",
    "unit_col": "unit",
    "time_col": "per",
    "treated_col": "treat",
    "post_col": "post",
}


def _panel(
    n_units: int = 200,
    periods: int = 6,
    seed: int = 7,
    *,
    staggered: bool = False,
    nonlinear: bool = False,
    effect: float = 2.0,
) -> pd.DataFrame:
    """Balanced panel with a known DiD effect and parallel trends by construction.

    ``staggered=True`` lets treated units adopt at period 2, 3 or 4 (controls never);
    ``nonlinear=True`` swaps the linear common trend for a quadratic one.
    """
    rng = np.random.default_rng(seed)
    uid = np.repeat(np.arange(n_units), periods)
    per = np.tile(np.arange(periods), n_units)
    treated_unit = np.arange(n_units) % 2 == 0
    tu = treated_unit[uid]
    if staggered:
        adopt = np.where(treated_unit, 2 + (np.arange(n_units) // 2) % 3, periods + 1)[uid]
        post = per >= adopt
    else:
        post = per >= periods // 2
    u_eff = rng.normal(0, 1, n_units)[uid]
    time_eff = 0.3 * per**2 if nonlinear else 0.5 * per
    y = u_eff + time_eff + effect * (tu & post) + rng.normal(0, 0.5, len(uid))
    return pd.DataFrame(
        {
            "unit": uid.astype(str),
            "per": per.astype(str),
            "treat": tu.astype(int),
            "post": post.astype(int),
            "y": y,
        }
    )


def test_did_pre_trend_test_survives_staggered_nonlinear_common_trend():
    df = _panel(staggered=True, nonlinear=True)
    row = did(df, **_DID_KW).iloc[0]
    assert row["pre_trend_p"] > 0.05  # parallel trends hold by construction
    assert row["estimate"] == pytest.approx(2.0, abs=0.3)
    # ... while a real differential pre-trend is still detected.
    slope = 0.4 * df["per"].astype(int) * df["treat"]
    row2 = did(df.assign(y=df["y"] + slope), **_DID_KW).iloc[0]
    assert row2["pre_trend_p"] < 0.01


def test_did_handles_missing_outcome_rows():
    df = _panel()
    df.loc[df.index[:5], "y"] = np.nan
    row = did(df, **_DID_KW).iloc[0]
    assert row["estimate"] == pytest.approx(2.0, abs=0.3)
    assert row["n_obs"] == len(df) - 5


def test_did_identification_guards():
    df = _panel()
    with pytest.raises(CausalError, match="control"):
        did(df.assign(treat=1), **_DID_KW)
    with pytest.raises(CausalError, match="post_col must vary"):
        did(df.assign(post=1), **_DID_KW)
    with pytest.raises(CausalError, match="constant"):
        did(df.assign(post=(df["treat"] == 0).astype(int)), **_DID_KW)
    with pytest.raises(CausalError, match="two clusters"):
        did(df.assign(unit="u0"), **_DID_KW)


def test_did_scratch_columns_do_not_collide_with_user_columns():
    df = _panel()
    base = did(df, **_DID_KW).iloc[0]
    clash = did(df.assign(_did=999.0, _period=-1.0, _treated_num="x"), **_DID_KW).iloc[0]
    assert clash["estimate"] == pytest.approx(base["estimate"])
    assert clash["pre_trend_p"] == pytest.approx(base["pre_trend_p"])


def test_did_accepts_non_identifier_column_names():
    df = _panel().rename(columns={"y": "test score", "unit": "school id"})
    row = did(
        df,
        outcome="test score",
        unit_col="school id",
        time_col="per",
        treated_col="treat",
        post_col="post",
    ).iloc[0]
    assert row["estimate"] == pytest.approx(2.0, abs=0.3)
