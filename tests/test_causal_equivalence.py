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
