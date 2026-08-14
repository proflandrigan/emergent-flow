"""
emergentflow.stats
~~~~~~~~~~~~~~~~~
Statistical-analytics operations (Epic 1, Story 8).

Thin wrappers over statsmodels, a BSD-3-Clause library chosen as the statistics
backend because its results are returned as clean, tidy ``DataFrame``s (e.g.
``anova_lm``) rather than opaque result objects (see
``docs/sdk-design-philosophy.md``). Each public operation validates its inputs
at the boundary (fail fast, clear typed errors) and otherwise defers entirely to
the underlying, trusted library — no reimplementation, no hidden transformation.

See ``docs/public-api-conventions.md`` and ``docs/sdk-design-philosophy.md``.
"""

from __future__ import annotations

import importlib.util
import math
from dataclasses import dataclass
from typing import Any

import pandas as pd
import statsmodels.api as sm
from scipy import optimize
from scipy.stats import (
    chi2_contingency,
    fisher_exact,
    mannwhitneyu,
    ncf,
    norm,
    ttest_ind,
)
from scipy.stats import (
    kruskal as scipy_kruskal,
)
from scipy.stats import (
    wilcoxon as scipy_wilcoxon,
)
from statsmodels.formula.api import ols
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.power import TTestIndPower
from statsmodels.stats.proportion import confint_proportions_2indep, proportions_ztest

from emergentflow.api import public_op
from emergentflow.stats.diagnostics import DiagnosticSpec, known_diagnostic_keys
from emergentflow.stats.eda import (
    AutoEdaResult,
    auto_eda,
    co_missingness,
    data_dictionary,
    distribution_summary,
    group_by_aggregate,
    missingness,
    outlier_summary,
    profile,
)
from emergentflow.stats.errors import (
    InvalidModelSpecError,
    MissingOptionalDependencyError,
    StatsError,
    StatsScaleError,
    UnknownDiagnosticError,
    UnknownModelError,
)
from emergentflow.stats.models import FittedStatsModel
from emergentflow.stats.registry import ModelSpec, keys_for_archetype, known_model_keys
from emergentflow.stats.scale import enforce_dense_square_guard
from emergentflow.stats.spec import _prepare_diagnostic_spec, _prepare_model_spec

__all__ = [
    "anova",
    "AnovaResult",
    "auto_eda",
    "AutoEdaResult",
    "chi_square",
    "co_missingness",
    "cohort_retention",
    "CohortRetentionResult",
    "correct_pvalues",
    "correlation",
    "CORR_METHODS",
    "crosstab",
    "CrosstabResult",
    "data_dictionary",
    "describe",
    "diagnostic",
    "DiagnosticSpec",
    "distribution_summary",
    "funnel",
    "group_by_aggregate",
    "kruskal",
    "mann_whitney",
    "missingness",
    "outlier_summary",
    "power_analysis",
    "profile",
    "test_proportions",
    "ttest",
    "TTestResult",
    "wilcoxon",
    "FittedStatsModel",
    "ModelSpec",
    "StatsError",
    "UnknownDiagnosticError",
    "UnknownModelError",
    "InvalidModelSpecError",
    "MissingOptionalDependencyError",
    "StatsScaleError",
    "known_diagnostic_keys",
    "known_model_keys",
    "keys_for_archetype",
    "fit_model",
]

CORR_METHODS = ("pearson", "spearman", "kendall")


@dataclass
class AnovaResult:
    """Structured, inspectable result of a one-way ANOVA.

    Attributes
    ----------
    f_statistic: the ANOVA F value.
    p_value: the uncorrected p-value.
    effect_size: partial eta-squared.
    summary: statsmodels' full tidy ANOVA result table.
    ci_low, ci_high: confidence interval on effect_size (partial eta-squared),
        computed via the noncentral-F method (Steiger, 2004).
    """

    f_statistic: float
    p_value: float
    effect_size: float
    summary: pd.DataFrame
    ci_low: float
    ci_high: float


@dataclass
class TTestResult:
    """Structured, inspectable result of a two-sample t-test.

    Fields: t_statistic, p_value, df (degrees of freedom), group_a/group_b (the two group labels,
    sorted), n_a/n_b (per-group sizes), mean_a/mean_b (per-group means), equal_var (whether a
    Student's t-test was used vs Welch's), alpha (the caller-supplied significance threshold),
    effect_size (Cohen's d), ci_low/ci_high (confidence interval on Cohen's d at the given alpha).
    """

    t_statistic: float
    p_value: float
    df: float
    group_a: str
    group_b: str
    n_a: int
    n_b: int
    mean_a: float
    mean_b: float
    equal_var: bool
    alpha: float
    effect_size: float
    ci_low: float
    ci_high: float


