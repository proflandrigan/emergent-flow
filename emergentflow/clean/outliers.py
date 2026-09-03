"""
emergentflow.clean.outliers
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Statistical outlier flagging. Thin wrapper over pandas' own mean/std/quantile —
no reimplementation, no hidden transformation. Never mutates the input.

Three helpers are the **shared seam** with :func:`emergentflow.stats.outlier_summary`
(issue #102): :func:`check_outlier_rule` validates a ``(method, threshold)`` pair,
:func:`outlier_bounds` computes the fence, and :func:`is_outlier_eligible` decides
which columns a rule applies to. Both ops call all three, so the cut a summary
*reports* is by construction the cut a detector *applies* — they cannot drift.
"""

from __future__ import annotations

import pandas as pd
from pandas.api.types import is_bool_dtype, is_numeric_dtype

from emergentflow.api import public_op

from .errors import CleanError, ColumnCollisionError, UnknownColumnError

#: Threshold rules, spelled out as explicit strings so every choice is enumerable.
OUTLIER_METHODS = ("zscore", "modified_zscore", "iqr", "quantile", "percent")

#: How per-column flags combine into the single row-level flag.
OUTLIER_COMBINE = ("any", "all")

#: Methods whose ``threshold`` is an unbounded positive multiplier rather than a fraction.
_MULTIPLIER_METHODS = ("zscore", "modified_zscore", "iqr")

#: Phi^-1(0.75); makes modified-z comparable to z.
_MAD_SCALE = 0.6744897501960817


def is_outlier_eligible(series: pd.Series) -> bool:
    """Whether *series* is a valid target for an outlier rule: numeric, but not boolean.

    ``bool`` counts as numeric to ``is_numeric_dtype`` yet is excluded from
    ``select_dtypes(include="number")``. Pinning the rule in one place keeps
    :func:`detect_outliers`' implicit column selection, its explicit ``columns=``
    validation, and :func:`emergentflow.stats.outlier_summary`'s selection in
    agreement — a boolean column is a flag, not a measurement, and no fence over
    ``{0, 1}`` is meaningful.
    """
    return is_numeric_dtype(series) and not is_bool_dtype(series)


def check_outlier_rule(method: str, threshold: float) -> str | None:
    """Return why ``(method, threshold)`` is not a usable rule, or ``None`` if it is.

    Returns a message rather than raising so each caller keeps its own family's error
    type (``CleanError`` for :func:`detect_outliers`, ``ValueError`` for
    ``ef.stats.outlier_summary``) without duplicating the validation itself.

    ``threshold`` means different things per method, so its valid domain differs: an
    unbounded positive multiplier for ``zscore``/``modified_zscore``/``iqr``, a tail
    quantile in ``(0, 0.5)`` for ``quantile``, and a fraction in ``(0, 1)`` for
    ``percent``. Without this check the shared default of ``3.0`` reaches
    ``Series.quantile(3.0)`` for the latter two and surfaces as an opaque pandas
    ``"percentiles should all be in the interval [0, 1]"``.
    """
    if method not in OUTLIER_METHODS:
        return f"unknown method {method!r}; expected one of {OUTLIER_METHODS!r}."
    if not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
        return f"threshold must be a number; got {threshold!r}."
    if pd.isna(threshold):
        return "threshold must be a number; got NaN."
    if method in _MULTIPLIER_METHODS:
        if threshold <= 0:
            return (
                f"threshold must be > 0 for method {method!r} (it is a multiplier: "
                f"standard deviations for zscore/modified_zscore, k for iqr); got {threshold!r}."
            )
    elif method == "quantile":
        if not 0 < threshold < 0.5:
            return (
                "threshold must be a tail quantile in (0, 0.5) for method 'quantile' "
                f"(e.g. 0.01 keeps the middle 98%); got {threshold!r}."
            )
    elif not 0 < threshold < 1:
        return (
            "threshold must be a fraction in (0, 1) for method 'percent' "
            f"(e.g. 0.05 flags the most extreme 5%); got {threshold!r}."
        )
    return None


