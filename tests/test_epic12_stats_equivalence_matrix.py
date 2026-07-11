"""
Epic 12 Story 10 -- unified stats-model ADR-0002 equivalence matrix, computed dynamically from
the ``emergentflow.stats.registry`` model catalog.

Mirrors ``tests/test_ml_equivalence_matrix.py``'s shape (Epic 8 Story 9): rather than each story
shipping its own hand-picked equivalence test (OLS/WLS/GLS/GLM in
``test_stats_regression_catalog.py``, MixedLM in ``test_stats_mixedlm_catalog.py``, GAM in
``test_stats_gam_catalog.py``, BayesianGLM in ``test_stats_bayesian_catalog.py`` -- none of which
are modified here), this file iterates ``keys_for_archetype("fit_model")`` and
``keys_for_archetype("bayesian_fit")`` directly, so a newly curated model is automatically pulled
into the equivalence gate -- and the matrix fails loudly at test time if nobody has supplied a
compatible fixture for it yet.

Each registry model key is fit through its OWN dedicated node (``FitLinearRegression``/
``FitGLM``/``FitMixedModel``/``FitGAM``/``FitBayesianModel`` -- the generic catch-all
``FitModel`` node was retired once every family had a dedicated node), via the
``_NODE_FOR_MODEL_KEY`` lookup table below. Fixtures are copied verbatim (same seeds, same
column names) from the per-story test files so the underlying fits converge identically; only
the fixture *dispatch* (a dict keyed by the registry's own model keys, resolving to a node class
+ that node's own param names) is new.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import pytest

from emergentflow.nodes.examples import (
    FitGAM,
    FitGLM,
    FitLinearRegression,
    FitMixedModel,
)
from emergentflow.stats.registry import keys_for_archetype


def _run_codegen(definition, node, scope):
    """exec a node's preview fragment in *scope* and return the updated scope."""
    frag = definition.preview(node)
    exec(frag.render(), scope)  # noqa: S102 -- test-only, on our own emitted code
    return scope


# ---------------------------------------------------------------------------
# Fixtures -- copied verbatim from the per-story equivalence tests (see module docstring).
# ---------------------------------------------------------------------------


def _regression_df(seed: int = 0) -> pd.DataFrame:
    """OLS/GLS/WLS/GLM fixture -- copied from tests/test_stats_regression_catalog.py."""
    rng = np.random.default_rng(seed)
    n = 60
    x1 = rng.normal(size=n)
    x2 = rng.normal(size=n)
    y = 2.0 * x1 + 3.0 * x2 + 1.0 + rng.normal(scale=0.1, size=n)
    w = np.abs(rng.normal(size=n)) + 0.1
    df = pd.DataFrame({"x1": x1, "x2": x2, "y": y, "w": w})
    p = 1.0 / (1.0 + np.exp(-(2.0 * x1)))
    label = (rng.random(n) < p).astype(float)
    return df.assign(label=label)


def _grouped_df(seed: int = 0) -> pd.DataFrame:
    """MixedLM fixture -- copied from tests/test_stats_mixedlm_catalog.py's ``_grouped_df``."""
    rng = np.random.default_rng(seed)
    rows = []
    for g in range(6):
        intercept = g * 4.0
        slope = 2.0 + rng.normal(scale=1.0)
        for _ in range(10):
            x = rng.normal()
            y = intercept + slope * x + rng.normal(scale=0.5)
            rows.append({"x": x, "y": y, "grp": f"g{g}"})
    return pd.DataFrame(rows)


def _gam_df(seed: int = 0) -> pd.DataFrame:
    """GAM fixture -- copied from tests/test_stats_gam_catalog.py's ``_gam_df``."""
    rng = np.random.default_rng(seed)
    n = 200
    x1 = rng.normal(size=n)
    x2 = rng.uniform(-3, 3, size=n)
    y = 1.0 + 2.0 * x1 + np.sin(x2) + rng.normal(scale=0.2, size=n)
    return pd.DataFrame({"x1": x1, "x2": x2, "y": y})


#: model_key -> the dedicated node class that fits it.
_NODE_FOR_MODEL_KEY: dict[str, type] = {
    "OLS": FitLinearRegression,
    "WLS": FitLinearRegression,
    "GLS": FitLinearRegression,
    "GLM": FitGLM,
    "MixedLM": FitMixedModel,
    "GAM": FitGAM,
}