@public_op(name="ef.stats.ttest")
def ttest(
    df: pd.DataFrame,
    *,
    group_col: str,
    value_col: str,
    equal_var: bool = True,
    alpha: float = 0.05,
) -> TTestResult:
    """Two-sample t-test of ``value_col`` between the two groups in ``group_col``.

    Thin wrapper over ``scipy.stats.ttest_ind``. ``group_col`` must contain EXACTLY two distinct
    groups. ``equal_var=True`` runs Student's t-test; ``False`` runs Welch's. ``alpha`` is recorded
    for callers but does not change the computation (the raw p-value is reported). Deterministic.
    """
    if group_col not in df.columns:
        raise ValueError(f"unknown group_col {group_col!r}; expected one of {list(df.columns)!r}.")
    if value_col not in df.columns:
        raise ValueError(f"unknown value_col {value_col!r}; expected one of {list(df.columns)!r}.")
    if group_col == value_col:
        raise ValueError(f"group_col and value_col must differ; both were {group_col!r}.")
    groups = sorted(str(g) for g in df[group_col].dropna().unique())
    if len(groups) != 2:
        raise ValueError(
            f"two-sample t-test needs exactly 2 distinct groups in {group_col!r}; "
            f"found {len(groups)}."
        )
    a_label, b_label = groups[0], groups[1]
    # Drop NaN value rows so n_a/n_b, means, variances, and scipy's ttest all operate on the
    # same consistent subset (scipy and pandas mean/var drop NaN, so counting them inflated
    # the reported sample sizes and the pooled-variance weight).
    a = df.loc[df[group_col].astype(str) == a_label, value_col].dropna()
    b = df.loc[df[group_col].astype(str) == b_label, value_col].dropna()
    res = ttest_ind(a, b, equal_var=equal_var)
    n_a_count = int(a.shape[0])
    n_b_count = int(b.shape[0])
    var_a = float(a.var(ddof=1))
    var_b = float(b.var(ddof=1))
    pooled_sd = (
        ((n_a_count - 1) * var_a + (n_b_count - 1) * var_b) / (n_a_count + n_b_count - 2)
    ) ** 0.5
    cohens_d = (float(a.mean()) - float(b.mean())) / pooled_sd if pooled_sd > 0 else float("nan")
    se_d = (
        (n_a_count + n_b_count) / (n_a_count * n_b_count)
        + cohens_d**2 / (2 * (n_a_count + n_b_count - 2))
    ) ** 0.5
    z_crit = float(norm.ppf(1 - alpha / 2))
    ci_low = cohens_d - z_crit * se_d
    ci_high = cohens_d + z_crit * se_d
    return TTestResult(
        t_statistic=float(res.statistic),
        p_value=float(res.pvalue),
        df=float(res.df),
        group_a=a_label,
        group_b=b_label,
        n_a=int(a.shape[0]),
        n_b=int(b.shape[0]),
        mean_a=float(a.mean()),
        mean_b=float(b.mean()),
        equal_var=bool(equal_var),
        alpha=float(alpha),
        effect_size=cohens_d,
        ci_low=ci_low,
        ci_high=ci_high,
    )


def _partial_eta_sq_ci(f_stat: float, df1: float, df2: float, alpha: float) -> tuple[float, float]:
    """Noncentral-F confidence interval for partial eta-squared (Steiger, 2004).

    Solves for the noncentrality parameter ``lambda`` such that the noncentral F CDF at the
    observed F statistic equals each target tail probability, then converts ``lambda`` to
    partial eta-squared via ``eta_sq = lambda / (lambda + df1 + df2 + 1)``. Deterministic
    (root-finding on a fixed function, no randomness).
    """

    def _lambda_for_percentile(percentile: float) -> float:
        def objective(lam: float) -> float:
            return float(ncf.cdf(f_stat, df1, df2, lam)) - percentile

        if objective(0.0) < 0.0:
            return 0.0
        hi = 1.0
        while objective(hi) > 0.0:
            hi *= 2
            if hi > 1e7:
                return 0.0
        return float(optimize.brentq(objective, 0.0, hi))

    lambda_low = _lambda_for_percentile(1 - alpha / 2)
    lambda_high = _lambda_for_percentile(alpha / 2)
    eta_low = lambda_low / (lambda_low + df1 + df2 + 1)
    eta_high = lambda_high / (lambda_high + df1 + df2 + 1)
    return eta_low, eta_high


@public_op(name="ef.stats.anova")
def anova(
    df: pd.DataFrame,
    *,
    group_col: str,
    value_col: str,
    alpha: float = 0.05,
) -> AnovaResult:
    """Perform a one-way ANOVA of ``value_col`` across groups in ``group_col``.

    Thin wrapper over ``statsmodels`` (OLS + ``anova_lm``). ``alpha`` is recorded
    for callers but does not change the computation (the raw p-value is reported).
    """
    if group_col not in df.columns:
        raise ValueError(f"unknown group_col {group_col!r}; expected one of {list(df.columns)!r}.")
    if value_col not in df.columns:
        raise ValueError(f"unknown value_col {value_col!r}; expected one of {list(df.columns)!r}.")
    if group_col == value_col:
        raise ValueError(f"group_col and value_col must differ; both were {group_col!r}.")
    n_groups = int(df[group_col].nunique())
    if n_groups < 2:
        raise ValueError(
            f"one-way ANOVA needs at least 2 distinct groups in {group_col!r}; found {n_groups}."
        )

    # Rename to fixed, safe tokens so arbitrary column names (spaces, dots,
    # reserved words) cannot break the patsy/statsmodels formula parser.
    work = df[[group_col, value_col]].rename(columns={value_col: "_dv", group_col: "_grp"})
    model = ols("_dv ~ C(_grp)", data=work).fit()
    table = sm.stats.anova_lm(model, typ=2)

    effect = table.loc["C(_grp)"]
    effect_ss = float(effect["sum_sq"])
    resid_ss = float(table.loc["Residual", "sum_sq"])
    partial_eta_sq = effect_ss / (effect_ss + resid_ss)

    df1 = float(effect["df"])
    df2 = float(table.loc["Residual", "df"])
    ci_low, ci_high = _partial_eta_sq_ci(float(effect["F"]), df1, df2, alpha)

    return AnovaResult(
        f_statistic=float(effect["F"]),
        p_value=float(effect["PR(>F)"]),
        effect_size=partial_eta_sq,
        summary=table,
        ci_low=ci_low,
        ci_high=ci_high,
    )