def outlier_bounds(
    series: pd.Series,
    *,
    method: str,
    threshold: float,
) -> tuple[float, float]:
    """Return the ``(lower, upper)`` outlier fence for *series* under *method*/*threshold*.

    The fence is inclusive: a row is an outlier exactly when ``value < lower`` or
    ``value > upper``, so values sitting on the fence are inliers. Both
    :func:`detect_outliers` and ``ef.stats.outlier_summary`` derive their verdict from
    that one comparison against these bounds, which is what makes the reported cut and
    the applied cut the same cut. The returned bounds are always JSON-native ``float``
    scalars. When *series* has no spread the fence collapses to a single point, which
    is the mathematically correct fence (with ``IQR == 0`` the IQR rule fences at
    ``[p25, p75]``) and still classifies correctly.
    """
    values = series.astype("float64")

    if method == "zscore":
        mean = float(values.mean())
        std = float(values.std())
        if std == 0 or pd.isna(std):
            return (mean, mean)
        delta = threshold * std
        return (mean - delta, mean + delta)

    if method == "modified_zscore":
        median = float(values.median())
        mad = float((values - median).abs().median())
        if mad == 0 or pd.isna(mad):
            return (median, median)
        delta = threshold * mad / _MAD_SCALE
        return (median - delta, median + delta)

    if method == "iqr":
        p25 = float(values.quantile(0.25))
        p75 = float(values.quantile(0.75))
        iqr = p75 - p25
        if iqr == 0 or pd.isna(iqr):
            return (p25, p75)
        delta = threshold * iqr
        return (p25 - delta, p75 + delta)

    if method == "quantile":
        return (float(values.quantile(threshold)), float(values.quantile(1 - threshold)))

    if method == "percent":
        median = float(values.median())
        cutoff = float((values - median).abs().quantile(1 - threshold))
        if cutoff == 0 or pd.isna(cutoff):
            return (median, median)
        return (median - cutoff, median + cutoff)

    raise CleanError(f"unknown method {method!r}; expected one of {OUTLIER_METHODS!r}.")


