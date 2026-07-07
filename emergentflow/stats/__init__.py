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
from dataclasses import dataclass
from typing import Any

import pandas as pd
import statsmodels.api as sm
from scipy.stats import ttest_ind
from statsmodels.formula.api import ols

from emergentflow.api import public_op
from emergentflow.stats.diagnostics import DiagnosticSpec, known_diagnostic_keys
from emergentflow.stats.eda import (
    AutoEdaResult,
    auto_eda,
    co_missingness,
    distribution_summary,
    group_by_aggregate,
    missingness,
    profile,
)
from emergentflow.stats.errors import (
    InvalidModelSpecError,
    MissingOptionalDependencyError,
    StatsError,
    UnknownDiagnosticError,
    UnknownModelError,
)
from emergentflow.stats.models import FittedStatsModel
from emergentflow.stats.registry import ModelSpec, keys_for_archetype, known_model_keys
from emergentflow.stats.spec import _prepare_diagnostic_spec, _prepare_model_spec

__all__ = [
    "anova",
    "AnovaResult",
    "auto_eda",
    "AutoEdaResult",
    "co_missingness",
    "correlation",
    "CORR_METHODS",
    "describe",
    "diagnostic",
    "DiagnosticSpec",
    "distribution_summary",
    "group_by_aggregate",
    "missingness",
    "profile",
    "ttest",
    "TTestResult",
    "FittedStatsModel",
    "ModelSpec",
    "StatsError",
    "UnknownDiagnosticError",
    "UnknownModelError",
    "InvalidModelSpecError",
    "MissingOptionalDependencyError",
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
    """

    f_statistic: float
    p_value: float
    effect_size: float
    summary: pd.DataFrame


@dataclass
class TTestResult:
    """Structured, inspectable result of a two-sample t-test.

    Fields: t_statistic, p_value, df (degrees of freedom), group_a/group_b (the two group labels,
    sorted), n_a/n_b (per-group sizes), mean_a/mean_b (per-group means), equal_var (whether a
    Student's t-test was used vs Welch's), alpha (the caller-supplied significance threshold).
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
    a = df.loc[df[group_col].astype(str) == a_label, value_col]
    b = df.loc[df[group_col].astype(str) == b_label, value_col]
    res = ttest_ind(a, b, equal_var=equal_var)
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
    )


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

    return AnovaResult(
        f_statistic=float(effect["F"]),
        p_value=float(effect["PR(>F)"]),
        effect_size=partial_eta_sq,
        summary=table,
    )


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
) -> pd.DataFrame:
    """Compute a pairwise correlation matrix, returned as a tidy DataFrame.

    Thin wrapper over ``pandas.DataFrame.corr``. ``method`` is one of pearson/spearman/kendall.
    With ``columns`` given, only those columns are correlated (each must exist). The row labels
    are moved into a leading ``column`` field so the matrix is tidy/serializable.
    """
    if method not in CORR_METHODS:
        raise ValueError(f"unknown method {method!r}; expected one of {list(CORR_METHODS)!r}.")
    if columns is not None:
        unknown = [c for c in columns if c not in df.columns]
        if unknown:
            raise ValueError(f"unknown columns {unknown!r}; expected one of {list(df.columns)!r}.")
        target = df[columns]
    else:
        target = df.select_dtypes(include="number")
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