@public_op(name="ef.stats.mann_whitney")
def mann_whitney(
    df: pd.DataFrame,
    *,
    group_col: str,
    value_col: str,
    alternative: str = "two-sided",
) -> pd.DataFrame:
    """Mann-Whitney U rank-sum test between two groups.

    Thin wrapper over ``scipy.stats.mannwhitneyu``. ``group_col`` must contain exactly two
    groups. Effect size is the rank-biserial correlation ``r = (2*U) / (n_a*n_b) - 1``, where
    ``U`` is the U statistic for group_a (positive means group_a is stochastically greater than
    group_b, matching the sign convention used by ``ttest``'s Cohen's d). Deterministic.
    """
    if group_col not in df.columns:
        raise ValueError(f"unknown group_col {group_col!r}; expected one of {list(df.columns)!r}.")
    if value_col not in df.columns:
        raise ValueError(f"unknown value_col {value_col!r}; expected one of {list(df.columns)!r}.")
    if group_col == value_col:
        raise ValueError(f"group_col and value_col must differ; both were {group_col!r}.")
    groups = sorted(str(g) for g in df[group_col].dropna().unique())
    if len(groups) != 2:
        raise ValueError(
            f"Mann-Whitney U test needs exactly 2 distinct groups in {group_col!r}; "
            f"found {len(groups)}."
        )
    if alternative not in ("two-sided", "less", "greater"):
        raise ValueError(
            f"unknown alternative {alternative!r}; expected 'two-sided', 'less', or 'greater'."
        )
    a_label, b_label = groups[0], groups[1]
    # Drop NaN value rows so n_a/n_b and the rank-biserial denominator operate on the
    # same consistent subset scipy uses internally (scipy strips NaN, so counting them
    # inflated the reported sample sizes and the effect-size denominator). Mirrors the
    # dropna already applied in `ttest` for the same case.
    a = df.loc[df[group_col].astype(str) == a_label, value_col].dropna()
    b = df.loc[df[group_col].astype(str) == b_label, value_col].dropna()
    n_a, n_b = int(a.shape[0]), int(b.shape[0])
    res = mannwhitneyu(a, b, alternative=alternative)
    u_stat = float(res.statistic)
    effect_size = (2.0 * u_stat) / (n_a * n_b) - 1.0 if n_a * n_b > 0 else float("nan")
    return pd.DataFrame(
        [
            {
                "statistic": u_stat,
                "p_value": float(res.pvalue),
                "effect_size": effect_size,
                "group_a": a_label,
                "group_b": b_label,
                "n_a": n_a,
                "n_b": n_b,
                "alternative": alternative,
            }
        ]
    )


@public_op(name="ef.stats.wilcoxon")
def wilcoxon(
    df: pd.DataFrame,
    *,
    col_a: str,
    col_b: str,
    alternative: str = "two-sided",
) -> pd.DataFrame:
    """Wilcoxon signed-rank test for paired samples in two columns.

    Thin wrapper over ``scipy.stats.wilcoxon``. ``col_a`` and ``col_b`` are two numeric columns
    of the same DataFrame, row-paired. Rows with NaN in either column are dropped (paired
    dropna). Deterministic.
    """
    if col_a not in df.columns:
        raise ValueError(f"unknown col_a {col_a!r}; expected one of {list(df.columns)!r}.")
    if col_b not in df.columns:
        raise ValueError(f"unknown col_b {col_b!r}; expected one of {list(df.columns)!r}.")
    if col_a == col_b:
        raise ValueError(f"col_a and col_b must differ; both were {col_a!r}.")
    if alternative not in ("two-sided", "less", "greater"):
        raise ValueError(
            f"unknown alternative {alternative!r}; expected 'two-sided', 'less', or 'greater'."
        )
    paired = df[[col_a, col_b]].dropna()
    n = int(paired.shape[0])
    if n == 0:
        raise ValueError(
            f"wilcoxon needs at least 1 complete pair in {col_a!r}/{col_b!r} after dropping "
            f"missing values."
        )
    res = scipy_wilcoxon(paired[col_a], paired[col_b], alternative=alternative)
    return pd.DataFrame(
        [
            {
                "statistic": float(res.statistic),
                "p_value": float(res.pvalue),
                "n": n,
                "alternative": alternative,
            }
        ]
    )


