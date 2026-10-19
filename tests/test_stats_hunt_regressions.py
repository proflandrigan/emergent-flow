"""Regression tests for bugs found in the stats bug hunt (NaN / missing-value handling)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import emergentflow as ef


@pytest.mark.parametrize("method", ["bonferroni", "benjamini_hochberg"])
def test_correct_pvalues_ignores_missing_pvalues(method: str) -> None:
    from statsmodels.stats.multitest import multipletests

    df = pd.DataFrame({"p_value": [0.01, np.nan, 0.04, 0.03]})
    out = ef.stats.correct_pvalues(df, method=method)
    sm_method = {"bonferroni": "bonferroni", "benjamini_hochberg": "fdr_bh"}[method]
    rej, adj, _, _ = multipletests([0.01, 0.04, 0.03], alpha=0.05, method=sm_method)
    observed = out["p_value"].notna().to_numpy()
    np.testing.assert_allclose(out.loc[observed, "p_adjusted"].to_numpy(), adj)
    assert out.loc[observed, "reject_null"].tolist() == rej.tolist()
    assert np.isnan(out.loc[~observed, "p_adjusted"]).all()
    assert not out.loc[~observed, "reject_null"].any()


def test_cohort_retention_skips_missing_user_or_date() -> None:
    df = pd.DataFrame(
        {
            "u": ["a", "a", "b", None, "c"],
            "d": ["2020-01-01", "2020-02-05", "2020-01-03", "2020-01-04", None],
        }
    )
    res = ef.stats.cohort_retention(df, user_col="u", date_col="d")
    expected = ef.stats.cohort_retention(df.dropna(), user_col="u", date_col="d")
    pd.testing.assert_frame_equal(res.tidy, expected.tidy)


@pytest.mark.parametrize(
    ("model", "extra"),
    [("OLS", {}), ("GLS", {}), ("WLS", {"weights": "w"}), ("GLM", {"family": "gaussian"})],
)
def test_cluster_cov_aligned_when_model_rows_have_missing_values(
    model: str, extra: dict[str, str]
) -> None:
    rng = np.random.default_rng(0)
    n = 60
    df = pd.DataFrame(
        {
            "y": rng.normal(size=n),
            "x": rng.normal(size=n),
            "g": np.repeat(np.arange(12), 5),
            "w": rng.uniform(1, 2, n),
        }
    )
    df.loc[3, "x"] = np.nan
    spec = {
        "target": "y",
        "fixed_effects": ["x"],
        "cov_type": "cluster",
        "cov_group": "g",
        **extra,
    }
    got = ef.stats.fit_model(df, model=model, spec=spec)
    want = ef.stats.fit_model(df.dropna(), model=model, spec=spec)
    np.testing.assert_allclose(
        got.coefficients["std_err"].to_numpy(), want.coefficients["std_err"].to_numpy()
    )