#: model_key -> (df, fit_kwargs), where fit_kwargs are the DEDICATED node's own param names
#: (no ``model``/``spec_extra`` catch-all). A registry key with no entry here fails the matrix
#: loudly (see ``test_fit_model_equivalence_matrix``) instead of silently being skipped.
_FIXTURES: dict[str, tuple[pd.DataFrame, dict[str, Any]]] = {
    "OLS": (_regression_df(), {"estimator": "OLS", "target": "y", "fixed_effects": ["x1", "x2"]}),
    "GLS": (_regression_df(), {"estimator": "GLS", "target": "y", "fixed_effects": ["x1", "x2"]}),
    "WLS": (
        _regression_df(),
        {"estimator": "WLS", "target": "y", "fixed_effects": ["x1", "x2"], "weights": "w"},
    ),
    "GLM": (
        _regression_df(),
        {"target": "label", "fixed_effects": ["x1"], "family": "binomial"},
    ),
    "MixedLM": (
        _grouped_df(),
        {
            "target": "y",
            "fixed_effects": ["x"],
            "random_effects": ["x"],
            "groups": "grp",
        },
    ),
    "GAM": (
        _gam_df(),
        {
            "target": "y",
            "linear_terms": ["x1"],
            "smooth_terms": [{"column": "x2", "df": 6, "degree": 3}],
        },
    ),
}


# ---------------------------------------------------------------------------
# The matrix: one equivalence assertion per fit_model-archetype key, dynamically discovered.
# ---------------------------------------------------------------------------


@pytest.mark.equivalence
@pytest.mark.parametrize("model_key", keys_for_archetype("fit_model"))
def test_fit_model_equivalence_matrix(model_key: str) -> None:
    """ADR 0002: execute() == running the emitted code, for every fit_model-archetype key."""
    assert model_key in _FIXTURES, f"no equivalence fixture for {model_key}"
    assert model_key in _NODE_FOR_MODEL_KEY, f"no dedicated node mapped for {model_key}"
    df, fit_kwargs = _FIXTURES[model_key]
    node_cls = _NODE_FOR_MODEL_KEY[model_key]

    defn = node_cls()
    node = defn.instantiate(**fit_kwargs)
    executed_model = defn.execute(node, inputs={"frame": df.copy()})["model"]
    scope = _run_codegen(defn, node, {"frame": df.copy()})
    codegen_model = scope["model"]

    pd.testing.assert_frame_equal(executed_model.coefficients, codegen_model.coefficients)
    assert executed_model.fit_stats == codegen_model.fit_stats
    assert executed_model.model == codegen_model.model == model_key


# ---------------------------------------------------------------------------
# Bayesian (bayesian_fit archetype) -- separate, importorskip-guarded so this file (and the
# fit_model matrix above) still runs in the default lane where bambi/pymc/arviz are absent.
# ---------------------------------------------------------------------------

_MCMC_KWARGS = {"seed": 0, "draws": 50, "tune": 50, "chains": 2}


def _bayesian_plain_df(seed: int = 0) -> pd.DataFrame:
    """Copied from tests/test_stats_bayesian_catalog.py's ``_plain_df``."""
    rng = np.random.default_rng(seed)
    n = 60
    x = rng.normal(size=n)
    y = 2.0 * x + 1.0 + rng.normal(scale=0.3, size=n)
    return pd.DataFrame({"x": x, "y": y})


_BAYESIAN_FIXTURES: dict[str, tuple[pd.DataFrame, dict[str, Any]]] = {
    "BayesianGLM": (
        _bayesian_plain_df(),
        {"target": "y", "fixed_effects": ["x"], **_MCMC_KWARGS},
    ),
}


@pytest.mark.equivalence
@pytest.mark.parametrize("model_key", keys_for_archetype("bayesian_fit"))
def test_bayesian_fit_equivalence_matrix(model_key: str) -> None:
    """ADR 0002: execute() == running the emitted code, for every bayesian_fit-archetype key."""
    pytest.importorskip("bambi")
    pytest.importorskip("pymc")
    pytest.importorskip("arviz")

    from emergentflow.nodes.examples import FitBayesianModel

    assert model_key in _BAYESIAN_FIXTURES, f"no equivalence fixture for {model_key}"
    assert model_key == "BayesianGLM", f"no dedicated node mapped for {model_key}"
    df, fit_kwargs = _BAYESIAN_FIXTURES[model_key]

    defn = FitBayesianModel()
    node = defn.instantiate(**fit_kwargs)
    executed_model = defn.execute(node, inputs={"frame": df.copy()})["model"]
    scope = _run_codegen(defn, node, {"frame": df.copy()})
    codegen_model = scope["model"]

    pd.testing.assert_frame_equal(executed_model.coefficients, codegen_model.coefficients)
    assert executed_model.fit_stats == codegen_model.fit_stats
    assert executed_model.model == codegen_model.model == model_key