@public_op(name="ef.stats.kruskal")
def kruskal(
    df: pd.DataFrame,
    *,
    group_col: str,
    value_col: str,
) -> pd.DataFrame:
    """Kruskal-Wallis H-test across two or more groups.

    Thin wrapper over ``scipy.stats.kruskal``. ``group_col`` must contain at least two distinct
    groups. Effect size is epsilon-squared. Deterministic.
    """
    if group_col not in df.columns:
        raise ValueError(f"unknown group_col {group_col!r}; expected one of {list(df.columns)!r}.")
    if value_col not in df.columns:
        raise ValueError(f"unknown value_col {value_col!r}; expected one of {list(df.columns)!r}.")
    if group_col == value_col:
        raise ValueError(f"group_col and value_col must differ; both were {group_col!r}.")
    n_groups = int(df[group_col].nunique())
    if n_groups < 2:
        raise ValueError(
            f"Kruskal-Wallis needs at least 2 distinct groups in {group_col!r}; found {n_groups}."
        )
    samples = [g[value_col].dropna().to_numpy() for _, g in df.groupby(group_col, sort=True)]
    n_total = int(sum(len(s) for s in samples))
    res = scipy_kruskal(*samples)
    h_stat = float(res.statistic)
    df_stat = n_groups - 1
    effect_size = (
        (h_stat - df_stat) / (n_total - n_groups) if (n_total - n_groups) > 0 else float("nan")
    )
    return pd.DataFrame(
        [
            {
                "statistic": h_stat,
                "p_value": float(res.pvalue),
                "df": df_stat,
                "effect_size": effect_size,
                "n_groups": n_groups,
            }
        ]
    )


@public_op(name="ef.stats.chi_square")
def chi_square(
    df: pd.DataFrame,
    *,
    row_col: str,
    col_col: str,
    correction: bool = True,
) -> pd.DataFrame:
    """Chi-square test of independence on a contingency table.

    Thin wrapper over ``scipy.stats.chi2_contingency``. When the table is exactly 2x2, also
    computes Fisher's exact test and includes its p-value and odds ratio as extra columns.
    Effect size is Cramer's V. Deterministic.
    """
    if row_col not in df.columns:
        raise ValueError(f"unknown row_col {row_col!r}; expected one of {list(df.columns)!r}.")
    if col_col not in df.columns:
        raise ValueError(f"unknown col_col {col_col!r}; expected one of {list(df.columns)!r}.")
    if row_col == col_col:
        raise ValueError(f"row_col and col_col must differ; both were {row_col!r}.")
    table = pd.crosstab(df[row_col], df[col_col])
    if table.shape[0] < 2 or table.shape[1] < 2:
        raise ValueError(
            f"chi-square needs at least a 2x2 contingency table; got shape {table.shape} "
            f"from {row_col!r} x {col_col!r}."
        )
    chi2, p, dof, _expected = chi2_contingency(table.to_numpy(), correction=correction)
    n = int(table.to_numpy().sum())
    min_dim = min(table.shape[0], table.shape[1])
    cramers_v = (
        float((chi2 / (n * (min_dim - 1))) ** 0.5) if n > 0 and min_dim > 1 else float("nan")
    )
    fisher_p: float | None = None
    fisher_odds_ratio: float | None = None
    if table.shape == (2, 2):
        odds_ratio, fp = fisher_exact(table.to_numpy())
        fisher_odds_ratio = float(odds_ratio)
        fisher_p = float(fp)
    return pd.DataFrame(
        [
            {
                "statistic": float(chi2),
                "p_value": float(p),
                "df": int(dof),
                "effect_size": cramers_v,
                "n": n,
                "fisher_p": fisher_p,
                "fisher_odds_ratio": fisher_odds_ratio,
            }
        ]
    )


_CORRECTION_METHODS = {"bonferroni": "bonferroni", "benjamini_hochberg": "fdr_bh"}


@public_op(name="ef.stats.correct_pvalues")
def correct_pvalues(
    df: pd.DataFrame,
    *,
    p_col: str = "p_value",
    method: str = "bonferroni",
    alpha: float = 0.05,
) -> pd.DataFrame:
    """Apply a multiple-comparison correction to a DataFrame's p-value column.

    Thin wrapper over ``statsmodels.stats.multitest.multipletests``. ``method`` is
    ``"bonferroni"`` or ``"benjamini_hochberg"`` (Benjamini-Hochberg FDR control). Returns a COPY
    of ``df`` with two new columns: ``p_adjusted`` (the corrected p-values) and ``reject_null``
    (bool, whether each adjusted p-value is below ``alpha``). Never mutates ``df``. Raises a
    typed ``ColumnCollisionError``-style ``ValueError`` if ``p_adjusted`` or ``reject_null``
    already exist as columns in ``df`` (mirrors the ``emergentflow/clean/`` overwrite-guard
    discipline used elsewhere in this repo).
    """
    if p_col not in df.columns:
        raise ValueError(f"unknown p_col {p_col!r}; expected one of {list(df.columns)!r}.")
    if method not in _CORRECTION_METHODS:
        raise ValueError(
            f"unknown method {method!r}; expected one of {list(_CORRECTION_METHODS)!r}."
        )
    collisions = [c for c in ("p_adjusted", "reject_null") if c in df.columns]
    if collisions:
        raise ValueError(
            f"correct_pvalues would overwrite existing column(s) {collisions!r}; "
            f"rename them before calling."
        )
    pvals = df[p_col].to_numpy()
    reject, p_adjusted, _, _ = multipletests(pvals, alpha=alpha, method=_CORRECTION_METHODS[method])
    result = df.copy()
    result["p_adjusted"] = p_adjusted
    result["reject_null"] = reject
    return result


