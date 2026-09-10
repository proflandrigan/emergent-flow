"""Regression tests for the 3-level MixedLM fix (issue #164 Gap 2 follow-up).

``nested_groups`` used to fit a 2-level model: statsmodels drops its default random
intercept when a ``vc_formula`` is present, so the top-level ``groups`` variance was
silently absorbed into the first nested component. Also covers the spec-gate hardening
that landed with the fix (NaN / duplicate-index / reserved-name / list-groups guards).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from emergentflow.stats import fit_model
from emergentflow.stats.errors import InvalidModelSpecError
from emergentflow.stats.spec import _prepare_model_spec


def _three_level_df(seed: int = 0) -> pd.DataFrame:
    """60 schools x 5 rooms x 10 pupils; true variances school 9, room 4, residual 1."""
    rng = np.random.default_rng(seed)
    rows = []
    for s in range(60):
        u_school = rng.normal(scale=3.0)
        for r in range(5):
            u_room = rng.normal(scale=2.0)
            for _ in range(10):
                x = rng.normal()
                rows.append(
                    {
                        "x": x,
                        "y": 1.0 + 0.5 * x + u_school + u_room + rng.normal(scale=1.0),
                        "school": f"s{s}",
                        "room": f"s{s}_r{r}",
                    }
                )
    return pd.DataFrame(rows)


_SPEC = {"target": "y", "fixed_effects": ["x"], "groups": "school", "nested_groups": ["room"]}


def test_nested_groups_keeps_top_level_variance():
    fitted = fit_model(_three_level_df(), model="MixedLM", spec=dict(_SPEC))
    assert fitted.results.k_re == 1  # the top-level intercept is present again
    shares = fitted.fit_stats["level_icc"]
    assert set(shares) == {"group", "room", "residual"}
    assert shares["group"] == pytest.approx(9 / 14, abs=0.1)
    assert shares["room"] == pytest.approx(4 / 14, abs=0.1)
    assert shares["residual"] == pytest.approx(1 / 14, abs=0.05)
    assert sum(shares.values()) == pytest.approx(1.0)
    assert fitted.fit_stats["icc"] == pytest.approx(shares["group"])
    terms = set(fitted.coefficients["term"])
    assert {"Group Var (Intercept)", "room Var", "Residual Var"} <= terms


def test_random_effects_and_nested_groups_combine():
    spec = {**_SPEC, "random_effects": ["x"]}
    fitted = fit_model(_three_level_df(), model="MixedLM", spec=spec)
    assert fitted.results.k_re == 2
    terms = set(fitted.coefficients["term"])
    assert "room Var" in terms
    assert "group" in fitted.fit_stats["level_icc"]


def test_nested_groups_rejects_missing_values():
    df = _three_level_df()
    df.loc[0, "room"] = None
    with pytest.raises(InvalidModelSpecError, match="missing values"):
        fit_model(df, model="MixedLM", spec=dict(_SPEC))


def test_mixedlm_rejects_duplicate_index():
    df = _three_level_df()
    df.index = np.zeros(len(df), dtype=int)
    with pytest.raises(InvalidModelSpecError, match="unique DataFrame index"):
        fit_model(df, model="MixedLM", spec=dict(_SPEC))


@pytest.mark.parametrize(
    ("nested", "match"),
    [
        (["room", "room"], "duplicates"),
        (["school"], "top-level groups"),
        (["residual"], "reserved"),
    ],
)
def test_nested_groups_validation(nested, match):
    df = _three_level_df()
    if nested == ["residual"]:
        df = df.rename(columns={"room": "residual"})
    with pytest.raises(InvalidModelSpecError, match=match):
        fit_model(df, model="MixedLM", spec={**_SPEC, "nested_groups": nested})


def test_mixedlm_rejects_list_groups_with_helpful_message():
    df = _three_level_df()
    with pytest.raises(InvalidModelSpecError, match="single column name"):
        fit_model(
            df,
            model="MixedLM",
            spec={"target": "y", "fixed_effects": ["x"], "groups": ["school", "room"]},
        )


def test_mixedlm_cov_type_gate_message():
    df = _three_level_df()
    with pytest.raises(InvalidModelSpecError, match="MixedLM does not support cov_type"):
        fit_model(df, model="MixedLM", spec={**_SPEC, "cov_type": "HC1"})
    # An explicit nonrobust is the statsmodels default and must be accepted.
    fitted = fit_model(df, model="MixedLM", spec={**_SPEC, "cov_type": "nonrobust"})
    assert fitted.model == "MixedLM"


def test_bayesian_priors_must_be_dict():
    df = _three_level_df()
    spec = {"target": "y", "seed": 1, "draws": 10, "tune": 10, "chains": 1, "priors": "tight"}
    with pytest.raises(InvalidModelSpecError, match="priors"):
        _prepare_model_spec(df, "BayesianGLM", spec)
