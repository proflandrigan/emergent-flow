"""
emergentflow.stats.eda
~~~~~~~~~~~~~~~~~~~~~~~
Exploratory-data-analysis wrapper operations (Epic 12, Story 11).

The seam every EDA node (Task 5) routes through, mirroring ``fit_model``/``diagnostic``: each
function here is a ``@public_op`` that validates its inputs at the boundary (fail fast, clear
typed errors), never mutates the input ``df``, and returns a tidy, JSON-native ``DataFrame`` so
both ``compile_to_code``'s emitted code and ``execute`` reach identical results (ADR-0002). No
heavyweight reporting library is used here (see ``emergentflow/reports/`` for the ydata-profiling
based report node, which is explicitly kept separate).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
from pandas.api.types import is_numeric_dtype

from emergentflow.api import public_op
from emergentflow.clean.outliers import check_outlier_rule, is_outlier_eligible, outlier_bounds
from emergentflow.stats.scale import enforce_dense_square_guard

# ``PlotSpec`` (emergentflow.viz.models) is a standalone dataclass that imports nothing from
# ``emergentflow.stats``, so importing it here is cycle-free -- unlike ``emergentflow.viz`` itself
# (whose ``__init__`` imports ``emergentflow.stats.models``), which ``auto_eda`` imports lazily.
from emergentflow.viz.models import PlotSpec


@public_op(name="ef.stats.profile")
def profile(df: pd.DataFrame, *, columns: list[str] | None = None) -> pd.DataFrame:
    """Per-column profile (numeric + categorical), one row per column, as a tidy DataFrame.

    With ``columns`` given, only those columns are profiled (each must exist). Every column gets
    ``column``/``dtype``/``count``/``n_missing``/``pct_missing``/``n_unique``/``cardinality``;
    numeric columns additionally get ``mean``/``std``/``min``/``max``/``skew``/``kurtosis`` (NaN
    for non-numeric columns). Never mutates ``df``.
    """
    if columns is not None:
        unknown = [c for c in columns if c not in df.columns]
        if unknown:
            raise ValueError(f"unknown columns {unknown!r}; expected one of {list(df.columns)!r}.")
        target = df[columns]
    else:
        target = df

    rows: list[dict[str, Any]] = []
    for col in target.columns:
        series = target[col]
        count = int(series.count())
        n_missing = int(series.isna().sum())
        pct_missing = round(float(n_missing / len(series) * 100) if len(series) else 0.0, 4)
        n_unique = int(series.nunique())
        cardinality = float(n_unique / count) if count else 0.0
        row: dict[str, Any] = {
            "column": col,
            "dtype": str(series.dtype),
            "count": count,
            "n_missing": n_missing,
            "pct_missing": pct_missing,
            "n_unique": n_unique,
            "cardinality": cardinality,
        }
        if is_numeric_dtype(series):
            row["mean"] = float(series.mean())
            row["std"] = float(series.std())
            row["min"] = float(series.min())
            row["max"] = float(series.max())
            row["skew"] = float(series.skew())
            row["kurtosis"] = float(series.kurtosis())
        else:
            row["mean"] = float("nan")
            row["std"] = float("nan")
            row["min"] = float("nan")
            row["max"] = float("nan")
            row["skew"] = float("nan")
            row["kurtosis"] = float("nan")
        rows.append(row)
    return pd.DataFrame(rows)


@public_op(name="ef.stats.missingness")
def missingness(df: pd.DataFrame, *, columns: list[str] | None = None) -> pd.DataFrame:
    """Per-column null analysis, one row per column, as a tidy DataFrame.

    With ``columns`` given, only those columns are analyzed (each must exist). Columns:
    ``column``/``n_missing``/``n_present``/``pct_missing``. Rows are sorted by ``pct_missing``
    descending, then ``column`` ascending. Never mutates ``df``.
    """
    if columns is not None:
        unknown = [c for c in columns if c not in df.columns]
        if unknown:
            raise ValueError(f"unknown columns {unknown!r}; expected one of {list(df.columns)!r}.")
        target = df[columns]
    else:
        target = df

    n_rows = len(target)
    rows: list[dict[str, Any]] = []
    for col in target.columns:
        n_missing = int(target[col].isna().sum())
        n_present = int(n_rows - n_missing)
        pct_missing = round(float(n_missing / n_rows * 100) if n_rows else 0.0, 4)
        rows.append(
            {
                "column": col,
                "n_missing": n_missing,
                "n_present": n_present,
                "pct_missing": pct_missing,
            }
        )
    result = pd.DataFrame(rows)
    result = result.sort_values(by=["pct_missing", "column"], ascending=[False, True]).reset_index(
        drop=True
    )
    return result


@public_op(name="ef.stats.co_missingness")
def co_missingness(
    df: pd.DataFrame,
    *,
    columns: list[str] | None = None,
    max_footprint_bytes: int | None = None,
) -> pd.DataFrame:
    """Pairwise co-missingness matrix, tidy like ``correlation``'s output.

    With ``columns`` given, only those columns are included (each must exist). Cell (i, j) is the
    fraction of rows where both column i and column j are null; the diagonal is each column's own
    missing fraction. Row labels are moved into a leading ``column`` field. Never mutates ``df``.

    The output is an inherently dense D x D matrix, so a pre-flight guard refuses footprints above
    ``max_footprint_bytes`` (default
    :data:`~emergentflow.stats.scale.DEFAULT_MAX_DENSE_FOOTPRINT_BYTES`)
    to protect the shared in-process server from OOM; pass a very large value to effectively
    disable the guard.
    """
    if columns is not None:
        unknown = [c for c in columns if c not in df.columns]
        if unknown:
            raise ValueError(f"unknown columns {unknown!r}; expected one of {list(df.columns)!r}.")
        # `columns` may contain duplicates; dedupe (preserving first-seen order) so the mask
        # doesn't end up with duplicate labels (matches `correlation`'s behavior).
        columns = list(dict.fromkeys(columns))
        target = df[columns]
    else:
        target = df

    enforce_dense_square_guard(target.shape[1], max_footprint_bytes, "co_missingness")

    mask = target.isna()
    cols = list(target.columns)
    data = {j: [float((mask[i] & mask[j]).mean()) for i in cols] for j in cols}
    matrix = pd.DataFrame(data, index=cols, columns=cols)
    return matrix.reset_index(names="column")


@public_op(name="ef.stats.distribution_summary")
def distribution_summary(df: pd.DataFrame, *, columns: list[str] | None = None) -> pd.DataFrame:
    """Per-numeric-column distribution/spread summary, one row per numeric column.

    With ``columns`` given, each named column must exist (raises otherwise), but a
    present-but-non-numeric named column is simply omitted from the output. Columns:
    ``column``/``count``/``mean``/``std``/``min``/``p05``/``p25``/``p50``/``p75``/``p95``/
    ``max``/``iqr``. Never mutates ``df``.
    """
    if columns is not None:
        unknown = [c for c in columns if c not in df.columns]
        if unknown:
            raise ValueError(f"unknown columns {unknown!r}; expected one of {list(df.columns)!r}.")
        target = df[columns]
    else:
        target = df

    rows: list[dict[str, Any]] = []
    for col in target.columns:
        series = target[col]
        if not is_numeric_dtype(series):
            continue
        quantiles = series.quantile([0.05, 0.25, 0.5, 0.75, 0.95])
        p05 = float(quantiles.loc[0.05])
        p25 = float(quantiles.loc[0.25])
        p50 = float(quantiles.loc[0.5])
        p75 = float(quantiles.loc[0.75])
        p95 = float(quantiles.loc[0.95])
        rows.append(
            {
                "column": col,
                "count": int(series.count()),
                "mean": float(series.mean()),
                "std": float(series.std()),
                "min": float(series.min()),
                "p05": p05,
                "p25": p25,
                "p50": p50,
                "p75": p75,
                "p95": p95,
                "max": float(series.max()),
                "iqr": p75 - p25,
            }
        )
    return pd.DataFrame(rows)


@public_op(name="ef.stats.outlier_summary")
def outlier_summary(
    df: pd.DataFrame,
    *,
    columns: list[str] | None = None,
    method: str = "zscore",
    threshold: float = 3.0,
) -> pd.DataFrame:
    """Report the outlier bounds a rule would apply, one row per numeric column.

    The auditable companion to ``ef.clean.detect_outliers``: same ``columns``/
    ``method``/``threshold`` contract, but returns the thresholds and hit counts
    instead of a flagged frame. Columns:
    ``column``/``method``/``threshold``/``lower``/``upper``/``n``/``n_outliers``/
    ``pct_outliers``.

    Shares the detector's ``check_outlier_rule``/``outlier_bounds``/``is_outlier_eligible``
    seam and applies the identical ``value < lower or value > upper`` test, so
    ``n_outliers`` always equals the number of rows ``detect_outliers`` flags for that
    column under the same arguments — the reported cut cannot drift from the applied cut.
    ``n`` counts non-missing values, and missing values are never counted as outliers.

    Where the two ops deliberately differ: a named column that is non-numeric (or boolean)
    is silently omitted here, mirroring ``distribution_summary``, where ``detect_outliers``
    raises. Raises ``ValueError`` for an unknown ``method`` or a ``threshold`` outside the
    method's domain. Never mutates ``df``.
    """
    problem = check_outlier_rule(method, threshold)
    if problem is not None:
        raise ValueError(problem)

    if columns is not None:
        unknown = [c for c in columns if c not in df.columns]
        if unknown:
            raise ValueError(f"unknown columns {unknown!r}; expected one of {list(df.columns)!r}.")
        target = df[columns]
    else:
        target = df

    rows: list[dict[str, Any]] = []
    for col in target.columns:
        series = target[col]
        if not is_outlier_eligible(series):
            continue
        values = series.astype("float64")
        lower, upper = outlier_bounds(values, method=method, threshold=threshold)
        n = int(values.count())
        n_outliers = int(((values < lower) | (values > upper)).sum())
        pct_outliers = round(float(n_outliers / n * 100) if n else 0.0, 4)
        rows.append(
            {
                "column": col,
                "method": method,
                "threshold": float(threshold),
                "lower": lower,
                "upper": upper,
                "n": n,
                "n_outliers": n_outliers,
                "pct_outliers": pct_outliers,
            }
        )
    return pd.DataFrame(rows)


@public_op(name="ef.stats.group_by_aggregate")
def group_by_aggregate(
    df: pd.DataFrame,
    *,
    by: str | list[str],
    agg: str | dict[str, str | list[str]],
    columns: list[str] | None = None,
) -> pd.DataFrame:
    """Split/agg/pivot returning a tidy DataFrame, one row per group.

    ``by`` is a grouping column or list of grouping columns (each must exist). ``agg`` is either a
    single aggregation name (e.g. ``"mean"``) or a dict mapping value columns to aggregation
    function(s), passed straight to ``DataFrame.groupby(by).agg(agg)``. With ``columns`` given,
    only those value columns are aggregated (each must exist); if ``agg`` is a str and ``columns``
    is ``None``, all numeric non-``by`` columns are aggregated. After aggregation, group keys are
    restored as leading columns via ``reset_index`` so the result is tidy; when a dict ``agg``
    maps a column to a *list* of aggregation functions, pandas emits ``MultiIndex`` columns
    (e.g. ``("x", "mean")``), which are flattened to single ``"x_mean"``-style names so the
    result stays a genuinely tidy, JSON-round-trippable frame. Never mutates ``df``.
    """
    by_cols = [by] if isinstance(by, str) else list(by)
    unknown_by = [c for c in by_cols if c not in df.columns]
    if unknown_by:
        raise ValueError(f"unknown columns {unknown_by!r}; expected one of {list(df.columns)!r}.")

    if columns is not None:
        unknown = [c for c in columns if c not in df.columns]
        if unknown:
            raise ValueError(f"unknown columns {unknown!r}; expected one of {list(df.columns)!r}.")

    if isinstance(agg, str):
        if columns is not None:
            value_cols = [c for c in columns if c not in by_cols]
        else:
            value_cols = [c for c in df.columns if c not in by_cols and is_numeric_dtype(df[c])]
        target = df[by_cols + value_cols]
    else:
        if columns is not None:
            agg = {k: v for k, v in agg.items() if k in columns}
        target = df[by_cols + list(agg.keys())]
    grouped = target.groupby(by_cols).agg(agg)
    if isinstance(grouped.columns, pd.MultiIndex):
        grouped.columns = [
            "_".join(str(level) for level in col if level) for col in grouped.columns
        ]

    return grouped.reset_index()


@dataclass
class AutoEdaResult:
    """A one-shot exploratory-data-analysis bundle: tidy summary frames + curated plots.

    ``frames`` and ``plots`` are string-keyed dicts of inspectable values (tidy DataFrames and
    :class:`~emergentflow.viz.models.PlotSpec`s), so an ``AutoEdaResult`` is itself inspectable
    under the ``@public_op`` contract and rides the result-payload contract untouched (every leaf
    is JSON-native). The bundle is *composed* from the existing ``ef.stats``/``ef.viz`` seams, so
    it inherits their ADR-0002 equivalence rather than reimplementing any analysis.

    Attributes
    ----------
    frames: ``profile`` / ``missingness`` / ``co_missingness`` / ``distribution_summary`` /
        ``correlation`` tidy frames.
    plots: ``distributions`` (per-column histograms) / ``correlation_heatmap`` / ``missingness``
        (a co-missingness heatmap -- which columns tend to go missing together).
    """

    frames: dict[str, pd.DataFrame]
    plots: dict[str, PlotSpec]


@public_op(name="ef.stats.auto_eda")
def auto_eda(df: pd.DataFrame, *, columns: list[str] | None = None) -> AutoEdaResult:
    """Run a one-shot EDA pass and return an inspectable :class:`AutoEdaResult` bundle.

    With ``columns`` given, the pass is restricted to those columns (each must exist). The bundle's
    tidy frames come from ``profile``/``missingness``/``co_missingness``/``distribution_summary``
    (this module) and ``ef.stats.correlation``; its plots come from ``ef.viz.plot`` and
    ``ef.viz.plot_correlation_heatmap``/``ef.viz.plot_missingness_heatmap`` -- so ``auto_eda`` is a
    *composition* of already-equivalent seams (Epic 12 Story 11), never a parallel implementation.
    ``missingness_plot`` renders the pairwise ``co_missingness`` matrix as a heatmap (which columns
    tend to go missing together), not just per-column missing rates. Never mutates ``df``.
    ``ef.stats.correlation`` and the viz seams are imported lazily to keep this module free of the
    ``emergentflow.viz`` import cycle.
    """
    if columns is not None:
        unknown = [c for c in columns if c not in df.columns]
        if unknown:
            raise ValueError(f"unknown columns {unknown!r}; expected one of {list(df.columns)!r}.")
        work = df[columns]
    else:
        work = df

    from emergentflow.stats import correlation
    from emergentflow.viz import plot, plot_correlation_heatmap, plot_missingness_heatmap

    profile_frame = profile(work)
    missingness_frame = missingness(work)
    co_missingness_frame = co_missingness(work)
    distribution_frame = distribution_summary(work)
    correlation_frame = correlation(work)

    # Per-column distribution histograms: melt the numeric columns to long form (private column
    # names so a real "value"/"variable" column can't collide), one faceted histogram per column.
    numeric = work.select_dtypes(include="number")
    long = numeric.melt(var_name="__variable__", value_name="__value__")
    distributions_plot = plot(
        long,
        chart="histogram",
        encoding={"x": "__value__", "facet_col": "__variable__"},
    )
    missingness_plot = plot_missingness_heatmap(co_missingness_frame)
    correlation_heatmap = plot_correlation_heatmap(correlation_frame)

    return AutoEdaResult(
        frames={
            "profile": profile_frame,
            "missingness": missingness_frame,
            "co_missingness": co_missingness_frame,
            "distribution_summary": distribution_frame,
            "correlation": correlation_frame,
        },
        plots={
            "distributions": distributions_plot,
            "correlation_heatmap": correlation_heatmap,
            "missingness": missingness_plot,
        },
    )


@public_op(name="ef.stats.data_dictionary")
def data_dictionary(
    df: pd.DataFrame,
    *,
    columns: list[str] | None = None,
    top_n: int = 5,
    notes: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Auto-emit a documented schema (data dictionary) for *df*, one row per column.

    Epic 16, Story 21. Pairs with :func:`auto_eda`: reuses :func:`profile` for the
    type/null-rate/cardinality/range columns (``dtype``/``count``/``n_missing``/
    ``pct_missing``/``n_unique``/``cardinality``, plus ``mean``/``std``/``min``/``max``/
    ``skew``/``kurtosis`` for numeric columns, NaN for non-numeric) rather than recomputing
    them, and adds two columns of its own:

    - ``top_values``: the *top_n* most frequent values in that column, as a JSON-native list
      of ``{"value": str, "count": int}`` dicts, most frequent first. Values are stringified
      so the column stays JSON-native regardless of the source dtype.
    - ``notes``: an optional caller-supplied note per column (``notes.get(column)``, ``None``
      if not given for that column or *notes* is ``None``) -- free-text documentation a user
      attaches to a column, carried through untouched.

    With ``columns`` given, only those columns are profiled (each must exist, same contract as
    :func:`profile`). Never mutates ``df``.
    """
    base = profile(df, columns=columns)
    target = df[columns] if columns is not None else df

    top_values: list[list[dict[str, Any]]] = []
    note_values: list[str | None] = []
    for col in base["column"]:
        counts = target[col].value_counts().head(top_n)
        top_values.append(
            [{"value": str(value), "count": int(count)} for value, count in counts.items()]
        )
        note_values.append((notes or {}).get(col))

    result = base.copy()
    result["top_values"] = top_values
    result["notes"] = note_values
    return result