@public_op(name="ef.stats.test_proportions")
def test_proportions(
    df: pd.DataFrame,
    *,
    group_col: str,
    success_col: str,
    alpha: float = 0.05,
) -> pd.DataFrame:
    """Two-proportion z-test between two groups, with CI on the difference and relative uplift.

    Thin wrapper over ``statsmodels.stats.proportion.proportions_ztest`` (test statistic/p-value)
    and ``confint_proportions_2indep`` (CI). ``group_col`` must contain exactly 2 distinct groups
    (sorted labels group_a < group_b); ``success_col`` must be a binary 0/1/True/False column.
    ``statistic``/``diff``/``ci_low``/``ci_high``/``relative_uplift`` are all expressed as GROUP B
    RELATIVE TO GROUP A (``p_b - p_a``), so a positive ``diff`` (and a positive ``statistic``)
    means group_b's rate is higher. Deterministic.
    """
    if group_col not in df.columns:
        raise ValueError(f"unknown group_col {group_col!r}; expected one of {list(df.columns)!r}.")
    if success_col not in df.columns:
        raise ValueError(
            f"unknown success_col {success_col!r}; expected one of {list(df.columns)!r}."
        )
    if group_col == success_col:
        raise ValueError(f"group_col and success_col must differ; both were {group_col!r}.")
    groups = sorted(str(g) for g in df[group_col].dropna().unique())
    if len(groups) != 2:
        raise ValueError(
            f"two-proportion z-test needs exactly 2 distinct groups in {group_col!r}; "
            f"found {len(groups)}."
        )
    if not df[success_col].dropna().isin([0, 1, True, False]).all():
        raise ValueError(f"success_col {success_col!r} must contain only 0/1/True/False values.")
    a_label, b_label = groups[0], groups[1]
    a = df.loc[df[group_col].astype(str) == a_label, success_col].dropna()
    b = df.loc[df[group_col].astype(str) == b_label, success_col].dropna()
    n_a, n_b = int(a.shape[0]), int(b.shape[0])
    count_a, count_b = int(a.sum()), int(b.sum())
    p_a = count_a / n_a if n_a > 0 else float("nan")
    p_b = count_b / n_b if n_b > 0 else float("nan")
    stat, p_value = proportions_ztest([count_b, count_a], [n_b, n_a])
    ci_low, ci_high = confint_proportions_2indep(
        count_b, n_b, count_a, n_a, compare="diff", alpha=alpha
    )
    diff = p_b - p_a
    relative_uplift = diff / p_a if not (p_a == 0 or math.isnan(p_a)) else float("nan")
    return pd.DataFrame(
        [
            {
                "statistic": float(stat),
                "p_value": float(p_value),
                "group_a": a_label,
                "group_b": b_label,
                "n_a": n_a,
                "n_b": n_b,
                "p_a": p_a,
                "p_b": p_b,
                "diff": diff,
                "ci_low": float(ci_low),
                "ci_high": float(ci_high),
                "relative_uplift": relative_uplift,
                "alpha": float(alpha),
            }
        ]
    )


@public_op(name="ef.stats.power_analysis")
def power_analysis(
    *,
    effect_size: float | None = None,
    nobs: float | None = None,
    alpha: float = 0.05,
    power: float | None = None,
    ratio: float = 1.0,
    alternative: str = "two-sided",
) -> pd.DataFrame:
    """Solve a two-independent-sample t-test power equation for the one unset quantity.

    Thin wrapper over ``statsmodels.stats.power.TTestIndPower.solve_power``. Exactly one of
    ``effect_size`` (MDE), ``nobs`` (sample size per group), or ``power`` (achieved power) must
    be ``None`` -- that is the quantity solved for; the other two (plus ``alpha``) must be given.
    ``alternative`` is ``"two-sided"``, ``"larger"``, or ``"smaller"``. Deterministic.
    """
    unset = [
        name
        for name, val in (("effect_size", effect_size), ("nobs", nobs), ("power", power))
        if val is None
    ]
    if len(unset) != 1:
        raise ValueError(
            "power_analysis needs exactly one of effect_size, nobs, power left unset (None) "
            f"to solve for; found {len(unset)} unset: {unset!r}."
        )
    if alternative not in ("two-sided", "larger", "smaller"):
        raise ValueError(
            f"unknown alternative {alternative!r}; expected 'two-sided', 'larger', or 'smaller'."
        )
    solved_for = unset[0]
    solved_value = float(
        TTestIndPower().solve_power(
            effect_size=effect_size,
            nobs1=nobs,
            alpha=alpha,
            power=power,
            ratio=ratio,
            alternative=alternative,
        )
    )
    # Exactly one of effect_size/nobs/power is None (solved_for); the other two are non-None.
    effect_size_val: float = solved_value if solved_for == "effect_size" else float(effect_size)  # type: ignore[arg-type]
    nobs_val: float = solved_value if solved_for == "nobs" else float(nobs)  # type: ignore[arg-type]
    power_val: float = solved_value if solved_for == "power" else float(power)  # type: ignore[arg-type]
    return pd.DataFrame(
        [
            {
                "effect_size": effect_size_val,
                "nobs": nobs_val,
                "alpha": float(alpha),
                "power": power_val,
                "ratio": float(ratio),
                "alternative": alternative,
                "solved_for": solved_for,
            }
        ]
    )


