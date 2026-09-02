"""Survival-analysis operations (Epic 19, Story 8). Thin wrappers over lifelines.

Requires ``emergentflow[survival]`` extra. A base-install import of this module
raises :class:`~emergentflow.stats.errors.MissingOptionalDependencyError` with
an install hint. Both ``fit_survival`` and ``survival_curve`` are ``@public_op``
operations that return tidy DataFrames.
"""

from __future__ import annotations

import importlib.util
from typing import Any

import pandas as pd

from emergentflow.api import public_op
from emergentflow.stats.errors import MissingOptionalDependencyError

_EXTRA = "emergentflow[survival]"
_LIFELINES_PROBE = "lifelines"


def _require_lifelines() -> None:
    """Raise :class:`MissingOptionalDependencyError` if lifelines is not installed."""
    if importlib.util.find_spec(_LIFELINES_PROBE) is None:
        raise MissingOptionalDependencyError(_EXTRA)


@public_op(name="ef.stats.fit_survival")
def fit_survival(
    df: pd.DataFrame,
    *,
    duration_col: str,
    event_col: str,
    formula: str | None = None,
    alpha: float = 0.05,
) -> pd.DataFrame:
    """Fit a Cox proportional-hazards model and return a tidy coefficient frame.

    Thin wrapper over ``lifelines.CoxPHFitter``. When ``formula`` is given it is
    used as the Patsy-style formula; otherwise all columns except ``duration_col``
    and ``event_col`` are used as predictors. Returns one row per covariate with
    ``coef``, ``exp(coef)`` (hazard ratio), ``se(coef)``, ``z``, ``p``,
    ``ci_low``, ``ci_high``, and ``n_events``/``n_observations`` as metadata.
    Also returns a ``proportional_hazard_test`` row if the PH assumption is
    violated (Schoenfeld residuals test p-value < alpha).
    """
    _require_lifelines()
    from lifelines import CoxPHFitter

    if duration_col not in df.columns:
        raise ValueError(
            f"unknown duration_col {duration_col!r}; expected one of {list(df.columns)!r}."
        )
    if event_col not in df.columns:
        raise ValueError(f"unknown event_col {event_col!r}; expected one of {list(df.columns)!r}.")

    cph = CoxPHFitter(alpha=alpha)
    if formula:
        cph.fit(df, duration_col=duration_col, event_col=event_col, formula=formula)
    else:
        cph.fit(df, duration_col=duration_col, event_col=event_col)

    summary = cph.summary.reset_index()
    summary = summary.rename(
        columns={
            "coef": "coef",
            "exp(coef)": "hazard_ratio",
            "se(coef)": "se",
            "z": "z",
            "p": "p_value",
            "coef lower 95%": "ci_low",
            "coef upper 95%": "ci_high",
        }
    )
    summary["n_observations"] = cph._n_examples
    summary["n_events"] = cph._n_events

    try:
        ph_test = cph.check_assumptions(
            df, p_value_threshold=alpha, show_plots=False, print_warning=False
        )
        ph_rows = []
        for col, row in ph_test.summary.iterrows():
            ph_rows.append(
                {
                    "covariate": col,
                    "ph_test_p": float(row["p"]),
                    "ph_test_stat": float(row["test_statistic"]),
                    "ph_violation": bool(row["p"] < alpha),
                }
            )
        ph_df = pd.DataFrame(ph_rows) if ph_rows else pd.DataFrame()
    except Exception:
        ph_df = pd.DataFrame()

    if not ph_df.empty:
        for col in ["ph_test_p", "ph_test_stat", "ph_violation"]:
            summary[col] = float("nan")
        for _, ph_row in ph_df.iterrows():
            mask = summary["covariate"] == ph_row["covariate"]
            if mask.any():
                for col in ["ph_test_p", "ph_test_stat", "ph_violation"]:
                    summary.loc[mask, col] = ph_row[col]

    return summary


@public_op(name="ef.stats.survival_curve")
def survival_curve(
    df: pd.DataFrame,
    *,
    duration_col: str,
    event_col: str,
    group_col: str | None = None,
    alpha: float = 0.05,
) -> pd.DataFrame:
    """Compute Kaplan-Meier survival curves.

    Thin wrapper over ``lifelines.KaplanMeierFitter``. When ``group_col`` is given,
    one curve per group is computed and the DataFrame has columns ``group``,
    ``timeline``, ``survival_probability``, ``ci_low``, ``ci_high``. Without
    ``group_col``, a single curve is returned (no ``group`` column).
    """
    _require_lifelines()
    from lifelines import KaplanMeierFitter

    if duration_col not in df.columns:
        raise ValueError(
            f"unknown duration_col {duration_col!r}; expected one of {list(df.columns)!r}."
        )
    if event_col not in df.columns:
        raise ValueError(f"unknown event_col {event_col!r}; expected one of {list(df.columns)!r}.")

    rows: list[dict[str, Any]] = []

    if group_col is not None:
        if group_col not in df.columns:
            raise ValueError(
                f"unknown group_col {group_col!r}; expected one of {list(df.columns)!r}."
            )
        for group_name, sub in df.groupby(group_col, sort=True):
            kmf = KaplanMeierFitter()
            kmf.fit(sub[duration_col], event_observed=sub[event_col], alpha=alpha)
            for t, surv, ci_l, ci_u in zip(
                kmf.survival_function_.index,
                kmf.survival_function_["KM_estimate"],
                kmf.confidence_interval_.iloc[:, 0],
                kmf.confidence_interval_.iloc[:, 1],
                strict=True,
            ):
                rows.append(
                    {
                        "group": str(group_name),
                        "timeline": float(t),
                        "survival_probability": float(surv),
                        "ci_low": float(ci_l),
                        "ci_high": float(ci_u),
                    }
                )
    else:
        kmf = KaplanMeierFitter()
        kmf.fit(df[duration_col], event_observed=df[event_col], alpha=alpha)
        for t, surv, ci_l, ci_u in zip(
            kmf.survival_function_.index,
            kmf.survival_function_["KM_estimate"],
            kmf.confidence_interval_.iloc[:, 0],
            kmf.confidence_interval_.iloc[:, 1],
            strict=True,
        ):
            rows.append(
                {
                    "timeline": float(t),
                    "survival_probability": float(surv),
                    "ci_low": float(ci_l),
                    "ci_high": float(ci_u),
                }
            )

    return pd.DataFrame(rows)
