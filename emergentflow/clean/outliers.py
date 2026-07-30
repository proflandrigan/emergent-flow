"""
emergentflow.clean.outliers
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Statistical outlier flagging. Thin wrapper over pandas' own mean/std/quantile —
no reimplementation, no hidden transformation. Never mutates the input.
"""

from __future__ import annotations

import pandas as pd
from pandas.api.types import is_numeric_dtype

from emergentflow.api import public_op

from .errors import CleanError, ColumnCollisionError, UnknownColumnError

#: Threshold rules, spelled out as explicit strings so every choice is enumerable.
OUTLIER_METHODS = ("zscore", "modified_zscore", "iqr", "quantile", "percent")

#: How per-column flags combine into the single row-level flag.
OUTLIER_COMBINE = ("any", "all")

#: Phi^-1(0.75); makes modified-z comparable to z.
_MAD_SCALE = 0.6744897501960817


def _bounds(
    series: pd.Series,
    *,
    method: str,
    threshold: float,
) -> tuple[float, float]:
    """Return the (lower, upper) outlier fence for ``series`` under ``method``/``threshold``.

    The fence is the boundary inside which values are considered inliers; values exactly on
    the fence are NOT flagged (the flag rule uses strict ``>`` deviation). The returned
    bounds are always JSON-native ``float`` scalars.
    """
    if method == "zscore":
        mean = float(series.mean())
        std = float(series.std())
        if std == 0 or pd.isna(std):
            return (mean, mean)
        delta = threshold * std
        return (mean - delta, mean + delta)

    if method == "modified_zscore":
        median = float(series.median())
        mad = float((series - median).abs().median())
        if mad == 0 or pd.isna(mad):
            return (median, median)
        delta = threshold * mad / _MAD_SCALE
        return (median - delta, median + delta)

    if method == "iqr":
        p25 = float(series.quantile(0.25))
        p75 = float(series.quantile(0.75))
        iqr = p75 - p25
        if iqr == 0 or pd.isna(iqr):
            return (p25, p75)
        delta = threshold * iqr
        return (p25 - delta, p75 + delta)

    if method == "quantile":
        lower = float(series.quantile(threshold))
        upper = float(series.quantile(1 - threshold))
        return (lower, upper)

    if method == "percent":
        median = float(series.median())
        abs_dev = (series - median).abs()
        cutoff = float(abs_dev.quantile(1 - threshold))
        if cutoff == 0 or pd.isna(cutoff):
            return (median, median)
        return (median - cutoff, median + cutoff)

    raise CleanError(f"unknown method {method!r}; expected one of {OUTLIER_METHODS!r}.")


def _deviation(
    series: pd.Series,
    *,
    method: str,
    threshold: float,
) -> pd.Series:
    """Return a normalized deviation series where values ``> 1.0`` are past the cut.

    ``0`` means well inside the fence; ``1.0`` means exactly on the fence; ``> 1.0`` means
    outside it. Missing values in ``series`` propagate as ``NaN`` deviation.
    """
    lower, upper = _bounds(series, method=method, threshold=threshold)

    if method in ("zscore", "modified_zscore", "iqr", "quantile"):
        raw = pd.Series(0.0, index=series.index)
        below = series < lower
        above = series > upper
        raw[below] = lower - series[below]
        raw[above] = series[above] - upper

        if method == "zscore":
            cut_width = threshold * float(series.std())
        elif method == "modified_zscore":
            median = float(series.median())
            mad = float((series - median).abs().median())
            cut_width = threshold * mad / _MAD_SCALE
        elif method == "iqr":
            cut_width = threshold * (float(series.quantile(0.75)) - float(series.quantile(0.25)))
        else:  # quantile
            cut_width = (upper - lower) / 2.0

        if cut_width == 0 or pd.isna(cut_width):
            return pd.Series(0.0, index=series.index)
        deviation = raw / cut_width
        deviation[below | above] = deviation[below | above] + 1.0
        return deviation

    if method == "percent":
        median = float(series.median())
        abs_dev = (series - median).abs()
        cutoff = float(abs_dev.quantile(1 - threshold))
        if cutoff == 0 or pd.isna(cutoff):
            return pd.Series(0.0, index=series.index)
        return abs_dev / cutoff

    raise CleanError(f"unknown method {method!r}; expected one of {OUTLIER_METHODS!r}.")


@public_op(name="ef.clean.detect_outliers")
def detect_outliers(
    df: pd.DataFrame,
    *,
    columns: list[str] | None = None,
    method: str = "zscore",
    threshold: float = 3.0,
    combine: str = "any",
    flag_column: str = "is_outlier",
    score_column: str = "outlier_score",
    drop: bool = False,
) -> pd.DataFrame:
    """Flag outlying rows, returning a NEW DataFrame.

    Adds a boolean ``flag_column`` and a float ``score_column`` (the strongest per-column
    normalized deviation). ``method``:

    * ``"zscore"`` — |x - mean| / std > ``threshold`` (threshold in SDs, e.g. 3.0)
    * ``"modified_zscore"`` — MAD-based, robust to the outliers themselves
    * ``"iqr"`` — outside [p25 - k*IQR, p75 + k*IQR] (``threshold`` is k, e.g. 1.5)
    * ``"quantile"`` — outside [q, 1-q] (``threshold`` is q, e.g. 0.01)
    * ``"percent"`` — the most extreme ``threshold`` fraction by |x - median|

    When ``columns is None`` the target defaults to the numeric columns. ``combine`` decides
    whether a row is flagged when ANY or ALL target columns flag it. ``drop=True`` returns only
    the non-outlier rows and omits both added columns.

    Deterministic (pure pandas aggregation, no sampling).
    """
    if method not in OUTLIER_METHODS:
        raise CleanError(f"unknown method {method!r}; expected one of {OUTLIER_METHODS!r}.")
    if combine not in OUTLIER_COMBINE:
        raise CleanError(f"unknown combine {combine!r}; expected one of {OUTLIER_COMBINE!r}.")

    if columns is not None:
        unknown = [c for c in columns if c not in df.columns]
        if unknown:
            raise UnknownColumnError(
                f"unknown columns {unknown!r}; expected one of {list(df.columns)!r}."
            )
        non_numeric = [c for c in columns if not is_numeric_dtype(df[c])]
        if non_numeric:
            raise CleanError(
                f"columns {non_numeric!r} are not numeric; every outlier rule is "
                "undefined on non-numeric data."
            )
        target = list(columns)
    else:
        target = list(df.select_dtypes(include="number").columns)

    collisions = [c for c in (flag_column, score_column) if c in df.columns]
    if collisions:
        raise ColumnCollisionError(
            f"detect_outliers would overwrite existing column(s) {collisions!r}; "
            "choose different flag_column/score_column names."
        )

    result = df.copy()
    if not target:
        result[flag_column] = False
        result[score_column] = float("nan")
        return result.drop(columns=[flag_column, score_column]).copy() if drop else result

    scores = pd.DataFrame(index=df.index)
    for col in target:
        scores[col] = _deviation(df[col], method=method, threshold=threshold)

    flags = scores > 1.0
    is_outlier = flags.any(axis=1) if combine == "any" else flags.all(axis=1)

    result[flag_column] = is_outlier
    result[score_column] = scores.max(axis=1)
    if drop:
        return result.loc[~is_outlier].drop(columns=[flag_column, score_column]).copy()
    return result