@dataclass
class CrosstabResult:
    """Structured, inspectable result of a cross-tabulation.

    Attributes
    ----------
    table: tidy DataFrame -- the cross-tabulated counts (or normalized proportions), with
        ``row_col``'s values as a leading column, one column per ``col_col`` value, and
        (if ``margins=True``) a trailing "Total" row and column.
    chi_square, p_value, dof: chi-square test of independence, ALWAYS computed on the raw,
        un-margined, un-normalized 2x2+ contingency table -- stable regardless of ``normalize``/
        ``margins``.
    n: total number of observations in the raw contingency table.
    """

    table: pd.DataFrame
    chi_square: float
    p_value: float
    dof: int
    n: int


@public_op(name="ef.stats.crosstab")
def crosstab(
    df: pd.DataFrame,
    *,
    row_col: str,
    col_col: str,
    normalize: str = "none",
    margins: bool = True,
) -> CrosstabResult:
    """Cross-tabulate two categorical columns into counts (or normalized proportions), with
    optional margins, plus a chi-square test of independence.

    Thin wrapper over ``pandas.crosstab`` (the table) and ``scipy.stats.chi2_contingency`` (the
    test). ``normalize`` is ``"none"``, ``"index"`` (row percentages), ``"columns"`` (column
    percentages), or ``"all"`` (overall percentages) -- these map onto pandas' own
    ``normalize=False/"index"/"columns"/"all"`` values, spelled out as explicit strings so every
    choice is enumerable for a node dropdown. ``margins``, when True, adds a "Total" row/column to
    ``table``. The chi-square test always runs on the RAW un-margined, un-normalized table, so
    ``chi_square``/``p_value``/``dof`` never change based on ``normalize``/``margins``. Distinct
    from ``group_by_aggregate``: this always cross-tabulates COUNTS of two categorical columns
    into a full 2D table, not an arbitrary aggregation of a third value column. Never mutates
    ``df``.
    """
    if row_col not in df.columns:
        raise ValueError(f"unknown row_col {row_col!r}; expected one of {list(df.columns)!r}.")
    if col_col not in df.columns:
        raise ValueError(f"unknown col_col {col_col!r}; expected one of {list(df.columns)!r}.")
    if row_col == col_col:
        raise ValueError(f"row_col and col_col must differ; both were {row_col!r}.")
    if normalize not in ("none", "index", "columns", "all"):
        raise ValueError(
            f"unknown normalize {normalize!r}; expected 'none', 'index', 'columns', or 'all'."
        )
    raw_table = pd.crosstab(df[row_col], df[col_col])
    if raw_table.shape[0] < 2 or raw_table.shape[1] < 2:
        raise ValueError(
            f"crosstab needs at least a 2x2 table; got shape {raw_table.shape} from "
            f"{row_col!r} x {col_col!r}."
        )
    chi2, p, dof, _expected = chi2_contingency(raw_table.to_numpy())
    n = int(raw_table.to_numpy().sum())
    normalize_arg: bool | str = False if normalize == "none" else normalize
    table = pd.crosstab(
        df[row_col],
        df[col_col],
        normalize=normalize_arg,
        margins=margins,
        margins_name="Total",
    )
    table = table.reset_index()
    table.columns.name = None
    return CrosstabResult(
        table=table,
        chi_square=float(chi2),
        p_value=float(p),
        dof=int(dof),
        n=n,
    )


_COHORT_PERIODS = ("D", "W", "M")


@dataclass
class CohortRetentionResult:
    """Structured, inspectable result of a cohort retention analysis.

    Attributes
    ----------
    tidy: long-format DataFrame with columns ``cohort`` (the cohort's first-activity period, as
        a string), ``period_number`` (0, 1, 2, ... periods since the cohort's first activity),
        ``n_users`` (distinct users active in that period), ``cohort_size`` (the cohort's total
        user count, i.e. ``n_users`` at ``period_number=0``), ``retention_rate`` (``n_users /
        cohort_size``).
    wide: the same data pivoted, one row per ``cohort``, one column per ``period_number``
        (named ``period_0``, ``period_1``, ...), values are ``retention_rate``.
    """

    tidy: pd.DataFrame
    wide: pd.DataFrame


