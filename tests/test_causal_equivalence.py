"""
ADR-0002 equivalence tests for the causal node family (issue #164 Gap 1): running the
code from ``compile_to_code``/``preview`` (codegen path) must produce artifacts
equivalent to ``execute`` (the reference interpreter path), for every ``causal.*`` node.

Follows the ``tests/test_timeseries_equivalence.py`` pattern: each node is instantiated,
executed directly, and its ``preview`` fragment exec'd in a scope with the same inputs;
the two results are then compared.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from emergentflow.nodes.examples import (
    CausalDid,
    CausalEstimateEffect,
    CausalFitPropensity,
    CausalSensitivity,
)


def _run_codegen(definition, node, scope):
    frag = definition.preview(node)
    exec(frag.render(), scope)
    return scope


def _confounded_df(n: int = 600, seed: int = 5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    x1 = rng.normal(0, 1, n)
    p = 1 / (1 + np.exp(-0.7 * x1))
    t = rng.binomial(1, p)
    y = 1.3 * t + 0.9 * x1 + rng.normal(0, 1, n)
    return pd.DataFrame({"x1": x1, "t": t, "y": y})


def _panel_df(seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n_units = 120
    periods = 4
    uid = np.repeat(np.arange(n_units), periods)
    per = np.tile(np.arange(periods), n_units)
    treated_unit = np.arange(n_units) % 2 == 0
    tu = treated_unit[uid]
    post = per >= 2
    y = (
        rng.normal(0, 1, n_units)[uid]
        + 0.5 * per
        + 2.0 * (tu & post)
        + rng.normal(0, 0.5, len(uid))
    )
    return pd.DataFrame(
        {
            "unit": uid.astype(str),
            "per": per.astype(str),
            "treat": tu.astype(int),
            "post": post.astype(int),
            "y": y,
        }
    )


def test_fit_propensity_equivalence():
    df = _confounded_df()
    defn = CausalFitPropensity()
    node = defn.instantiate(treatment="t", covariates=["x1"])
    executed = defn.execute(node, inputs={"frame": df.copy()})
    scope = _run_codegen(defn, node, {"frame": df.copy()})

    pd.testing.assert_frame_equal(executed["balance"], scope["balance"])
    # The result variable is the one scope key that is neither 'frame', 'balance', nor the
    # '__builtins__' dict exec injects.
    result_key = [
        k for k in scope if k not in ("frame", "balance", "__builtins__") and not k.startswith("ef")
    ]
    assert len(result_key) == 1
    codegen_result = scope[result_key[0]]
    pd.testing.assert_series_equal(executed["result"].weights, codegen_result.weights)


def test_estimate_effect_equivalence():
    df = _confounded_df()
    defn = CausalEstimateEffect()
    node = defn.instantiate(outcome="y", treatment="t", covariates=["x1"], method="aipw")
    executed = defn.execute(node, inputs={"frame": df.copy()})["result"]
    scope = _run_codegen(defn, node, {"frame": df.copy()})
    pd.testing.assert_frame_equal(executed, scope["result"])


def test_did_equivalence():
    df = _panel_df()
    defn = CausalDid()
    node = defn.instantiate(
        outcome="y", unit_col="unit", time_col="per", treated_col="treat", post_col="post"
    )
    executed = defn.execute(node, inputs={"frame": df.copy()})["result"]
    scope = _run_codegen(defn, node, {"frame": df.copy()})
    pd.testing.assert_frame_equal(executed, scope["result"])


def test_sensitivity_equivalence():
    df = _confounded_df()
    effect = CausalEstimateEffect().execute(
        CausalEstimateEffect().instantiate(
            outcome="y", treatment="t", covariates=["x1"], method="aipw"
        ),
        inputs={"frame": df.copy()},
    )["result"]
    defn = CausalSensitivity()
    node = defn.instantiate(method="e_value")
    executed = defn.execute(node, inputs={"effect": effect.copy()})["result"]
    scope = _run_codegen(defn, node, {"effect": effect.copy()})
    pd.testing.assert_frame_equal(executed, scope["result"])


def test_sensitivity_difference_scale_equivalence():
    df = _confounded_df()
    effect = CausalEstimateEffect().execute(
        CausalEstimateEffect().instantiate(
            outcome="y", treatment="t", covariates=["x1"], method="aipw"
        ),
        inputs={"frame": df.copy()},
    )["result"]
    defn = CausalSensitivity()
    node = defn.instantiate(method="e_value", scale="difference", sd=float(df["y"].std()))
    executed = defn.execute(node, inputs={"effect": effect.copy()})["result"]
    scope = _run_codegen(defn, node, {"effect": effect.copy()})
    pd.testing.assert_frame_equal(executed, scope["result"])


def test_sensitivity_rosenbaum_equivalence():
    rng = np.random.default_rng(5)
    pairs = pd.DataFrame({"o_t": rng.binomial(1, 0.6, 200), "o_c": rng.binomial(1, 0.3, 200)})
    defn = CausalSensitivity()
    node = defn.instantiate(
        method="rosenbaum", treated_outcome_col="o_t", control_outcome_col="o_c", gamma=1.5
    )
    executed = defn.execute(node, inputs={"matched": pairs.copy()})["result"]
    scope = _run_codegen(defn, node, {"matched": pairs.copy()})
    pd.testing.assert_frame_equal(executed, scope["result"])
    assert executed.iloc[0]["direction"] == "treated_higher"


def test_fit_propensity_empty_trim_is_equivalent_and_untrimmed():
    # ADR-0002: trim=[] means "no trimming" (None) on both paths; the compiled script used to fall
    # back to the op default (0.01, 0.99), so its max weight was 100 while execute's was unbounded.
    df = _confounded_df()
    defn = CausalFitPropensity()
    node = defn.instantiate(treatment="t", covariates=["x1"], trim=[])
    executed = defn.execute(node, inputs={"frame": df.copy()})
    scope = _run_codegen(defn, node, {"frame": df.copy()})
    result_key = [
        k for k in scope if k not in ("frame", "balance", "__builtins__") and not k.startswith("ef")
    ]
    codegen_result = scope[result_key[0]]
    pd.testing.assert_series_equal(executed["result"].weights, codegen_result.weights)
    trimmed = defn.execute(defn.instantiate(treatment="t", covariates=["x1"]), inputs={"frame": df})
    assert executed["result"].weights.max() >= trimmed["result"].weights.max()


def test_fit_propensity_params_reach_the_estimator():
    df = _confounded_df()
    defn = CausalFitPropensity()
    strong = defn.instantiate(treatment="t", covariates=["x1"], params={"C": 1e-3})
    default = defn.instantiate(treatment="t", covariates=["x1"])
    s = defn.execute(strong, inputs={"frame": df.copy()})["result"].scores
    d = defn.execute(default, inputs={"frame": df.copy()})["result"].scores
    assert s.std() < d.std()  # heavy regularisation flattens the scores
    scope = _run_codegen(defn, strong, {"frame": df.copy()})
    pd.testing.assert_frame_equal(
        defn.execute(strong, inputs={"frame": df.copy()})["balance"], scope["balance"]
    )


def test_estimate_effect_matching_caliper_and_seed_equivalence():
    df = _confounded_df(n=600)
    defn = CausalEstimateEffect()
    node = defn.instantiate(
        outcome="y",
        treatment="t",
        covariates=["x1"],
        method="matching",
        caliper=None,
        random_state=3,
    )
    executed = defn.execute(node, inputs={"frame": df.copy()})["result"]
    scope = _run_codegen(defn, node, {"frame": df.copy()})
    pd.testing.assert_frame_equal(executed, scope["result"])
    narrow = defn.instantiate(
        outcome="y", treatment="t", covariates=["x1"], method="matching", caliper=0.01
    )
    assert (
        defn.execute(narrow, inputs={"frame": df.copy()})["result"].iloc[0]["effective_n"]
        < executed.iloc[0]["effective_n"]
    )


def test_did_empty_cluster_col_is_equivalent():
    df = _panel_df()
    defn = CausalDid()
    node = defn.instantiate(
        outcome="y",
        unit_col="unit",
        time_col="per",
        treated_col="treat",
        post_col="post",
        cluster_col="",
    )
    executed = defn.execute(node, inputs={"frame": df.copy()})["result"]
    scope = _run_codegen(defn, node, {"frame": df.copy()})
    pd.testing.assert_frame_equal(executed, scope["result"])


def test_estimate_effect_node_dropdown_matches_registry_and_op():
    from emergentflow.causal import keys_for_archetype
    from emergentflow.causal.errors import UnknownMethodError

    method_spec = next(p for p in CausalEstimateEffect.params if p.name == "method")
    assert list(method_spec.hints.choices) == keys_for_archetype("estimate_effect")
    df = _confounded_df(n=200)
    with pytest.raises(UnknownMethodError):
        CausalEstimateEffect().execute(
            CausalEstimateEffect().instantiate(
                outcome="y", treatment="t", covariates=["x1"], method="tmle"
            ),
            inputs={"frame": df},
        )


def test_estimate_effect_absent_caliper_uses_declared_default():
    """A graph whose IR omits the ``caliper`` param must behave as the declared default 0.2
    (not as caliper=None/greedy matching) -- the node's ParamSpec default and the op's default
    agree, so absent == explicitly-0.2 (issue #164 follow-up)."""
    df = _confounded_df()
    defn = CausalEstimateEffect()
    absent = defn.instantiate(outcome="y", treatment="t", covariates=["x1"], method="matching")
    assert next(p.value for p in absent.params if p.name == "caliper") == 0.2  # declared default
    explicit = defn.instantiate(
        outcome="y", treatment="t", covariates=["x1"], method="matching", caliper=0.2
    )
    r_absent = defn.execute(absent, inputs={"frame": df.copy()})["result"]
    r_explicit = defn.execute(explicit, inputs={"frame": df.copy()})["result"]
    pd.testing.assert_frame_equal(r_absent, r_explicit)


def test_fit_propensity_absent_trim_uses_declared_default():
    """An absent ``trim`` param must fall back to the declared default (0.01, 0.99), not
    disable trimming -- absent == explicitly-[0.01, 0.99] (issue #164 follow-up)."""
    df = _confounded_df()
    defn = CausalFitPropensity()
    absent = defn.instantiate(treatment="t", covariates=["x1"])
    assert next(p.value for p in absent.params if p.name == "trim") == [0.01, 0.99]
    explicit = defn.instantiate(treatment="t", covariates=["x1"], trim=[0.01, 0.99])
    r_absent = defn.execute(absent, inputs={"frame": df.copy()})["result"]
    r_explicit = defn.execute(explicit, inputs={"frame": df.copy()})["result"]
    pd.testing.assert_series_equal(r_absent.weights, r_explicit.weights)
    pd.testing.assert_frame_equal(r_absent.balance, r_explicit.balance)


def test_sensitivity_sd_zero_fails_graph_validation():
    """causal.sensitivity sd=0.0 must fail node validation (the op requires sd > 0), not
    pass validation and crash at execute time (issue #164 follow-up)."""
    defn = CausalSensitivity()
    bad = defn.instantiate(sd=0.0, scale="difference")
    errors = defn.validate_node(bad)
    assert errors
    assert any("sd" in e for e in errors)
