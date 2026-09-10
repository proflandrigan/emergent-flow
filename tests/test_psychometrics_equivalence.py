"""
ADR-0002 equivalence tests for the psychometrics node family (issue #164 Gap 3): running
the code from ``compile_to_code``/``preview`` (codegen path) must produce artifacts
equivalent to ``execute`` (the reference interpreter path), for every ``psychometrics.*``
node. The ``fit_irt`` test is gated on the optional ``girth`` dependency.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from emergentflow.nodes.examples import (
    PsychometricsDisattenuate,
    PsychometricsFitIrt,
    PsychometricsReliability,
)


def _run_codegen(definition, node, scope):
    frag = definition.preview(node)
    exec(frag.render(), scope)
    return scope


def _two_factor_items(n_subj: int = 100, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    true = rng.normal(size=n_subj)
    return pd.DataFrame({f"i{k}": true + rng.normal(scale=1.0, size=n_subj) for k in range(6)})


def test_reliability_node_equivalence():
    df = _two_factor_items()
    defn = PsychometricsReliability()
    node = defn.instantiate(item_cols=list(df.columns))
    executed = defn.execute(node, inputs={"frame": df.copy()})["result"]
    scope = _run_codegen(defn, node, {"frame": df.copy()})
    pd.testing.assert_frame_equal(executed, scope["result"])


def test_disattenuate_node_equivalence():
    defn = PsychometricsDisattenuate()
    node = defn.instantiate(r=0.42, reliability_x=0.9, reliability_y=0.8, n=200)
    executed = defn.execute(node, inputs={})["result"]
    scope = _run_codegen(defn, node, {})
    pd.testing.assert_frame_equal(executed, scope["result"])


def test_fit_irt_node_equivalence():
    pytest.importorskip("girth")
    rng = np.random.default_rng(4)
    n_items, n_subj = 15, 120
    theta = rng.normal(0, 1, n_subj)
    diff = np.linspace(-2, 2, n_items)
    p = 1 / (1 + np.exp(-(theta[None, :] - diff[:, None])))
    resp = (rng.random((n_items, n_subj)) < p).astype(int)
    long = pd.DataFrame(
        {
            "subject": np.repeat(np.arange(n_subj), n_items),
            "item": np.tile(np.arange(n_items), n_subj),
            "score": resp.T.ravel(),
        }
    )
    defn = PsychometricsFitIrt()
    node = defn.instantiate(subject_col="subject", item_col="item", score_col="score")
    executed = defn.execute(node, inputs={"responses": long.copy()})["result"]
    scope = _run_codegen(defn, node, {"responses": long.copy()})
    codegen_result = scope["result"]
    pd.testing.assert_frame_equal(executed.abilities, codegen_result.abilities)
    pd.testing.assert_frame_equal(executed.items, codegen_result.items)
    pd.testing.assert_frame_equal(executed.fit, codegen_result.fit)