@public_op(name="ef.stats.cohort_retention")
def cohort_retention(
    df: pd.DataFrame,
    *,
    user_col: str,
    date_col: str,
    period: str = "M",
) -> CohortRetentionResult:
    """Cohort retention: group users by their first-activity period, track retention over time.

    Each user's COHORT is the calendar period (day/week/month, per ``period``) of their
    EARLIEST row in ``date_col``. For every subsequent period a user has at least one row in,
    their ``period_number`` (periods elapsed since their cohort's start, 0-indexed) is recorded.
    ``tidy`` is the long-format retention table; ``wide`` pivots it into a cohort x period-number
    retention matrix. Never mutates ``df``. Deterministic.
    """
    if user_col not in df.columns:
        raise ValueError(f"unknown user_col {user_col!r}; expected one of {list(df.columns)!r}.")
    if date_col not in df.columns:
        raise ValueError(f"unknown date_col {date_col!r}; expected one of {list(df.columns)!r}.")
    if user_col == date_col:
        raise ValueError(f"user_col and date_col must differ; both were {user_col!r}.")
    if period not in _COHORT_PERIODS:
        raise ValueError(f"unknown period {period!r}; expected one of {list(_COHORT_PERIODS)!r}.")

    work = df[[user_col, date_col]].copy()
    work["_period"] = pd.to_datetime(work[date_col]).dt.to_period(period)
    work["_cohort"] = work.groupby(user_col)["_period"].transform("min")
    work["_period_number"] = [
        (p - c).n for p, c in zip(work["_period"], work["_cohort"], strict=True)
    ]
    activity = work.drop_duplicates([user_col, "_cohort", "_period_number"])
    counts = (
        activity.groupby(["_cohort", "_period_number"])[user_col]
        .nunique()
        .reset_index(name="n_users")
    )
    cohort_sizes = (
        activity.loc[activity["_period_number"] == 0]
        .groupby("_cohort")[user_col]
        .nunique()
        .rename("cohort_size")
    )
    tidy = counts.merge(cohort_sizes, left_on="_cohort", right_index=True)
    tidy["retention_rate"] = tidy["n_users"] / tidy["cohort_size"]
    tidy = tidy.rename(columns={"_cohort": "cohort", "_period_number": "period_number"})
    tidy["cohort"] = tidy["cohort"].astype(str)
    tidy = tidy.sort_values(["cohort", "period_number"]).reset_index(drop=True)

    wide = tidy.pivot(index="cohort", columns="period_number", values="retention_rate")
    wide.columns = [f"period_{c}" for c in wide.columns]
    wide = wide.reset_index()
    wide.columns.name = None

    return CohortRetentionResult(tidy=tidy, wide=wide)


@public_op(name="ef.stats.funnel")
def funnel(
    df: pd.DataFrame,
    *,
    user_col: str,
    event_col: str,
    steps: list[str],
) -> pd.DataFrame:
    """Per-step conversion + drop-off funnel over an event log.

    ``steps`` is an ORDERED list of event names expected as values in ``event_col``. For each
    step, counts the number of DISTINCT users in ``user_col`` who have AT LEAST ONE row with
    that event value. This is deliberately NOT temporally-ordered per user (it does not check
    that a user's events happened in the ``steps`` order) -- a simpler, widely used funnel
    definition ("reached this step at some point") that avoids needing a timestamp column and
    per-user event-sequencing logic. Returns a tidy DataFrame with one row per step, columns
    ``step``, ``step_number`` (0-indexed), ``n_users``, ``conversion_rate`` (relative to step 0),
    ``drop_off`` (raw user-count decrease from the previous step; 0 for step 0),
    ``drop_off_rate`` (``drop_off`` / previous step's ``n_users``; 0.0 for step 0). Never mutates
    ``df``. Deterministic.
    """
    if user_col not in df.columns:
        raise ValueError(f"unknown user_col {user_col!r}; expected one of {list(df.columns)!r}.")
    if event_col not in df.columns:
        raise ValueError(f"unknown event_col {event_col!r}; expected one of {list(df.columns)!r}.")
    if user_col == event_col:
        raise ValueError(f"user_col and event_col must differ; both were {user_col!r}.")
    if not steps:
        raise ValueError("steps must be a non-empty ordered list of event names.")
    if len(steps) != len(set(steps)):
        raise ValueError(f"steps must be unique; got {steps!r}.")
    known_events = set(df[event_col].dropna().unique())
    unknown_steps = [s for s in steps if s not in known_events]
    if unknown_steps:
        raise ValueError(
            f"unknown step event(s) {unknown_steps!r}; expected one of "
            f"{sorted(str(e) for e in known_events)!r}."
        )

    rows = []
    first_n: int | None = None
    prev_n: int | None = None
    for i, step in enumerate(steps):
        n_users = int(df.loc[df[event_col] == step, user_col].nunique())
        if i == 0:
            first_n = n_users
        conversion_rate = n_users / first_n if first_n else float("nan")
        if prev_n is None:
            drop_off = 0
            drop_off_rate = 0.0
        else:
            drop_off = prev_n - n_users
            drop_off_rate = drop_off / prev_n if prev_n else float("nan")
        rows.append(
            {
                "step": step,
                "step_number": i,
                "n_users": n_users,
                "conversion_rate": conversion_rate,
                "drop_off": drop_off,
                "drop_off_rate": drop_off_rate,
            }
        )
        prev_n = n_users
    return pd.DataFrame(rows)


@public_op(name="ef.stats.describe")
def describe(df: pd.DataFrame, *, columns: list[str] | None = None) -> pd.DataFrame:
    """Compute summary statistics for numeric columns, returned as a tidy DataFrame.

    Thin wrapper over ``pandas.DataFrame.describe``. With ``columns`` given, only those
    columns are described (each must exist). The statistic name (count, mean, std, ...) is
    moved from the index into a leading ``statistic`` column so the result is tidy/serializable.
    """
    if columns is not None:
        unknown = [c for c in columns if c not in df.columns]
        if unknown:
            raise ValueError(f"unknown columns {unknown!r}; expected one of {list(df.columns)!r}.")
        target = df[columns]
    else:
        target = df
    result = target.describe().reset_index(names="statistic")
    return result