def _deviation(values: pd.Series, *, lower: float, upper: float) -> pd.Series:
    """Score each value by how far it sits toward its fence, in fence half-widths.

    ``0.0`` at the centre of the fence, ``1.0`` exactly *on* either fence, and ``> 1.0``
    outside it — the same meaning for every method, so scores are comparable across
    rules. Each side is normalized by its own half-width, so an asymmetric fence (the
    IQR and quantile rules on skewed data) still reads ``1.0`` on both edges.

    ``inf`` when the fence has zero width on that side (a constant column, a column whose
    IQR is 0, a MAD of 0 because half the values are identical) and the value nonetheless
    sits outside it: strictly outside a zero-width fence *is* infinitely many fence
    half-widths away, so ``inf`` is the limit of the same formula rather than a special
    case. Scoring it ``NaN`` instead would be actively harmful, because
    :func:`detect_outliers` reduces the per-column scores with a NaN-skipping ``max`` —
    an unrelated column's benign score would then be published for a row this column
    flagged, and the ``> 1.0`` contract above would silently break on multi-column frames.

    ``NaN`` therefore means exactly one thing: the value itself is missing. Scores never
    decide membership — :func:`detect_outliers` flags rows from the bounds directly — so a
    ``NaN`` score never suppresses a flag.
    """
    centre = (lower + upper) / 2.0
    deviation = pd.Series(float("nan"), index=values.index, dtype="float64")
    for side, width in ((values > centre, upper - centre), (values < centre, centre - lower)):
        if width > 0:
            deviation[side] = (values[side] - centre).abs() / width
        elif width == 0:
            deviation[side] = float("inf")
    deviation[values == centre] = 0.0
    return deviation


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
    action: str = "flag",
    by: str | list[str] | None = None,
) -> pd.DataFrame:
    """Flag outlying rows, returning a NEW DataFrame.

    Adds a boolean ``flag_column`` and a float ``score_column`` (the strongest per-column
    deviation, in fence half-widths — see :func:`_deviation`). ``method``, and what
    ``threshold`` means for each:

    * ``"zscore"`` — outside mean ± ``threshold`` * std (``threshold`` in SDs, e.g. 3.0)
    * ``"modified_zscore"`` — the same fence built from median/MAD, robust to the
      outliers themselves (``threshold`` in SDs, e.g. 3.0)
    * ``"iqr"`` — outside [p25 - k*IQR, p75 + k*IQR] (``threshold`` is k, e.g. 1.5)
    * ``"quantile"`` — outside [q, 1-q] (``threshold`` is q in (0, 0.5), e.g. 0.01)
    * ``"percent"`` — the most extreme ``threshold`` fraction by |x - median|
      (``threshold`` in (0, 1), e.g. 0.05)

    A row is an outlier for a column exactly when its value falls strictly outside that
    column's fence, so the verdict here always matches the bounds ``ef.stats.outlier_summary``
    reports for the same arguments. When ``columns is None`` the target defaults to every
    numeric non-boolean column; naming a column that is missing, non-numeric, or boolean
    raises. ``combine`` decides whether a row is flagged when ANY or ALL target columns
    flag it; a missing value never flags, so under ``"all"`` one missing value in a target
    column is enough to leave the row unflagged. ``drop=True`` returns only the non-outlier
    rows and omits both added columns.

    ``by`` groups the data before flagging, so fences are computed within each
    group rather than over the whole column. Group columns are never treated as
    measurement columns. Pass a single column name (``str``) or a list.
    ``by=None`` (default) uses the whole frame.

    Deterministic (pure pandas aggregation, no sampling). Raises ``CleanError`` for an
    unknown ``method``/``combine`` or a ``threshold`` outside the method's domain, and
    ``ColumnCollisionError`` rather than overwriting an existing ``flag_column``/
    ``score_column`` — but only when ``drop`` is false, since ``drop=True`` adds neither
    column and so has nothing to overwrite.
    """
    problem = check_outlier_rule(method, threshold)
    if problem is not None:
        raise CleanError(problem)
    if combine not in OUTLIER_COMBINE:
        raise CleanError(f"unknown combine {combine!r}; expected one of {OUTLIER_COMBINE!r}.")
    if action not in ("flag", "drop", "clip"):
        raise CleanError(f"unknown action {action!r}; expected 'flag', 'drop', or 'clip'.")
    if drop and action == "flag":
        drop = True
        action = "drop"
    if drop and action not in ("drop",):
        raise CleanError(
            f"drop=True is incompatible with action={action!r}; use "
            f"action='drop' or set drop=False."
        )
    if not drop and action == "drop":
        action = "drop"
    effective_drop = drop or action == "drop"
    effective_clip = action == "clip"

    by_cols = [by] if isinstance(by, str) else (list(by) if by else [])
    unknown_by = [c for c in by_cols if c not in df.columns]
    if unknown_by:
        raise UnknownColumnError(
            f"unknown group columns {unknown_by!r}; expected one of {list(df.columns)!r}."
        )

    if columns is not None:
        unknown = [c for c in columns if c not in df.columns]
        if unknown:
            raise UnknownColumnError(
                f"unknown columns {unknown!r}; expected one of {list(df.columns)!r}."
            )
        # Exclude group columns before checking eligibility — group keys are never
        # measurement columns, even when the user includes them in ``columns``.
        measurement_columns = [c for c in columns if c not in by_cols]
        ineligible = [c for c in measurement_columns if not is_outlier_eligible(df[c])]
        if ineligible:
            raise CleanError(
                f"columns {ineligible!r} are not numeric; every outlier rule is "
                "undefined on non-numeric (and boolean) data."
            )
        target = list(measurement_columns)
    else:
        target = [c for c in df.columns if is_outlier_eligible(df[c])]

    # Never treat a grouping key as a measurement column.
    target = [c for c in target if c not in by_cols]

    # Only the non-drop path writes these columns, so only it can collide. Guarding
    # unconditionally would reject the natural two-node flow (flag with one
    # detect_outliers, then cut the rows with a second one set to drop=True) over
    # columns the second call never adds. Clip also never adds these columns.
    if not effective_drop and not effective_clip:
        collisions = [c for c in (flag_column, score_column) if c in df.columns]
        if collisions:
            raise ColumnCollisionError(
                f"detect_outliers would overwrite existing column(s) {collisions!r}; "
                "choose different flag_column/score_column names."
            )

    if effective_drop and not target:
        return df.copy()

    # Grouped path: compute fences within each subset, preserving original row order.
    if by_cols:
        parts = [
            detect_outliers(
                sub,
                columns=target,
                method=method,
                threshold=threshold,
                combine=combine,
                flag_column=flag_column,
                score_column=score_column,
                drop=drop,
                action=action,
            )
            for _, sub in df.groupby(by_cols, sort=False, dropna=False)
        ]
        if not parts:
            if effective_drop:
                return df.copy()
            result = df.copy()
            result[flag_column] = False
            result[score_column] = float("nan")
            return result
        out = pd.concat(parts)
        return out.reindex([i for i in df.index if i in out.index])

    result = df.copy()
    if not target:
        result[flag_column] = False
        result[score_column] = float("nan")
        return result

    flags = pd.DataFrame(index=df.index)
    scores = pd.DataFrame(index=df.index)
    for col in target:
        values = df[col].astype("float64")
        lower, upper = outlier_bounds(values, method=method, threshold=threshold)
        flags[col] = (values < lower) | (values > upper)
        scores[col] = _deviation(values, lower=lower, upper=upper)

    is_outlier = flags.any(axis=1) if combine == "any" else flags.all(axis=1)

    if effective_drop:
        return df.loc[~is_outlier].copy()

    if effective_clip:
        for col in target:
            bounds = outlier_bounds(df[col].astype("float64"), method=method, threshold=threshold)
            result[col] = result[col].clip(lower=bounds[0], upper=bounds[1])
        return result

    result[flag_column] = is_outlier
    result[score_column] = scores.max(axis=1)
    return result
