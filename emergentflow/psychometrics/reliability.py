"""
emergentflow.psychometrics.reliability
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Internal-consistency reliability (issue #164 Gap 3).

``ef.psychometrics.reliability`` computes Cronbach's alpha (and KR-20, its yes/no-item
special case) from a wide item-response matrix, plus the per-item-dropped alpha so a user
can see which item is dragging the scale down. Pure numpy; no optional dependencies.
"""

from __future__ import annotations

import pandas as pd

from emergentflow.api import public_op
from emergentflow.psychometrics.errors import PsychometricsError

__all__ = ["reliability", "cronbach_alpha"]


def _wide_item_matrix(
    df: pd.DataFrame,
    *,
    item_cols: list[str] | None,
    subject_col: str | None,
    item_col: str | None,
    score_col: str | None,
) -> tuple[pd.DataFrame, bool]:
    """Return a wide ``subjects x items`` score matrix and whether items are binary.

    Prefers the wide ``item_cols`` form. If ``score_col`` is given (long format), pivots
    ``(subject_col, item_col) -> score_col``. Raises ``PsychometricsError`` on ambiguity /
    missing columns.
    """
    if item_cols is not None:
        unknown = [c for c in item_cols if c not in df.columns]
        if unknown:
            raise PsychometricsError(
                f"unknown item columns {unknown!r}; expected one of {list(df.columns)!r}."
            )
        matrix = df[item_cols]
    elif score_col is not None:
        if subject_col is None or item_col is None:
            raise PsychometricsError(
                "long-format reliability requires subject_col and item_col alongside score_col."
            )
        for col in (subject_col, item_col, score_col):
            if col not in df.columns:
                raise PsychometricsError(
                    f"unknown column {col!r}; expected one of {list(df.columns)!r}."
                )
        matrix = df.pivot_table(
            index=subject_col, columns=item_col, values=score_col, aggfunc="first"
        )
    else:
        raise PsychometricsError("reliability needs item_cols (wide) or score_col (long format).")
    if matrix.shape[1] < 2:
        raise PsychometricsError("reliability needs at least two items.")
    numeric = matrix.apply(pd.to_numeric, errors="coerce")
    all_binary = [c for c in numeric.columns if numeric[c].dropna().isin([0, 1, True, False]).all()]
    binary = len(all_binary) == numeric.shape[1]
    return numeric, bool(binary)


def cronbach_alpha(matrix: pd.DataFrame) -> float:
    """Cronbach's alpha of a wide item-response matrix (subjects x items, numeric).

    ``alpha = k/(k-1) * (1 - sum(item_var)/total_var)`` over complete cases (listwise
    deletion). Returns ``nan`` if fewer than two complete rows remain.
    """
    m = matrix.dropna(axis=0, how="any")
    k = m.shape[1]
    if k < 2 or m.shape[0] < 2:
        return float("nan")
    item_vars = m.var(axis=0, ddof=1)
    total_var = m.sum(axis=1).var(ddof=1)
    if total_var == 0:
        return float("nan")
    alpha = (k / (k - 1)) * (1 - item_vars.sum() / total_var)
    return float(alpha)


@public_op(name="ef.psychometrics.reliability")
def reliability(
    df: pd.DataFrame,
    *,
    item_cols: list[str] | None = None,
    subject_col: str | None = None,
    item_col: str | None = None,
    score_col: str | None = None,
    method: str = "cronbach_alpha",
) -> pd.DataFrame:
    """Internal-consistency reliability of a set of items.

    ``item_cols`` is the wide form: the item columns directly. Otherwise a long-format
    pivot is built from ``(subject_col, item_col)`` with ``score_col`` as the value.
    ``method`` is ``"cronbach_alpha"`` or ``"kr20"`` (KR-20, the equivalent formula for
    binary items -- reported alongside alpha as ``kr20`` when all items are 0/1).

    Returns a tidy frame carrying ``alpha`` (Cronbach's alpha), ``kr20`` (nan unless all
    items are binary), ``n_items``, ``n_subjects`` (complete cases), and a
    ``alpha_if_dropped`` column (the scale's alpha after removing each item, so a
    low-if-dropped item is the one dragging the scale down). Never mutates ``df``.
    """
    matrix, is_binary = _wide_item_matrix(
        df,
        item_cols=item_cols,
        subject_col=subject_col,
        item_col=item_col,
        score_col=score_col,
    )
    if method not in ("cronbach_alpha", "kr20"):
        raise PsychometricsError(f"unknown method {method!r}; expected 'cronbach_alpha' or 'kr20'.")
    m = matrix.dropna(axis=0, how="any")
    if m.shape[0] < 2 or m.shape[1] < 2:
        raise PsychometricsError(
            "reliability needs at least 2 subjects with complete responses across at least "
            "2 items after dropping missing values."
        )
    alpha = cronbach_alpha(matrix)
    # KR-20 is the same formula as Cronbach's alpha restricted to binary 0/1 items; report
    # it as the binary-item special case label. Non-binary scales get nan (KR-20 undefined).
    kr20 = alpha if is_binary else float("nan")

    if_dropped: dict[str, float] = {}
    for item in m.columns:
        sub = m.drop(columns=item)
        if_dropped[str(item)] = cronbach_alpha(sub)
    rows = (
        pd.DataFrame(if_dropped.items(), columns=["item", "alpha_if_dropped"])
        .sort_values("item")
        .reset_index(drop=True)
    )
    rows.insert(0, "n_items", m.shape[1])
    rows.insert(1, "n_subjects", m.shape[0])
    rows.insert(2, "alpha", alpha)
    rows.insert(3, "kr20", kr20)
    return rows