@public_op(name="ef.stats.correlation")
def correlation(
    df: pd.DataFrame,
    *,
    method: str = "pearson",
    columns: list[str] | None = None,
    max_footprint_bytes: int | None = None,
) -> pd.DataFrame:
    """Compute a pairwise correlation matrix, returned as a tidy DataFrame.

    Thin wrapper over ``pandas.DataFrame.corr``. ``method`` is one of pearson/spearman/kendall.
    With ``columns`` given, only those columns are correlated (each must exist). The row labels
    are moved into a leading ``column`` field so the matrix is tidy/serializable.
    ``max_footprint_bytes`` caps the estimated dense D x D footprint (default 2 GiB, see
    ``emergentflow.stats.scale``); ``correlation`` refuses to run above the cap to protect the
    shared in-process server from OOM. Pass a very large value to effectively disable the guard.
    """
    if method not in CORR_METHODS:
        raise ValueError(f"unknown method {method!r}; expected one of {list(CORR_METHODS)!r}.")
    if columns is not None:
        unknown = [c for c in columns if c not in df.columns]
        if unknown:
            raise ValueError(f"unknown columns {unknown!r}; expected one of {list(df.columns)!r}.")
        target = df[columns].select_dtypes(include="number")
        dropped = [c for c in columns if c not in target.columns]
        if dropped:
            raise ValueError(
                f"columns {dropped!r} are not numeric and cannot be correlated; "
                f"pass only numeric columns."
            )
    else:
        target = df.select_dtypes(include="number")
    enforce_dense_square_guard(target.shape[1], max_footprint_bytes, "correlation")
    result = target.corr(method=method).reset_index(names="column")
    return result


#: Maps an optional pip-extra target to every module whose presence proves the extra is fully
#: installed, so fit_model can raise a typed MissingOptionalDependencyError (never an opaque
#: ImportError) before attempting to fit an optional-dependency model (Epic 12 Story 1's hard
#: optional boundary). All modules must be importable -- a partial install (e.g. bambi present but
#: pymc/arviz absent) must still raise, not silently proceed into a bare ImportError later.
_EXTRA_PROBE_MODULES = {"emergentflow[bayes]": ("bambi", "pymc", "arviz")}


def _require_extra(extra: str) -> None:
    """Raise MissingOptionalDependencyError(extra) unless all of *extra*'s probe modules import."""
    probes = _EXTRA_PROBE_MODULES.get(extra)
    if not probes or any(importlib.util.find_spec(probe) is None for probe in probes):
        raise MissingOptionalDependencyError(extra)


@public_op(name="ef.stats.fit_model")
def fit_model(df: pd.DataFrame, *, model: str, spec: dict[str, Any]) -> FittedStatsModel:
    """Fit a curated, allow-listed statistical model and return an inspectable FittedStatsModel.

    The single seam every fit-model node routes through (Epic 12, Story 2). ``model`` is validated
    against the allow-list registry and ``spec`` against the shared ``_prepare_model_spec`` gate
    (raising :class:`~emergentflow.stats.errors.UnknownModelError` /
    :class:`~emergentflow.stats.errors.InvalidModelSpecError`); a model requiring an optional
    dependency extra that is absent raises
    :class:`~emergentflow.stats.errors.MissingOptionalDependencyError`. The resolved model's own
    per-family ``fitter`` assembles the backend call and builds the ``FittedStatsModel`` (the tidy
    coefficient/diagnostic frames + fit_stats + the live results object). Because both
    ``compile_to_code``'s emitted code and ``execute`` reach a model only through this function,
    ADR-0002 equivalence holds by construction. Never mutates ``df``.
    """
    model_spec, resolved_spec = _prepare_model_spec(df, model, spec)
    if model_spec.requires_extra is not None:
        _require_extra(model_spec.requires_extra)
    return model_spec.fitter(df, resolved_spec)


@public_op(name="ef.stats.diagnostic")
def diagnostic(
    df: pd.DataFrame | None = None,
    *,
    diagnostic: str,
    model: FittedStatsModel | None = None,
    spec: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Compute a curated, allow-listed diagnostic and return a tidy DataFrame.

    The single seam every diagnostic node routes through (Epic 12, Story 6), mirroring
    ``fit_model``. ``diagnostic`` is validated against the diagnostic allow-list registry and
    ``spec`` against the shared ``_prepare_diagnostic_spec`` gate; exactly one of ``df``/``model``
    must be given, matching the resolved diagnostic's ``needs_frame``/``needs_model`` contract.
    Never mutates ``df``. Never returns a live model object -- always a plain tidy DataFrame.
    """
    diag_spec, resolved_spec = _prepare_diagnostic_spec(df, model, diagnostic, spec or {})
    return diag_spec.fn(df, model, resolved_spec)


from emergentflow.stats import catalog, diagnostics_catalog  # noqa: E402, F401
